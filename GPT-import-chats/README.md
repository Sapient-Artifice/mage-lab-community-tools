# import_gpt_history

A Mage Lab community tool that imports exported ChatGPT conversation history into Mage Lab's native chat format, giving you a permanent, searchable local archive of conversations you would otherwise lose over time.

---

## Why this exists

ChatGPT offers an official data export, but those conversations live on OpenAI's servers and are subject to retention policies, account closures, and subscription changes. This tool bridges the gap between that export and Mage Lab's local-first chat storage, so your conversation history lives on your machine - fully searchable by Mage, never dependent on a third-party server staying online or keeping your data.

---

## Requirements

- **Python 3.8+** (no third-party packages required — stdlib only)
- **Mage Lab** installed and configured (for the assistant tool mode)
- A ChatGPT data export (see below for how to get one)

---

## How to get your ChatGPT export

1. Go to [chat.openai.com](https://chat.openai.com) and sign in
2. Click your profile icon → **Settings**
3. Under **Data controls**, click **Export data**
4. Confirm the export — OpenAI will email you a download link
5. Download and unzip the archive — you will find a `conversations.json` file inside

---

## Installation

### As a Mage Lab community tool (recommended)

Drop `import_gpt_history.py` into your Mage community tools folder:

```
~/Mage/Tools/import_gpt_history.py
```

### As a standalone CLI script

No installation needed. Run it directly with Python from wherever you saved it.

---

## Usage

### Via the Mage assistant

Once installed and Mage is restarted, just tell the assistant:

> "Import my ChatGPT history from `/path/to/conversations.json` into my chats folder."

or

> "Import my ChatGPT history from `/path/to/chatgpt-export.zip`."

Mage will call `import_gpt_history`, convert every conversation, and confirm what was saved.

---

### Command line

```
python import_gpt_history.py <input_path> [output_dir] [--overwrite]
```

**Arguments:**

| Argument | Description |
|---|---|
| `input_path` | Path to `conversations.json`, a `.zip` export bundle, or a directory containing `conversations.json`. Required. |
| `output_dir` | Where to write the converted `.json` files. Defaults to `~/Mage/Chats`. |
| `--overwrite` | Replace existing files with the same name. Off by default (duplicates are skipped). |

**Examples:**

```bash
# Point at conversations.json directly, use default output dir
python import_gpt_history.py ~/Downloads/chatgpt-export/conversations.json

# Point at the export directory
python import_gpt_history.py ~/Downloads/chatgpt-export/

# Point at the zip file
python import_gpt_history.py ~/Downloads/chatgpt-export.zip

# Custom output directory
python import_gpt_history.py ~/Downloads/chatgpt-export/ ~/my-chats/

# Overwrite any existing files
python import_gpt_history.py ~/Downloads/chatgpt-export/ --overwrite
```

**Example output:**

```
ChatGPT chat import complete.
  Imported:  3 conversation(s) → /home/yourname/Mage/Chats
    + gpt-2025-02-18-get-mac-addresses-proxmox-67b4eba9.json  (44 messages)
    + gpt-2025-01-05-firewall-mini-pc-setup-677a03f3.json  (138 messages)
    + gpt-2024-11-04-alameda-county-da-term-6728fbcf.json  (100 messages)
  Skipped:   1 (already exist)
    ~ gpt-2024-08-24-electric-field-calculation-6270aa5a.json  (already exists — pass overwrite=True to replace)
```

---

## Output format

Each conversation becomes a single `.json` file named:

```
gpt-YYYY-MM-DD-<slugged-title>-<short-id>.json
```

For example:
```
gpt-2025-02-18-get-mac-addresses-proxmox-67b4eba9.json
```

The file contains a JSON array of messages in Mage Lab's native format (OpenAI-compatible):

```json
[
  {
    "role": "system",
    "content": "This conversation was imported from ChatGPT (chat.openai.com).\nTitle: \"Get MAC Addresses Proxmox\"\nModel: gpt-4o\n..."
  },
  {
    "role": "user",
    "content": "On Proxmox, from console, how do I get a list of MAC addresses..."
  },
  {
    "role": "assistant",
    "content": "On Proxmox, you can get a list of MAC addresses using the following methods..."
  }
]
```

### System message

Every imported conversation begins with a `system` message containing:

- The original conversation title
- The model used (e.g. `gpt-4o`, `o1`, `auto`)
- Custom GPT name (if applicable)
- Whether the conversation was starred
- The original conversation UUID
- Original created and last-updated timestamps
- The timestamp when it was imported into Mage Lab

### Content type handling

ChatGPT's export uses a richer content structure than plain text. Here is how each type is handled:

| Content type | Behaviour |
|---|---|
| `text` | Included verbatim |
| `multimodal_text` | Text included verbatim; images become `[Image]` annotations |
| `code` | Included with `[Code (language)]` header |
| `execution_output` | Included with `[Code output]` header |
| `tether_quote` | Web browsing citation: `[Web source: title (url)]` |
| `tether_browsing_display` | `[Web browsing result]` with text content |
| `image_asset_pointer` | `[Image]` annotation |

### Conversation branching

ChatGPT stores conversations as a node tree, which means edited or regenerated messages create branches. The import follows the **active branch** (the path from the last message back to the root via parent pointers), correctly excluding any discarded edits or regenerations.

Only `user` and `assistant` messages are included. System and tool role messages are dropped.

---

## Idempotency

Running the import more than once on the same export is safe. Files are matched by their output filename (which encodes the conversation ID), so existing files are skipped unless `--overwrite` is passed. This means you can re-run after adding new conversations to your export without duplicating anything.

---

## Notes

- Imported conversations are **read-only historical records**. The system message marks them as such. They will appear in Mage's chat list and are fully searchable, but are not intended to be resumed as active sessions.
- All output is UTF-8 encoded with readable JSON formatting (`indent=2`).
- Control characters in message text are stripped to ensure valid JSON output.

---

## Contributing

This tool is part of the [Mage Lab community tools](https://github.com/magelab) collection. Community tools are loaded by Mage when `EXTRA_TOOLS=true` is set and are intended to be independently useful scripts that any Mage user can drop in and run.

If OpenAI changes their export format, the relevant sections to update are `_extract_content()` and `_get_active_path()` in the script.

Pull requests and issue reports welcome.
