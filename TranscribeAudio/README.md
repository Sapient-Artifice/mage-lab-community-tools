# TranscribeAudio Tool

## Overview

**TranscribeAudio** transcribes a local audio file to text using the mage lab
gateway's Whisper (speech-to-text) endpoint — the same gateway and signed-in
credentials the app already uses for voice input. There is nothing to configure:
the tool reads the endpoint, model, and auth from your mage lab session.

### Features:
- Transcribes all Whisper-supported formats: **flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm** (max 25 MB)
- Optional language hint (ISO-639-1, e.g. `en`, `es`) for better accuracy
- Saves the **complete** transcript to a `.txt` file next to the source audio
- Returns a clean inline transcript (or a preview, for long recordings), wrapped
  so it survives mage lab's tool-output limits without being truncated mid-word

## Functions

### `TranscribeAudio(audio_file_path, language=None)`
Transcribe an audio file to text via the mage lab gateway.

**Arguments:**
- `audio_file_path` *(str)*: Path to the audio file (flac, m4a, mp3, mp4, mpeg, mpga, oga, ogg, wav, webm; max 25 MB).
- `language` *(str, optional)*: ISO-639-1 code (e.g. `en`, `es`) to improve accuracy. Auto-detected if omitted.

**Returns:**
A status line (filename, word/char count), the path of the saved `.txt`
transcript, and the inline transcript or a preview for long files.

## Examples

Transcribe a voice memo (auto-detect language):
```
TranscribeAudio(audio_file_path="~/Downloads/meeting.m4a")
```

Transcribe a Spanish recording with a language hint:
```
TranscribeAudio(audio_file_path="/path/to/entrevista.mp3", language="es")
```

## Requirements

- You must be **signed in to mage lab** — the tool authenticates to the hosted
  gateway with your session token. If you are not signed in, the tool returns a
  clear error rather than failing silently.
- No extra Python packages are needed; it uses the `openai` client already
  bundled with mage lab.

## Notes

- Files over **25 MB** are rejected up front (the gateway's hard limit). Split or
  compress longer recordings before transcribing.
- The full transcript is always written to `<audio-file-name>.transcript.txt`
  beside the source file, so nothing is lost even when the inline output is
  shortened for long recordings.

## License

This tool inherits the MIT License from the mage lab Community Tools repository.
