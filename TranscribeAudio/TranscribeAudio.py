"""TranscribeAudio — send a local audio file through the Mage Lab gateway's
Whisper (speech-to-text) endpoint and get back a transcription.

Auth and endpoint are taken from Mage Lab's own config, so there is nothing to
set up: it reuses the same gateway + signed-in credentials the app already uses
for voice input, so there is no separate setup or API key to manage.
"""

import logging
import os
import tempfile
import textwrap
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import httpx
import openai

from config import config
from utils.functions_metadata import function_schema

logger = logging.getLogger(__name__)

# The gateway rejects uploads larger than 25 MB; check locally to fail fast.
MAX_AUDIO_BYTES = 25 * 1024 * 1024

# Formats accepted by the Whisper endpoint. Validated up front so a mislabeled
# non-audio file fails locally instead of round-tripping the gateway.
SUPPORTED_EXTS = {
    ".flac", ".m4a", ".mp3", ".mp4", ".mpeg", ".mpga",
    ".oga", ".ogg", ".wav", ".webm",
}

# Bound the request so a stalled gateway can't hang the calling agent (the SDK
# default is 600s). Connect fast; allow time for a 25 MB upload + transcription.
REQUEST_TIMEOUT = httpx.Timeout(180.0, connect=15.0)
MAX_RETRIES = 1

# Mage Lab caps the size of any tool result before the model sees it, both
# per-line and overall. We wrap below the per-line cap and keep the inline
# preview below the overall cap; the full transcript always goes to a file, so
# nothing is lost. The values below sit comfortably under the current limits.
WRAP_WIDTH = 400
INLINE_CHAR_LIMIT = 10000


def _build_whisper_client() -> openai.OpenAI:
    """Point the OpenAI SDK at the Mage Lab gateway with the right credentials.

    Matches how the app authenticates voice input: against the hosted gateway,
    auth is the signed-in MageLab JWT (the configured api_key is a placeholder);
    elsewhere (e.g. self-hosted) it's the configured whisper_api_key.
    """
    api_key = config.whisper_api_key
    default_headers = None
    try:
        from utils.auth_state import get_magelab_token
        from utils.provider_defaults import GATEWAY_ALLOWED_HOSTS

        host = (urlparse(str(config.whisper_endpoint)).hostname or "").lower()
        if host in GATEWAY_ALLOWED_HOSTS:
            token = get_magelab_token()
            if token:
                default_headers = {"Authorization": f"Bearer {token}"}
                api_key = ""
            else:
                logger.warning(
                    "TranscribeAudio: gateway host %s but no JWT; request may 401 "
                    "(are you signed in?)",
                    host,
                )
    except Exception as e:  # pragma: no cover - defensive: fall back to api_key
        logger.warning("TranscribeAudio: could not resolve gateway JWT (%s)", e)

    kwargs = {
        "base_url": config.whisper_endpoint,
        "api_key": api_key or "",
        "timeout": REQUEST_TIMEOUT,
        "max_retries": MAX_RETRIES,
    }
    if default_headers:
        kwargs["default_headers"] = default_headers
    return openai.OpenAI(**kwargs)


def _unique_path(base: Path) -> Path:
    """Return ``base`` if free, else ``<name>-N<suffix>`` — never clobber an
    existing file (the agent could pass the same audio twice, or a file the user
    already named ``<stem>.transcript.txt``)."""
    if not base.exists():
        return base
    for i in range(1, 1000):
        candidate = base.with_name(f"{base.stem}-{i}{base.suffix}")
        if not candidate.exists():
            return candidate
    return base


def _atomic_write_text(target: Path, data: str) -> None:
    """Write text atomically with fixed LF endings, so a crash mid-write can't
    leave a truncated file and the output is byte-identical across platforms
    (``Path.write_text`` would translate ``\\n``->``\\r\\n`` on Windows)."""
    fd, tmp = tempfile.mkstemp(dir=str(target.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(data)
        os.replace(tmp, target)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


@function_schema(
    name="TranscribeAudio",
    description=(
        "Transcribe a local audio file to text using the Mage Lab gateway's "
        "Whisper speech-to-text endpoint. Supports common formats (mp3, wav, m4a, "
        "ogg, flac, webm), max 25 MB. The complete transcript is saved to a .txt "
        "file next to the source audio; a preview is returned inline."
    ),
    required_params=["audio_file_path"],
    optional_params=["language"],
)
def TranscribeAudio(audio_file_path: str, language: Optional[str] = None) -> str:
    """Transcribe an audio file to text via the Mage Lab gateway.

    :param audio_file_path: Path to the audio file (mp3, wav, m4a, ogg, flac, webm; max 25 MB).
    :param language: Optional ISO-639-1 code (e.g. 'en', 'es') to improve accuracy; auto-detected if omitted.
    :return: A status line, the saved transcript path, and an inline transcript/preview.
    """
    path = Path(audio_file_path).expanduser().resolve()
    if not path.exists() or not path.is_file():
        return f"Error: audio file not found at '{path}'."

    if path.suffix.lower() not in SUPPORTED_EXTS:
        return (
            f"Error: '{path.name}' has an unsupported extension. Supported formats: "
            f"{', '.join(sorted(e.lstrip('.') for e in SUPPORTED_EXTS))}."
        )

    size = path.stat().st_size
    if size > MAX_AUDIO_BYTES:
        return (
            f"Error: '{path.name}' is {size / 1024 / 1024:.1f} MB, over the gateway's "
            "25 MB limit. Split or compress the file and try again."
        )

    client = _build_whisper_client()
    try:
        with open(path, "rb") as fh:
            kwargs = {"model": config.whisper_model_name, "file": fh}
            if language:
                kwargs["language"] = language
            resp = client.audio.transcriptions.create(**kwargs)
    except Exception as e:
        logger.error("TranscribeAudio failed: %s", e)
        return (
            f"Error: transcription failed ({e}). Confirm you're signed in to Mage Lab "
            "and that the file is valid, supported audio."
        )

    text = (getattr(resp, "text", "") or "").strip()
    if not text:
        return f"Transcription returned no text for '{path.name}' (the audio may be silent)."

    # Wrap so no single line exceeds Mage Lab's per-line output cap. Whisper
    # returns one long unbroken paragraph; without wrapping the inline result
    # would be truncated to the first line.
    wrapped = "\n".join(textwrap.fill(line, WRAP_WIDTH) for line in text.split("\n"))
    word_count = len(text.split())

    out_path = _unique_path(path.with_name(path.stem + ".transcript.txt"))
    saved = True
    try:
        _atomic_write_text(out_path, text)
    except Exception as e:
        saved = False
        logger.warning("TranscribeAudio: could not save transcript (%s)", e)

    header = f"Transcribed '{path.name}' — {word_count} words, {len(text)} chars."
    saved_note = (
        f"Full transcript saved to: {out_path}"
        if saved
        else "(could not write transcript file; full text is inline below)"
    )

    if len(wrapped) <= INLINE_CHAR_LIMIT:
        return f"{header}\n{saved_note}\n\n{wrapped}"

    preview = wrapped[:INLINE_CHAR_LIMIT].rsplit("\n", 1)[0]
    return (
        f"{header}\n{saved_note}\n\n--- preview (beginning of transcript) ---\n"
        f"{preview}\n... [preview truncated — read the saved file for the full transcript] ..."
    )
