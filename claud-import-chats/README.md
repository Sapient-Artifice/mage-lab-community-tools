# import_claude_history

A Mage Lab community tool that imports exported Claude.ai chat history into Mage Lab's native chat format, giving you a permanent, searchable local archive of conversations you would otherwise lose over time.

---

## Why this exists

Claude.ai is one of the few providers that offers full export so you can manage your long term history rather than losing it. This tool bridges the gap between that export and Mage Lab's local-first chat storage, so your conversation history lives on your machine alongside everything else - fully searchable by Mage, never dependent on a third-party server staying online or keeping your data.

---

## Requirements

- **Python 3.8+** (no third-party packages required — stdlib only)
- **Mage Lab** installed and configured (for the assistant tool mode)
- A Claude.ai data export (see below for how to get one)

---

## How to get your Claude export

1. Go to [claude.ai](https://claude.ai) and sign in
2. Open **Settings → Account**
3. Under **Data & Privacy**, click **Export Data**
4. Claude will email you a download link within a few minutes
5. Download and unzip the archive — you will find a `conversations.json` file inside

---

## Installation

### As a Mage Lab community tool (recommended)

Drop `import_claude_history.py` into your Mage community tools folder:

```
~/Mage/Tools/import_claude_history.py
```

Or, if you are working from the Mage Lab source repo, place it in:

```
backend/functions/community/import_claude_history.py
```

Then ensure `EXTRA_TOOLS=true` is set in your `~/.config/magelab/.env`. Restart Mage — the tool will be available to the assistant automatically.

### As a standalone CLI script

No installation needed. Run it directly with Python from wherever you saved it.

---

## Usage

### Via the Mage assistant

Once installed and Mage is restarted, just tell the assistant:

> "Import my Claude history from `/path/to/conversations.json` into my chats folder."

or

> "Import my Claude history from `/path/to/claude-export.zip`."

Mage will call `import_claude_history`, convert every conversation, and confirm what was saved.

---

### Command line

```
python import_claude_history.py <input_path> [output_dir] [--thinking] [--overwrite]
```

**Arguments:**

| Argument | Description |
|---|---|
| `input_path` | Path to `conversations.json`, a `.zip` export bundle, or a directory containing `conversations.json`. Required. |
| `output_dir` | Where to write the converted `.json` files. Defaults to `~/Mage/Chats`. |
| `--thinking` | Include Claude's extended thinking blocks as inline annotations. Off by default. |
| `--overwrite` | Replace existing files with the same name. Off by default (duplicates are skipped). |

**Examples:**

```bash
# Point at conversations.json directly, use default output dir
python import_claude_history.py ~/Downloads/claude-export/conversations.json

# Point at the export directory
python import_claude_history.py ~/Downloads/claude-export/

# Point at the zip file
python import_claude_history.py ~/Downloads/claude-export.zip

# Custom output directory
python import_claude_history.py ~/Downloads/claude-export/ ~/my-chats/

# Include thinking blocks, overwrite any existing files
python import_claude_history.py ~/Downloads/claude-export/ --thinking --overwrite
```

**Example output:**

```
Claude.ai chat import complete.
  Imported:  3 conversation(s) → /home/yourname/Mage/Chats
    + claude-2026-03-04-mage-lab-integration-for-research-6d824e85.json  (10 messages)
    + claude-2026-03-03-specifications-cefe2a27.json  (18 messages)
    + claude-2026-02-28-critical-analysis-of-6c3e2bbe.json  (12 messages)
  Skipped:   1 (already exist)
    ~ claude-2026-02-24-claude-cli-login-command-bbf2f155.json  (already exists — pass overwrite=True to replace)
```

---

## Output format

Each conversation becomes a single `.json` file named:

```
claude-YYYY-MM-DD-<slugged-title>-<short-uuid>.json
```

For example:
```
claude-2026-03-04-mage-lab-integration-for-bio-inspired-locomotion.json
```

The file contains a JSON array of messages in Mage Lab's native format (OpenAI-compatible):

```json
[
  {
    "role": "system",
    "content": "This conversation was imported from Claude.ai.\nTitle: \"Your Conversation Title\"\nOriginal conversation ID: 6d824e85-...\nOriginally created: 2026-03-04T21:28:57Z\n..."
  },
  {
    "role": "user",
    "content": "Can you help me with..."
  },
  {
    "role": "assistant",
    "content": "Of course! Here's what I found...\n\n[Tool call: web_search({\"query\": \"...\"})]\n\n[Tool result from web_search: Some Result Title (https://example.com)]"
  }
]
```

### System message

Every imported conversation begins with a `system` message containing:

- The original conversation title
- The original conversation summary (if present in the export)
- The original conversation UUID
- Original created and last-updated timestamps
- The timestamp when it was imported into Mage Lab

This makes imported chats easy to identify and search by Mage.

### Content block handling

The Claude.ai export includes richer message structure than plain text. Here is how each block type is handled:

| Block type | Default behaviour | With `--thinking` |
|---|---|---|
| `text` | Included verbatim | Included verbatim |
| `tool_use` | `[Tool call: name({...})]` annotation | Same |
| `tool_result` | `[Tool result from name: ...]` annotation | Same |
| `thinking` | Skipped | `[Extended thinking: ...]` annotation |

Tool call annotations preserve the tool name and inputs so you can understand what Claude was doing at each step, without needing any special rendering support.

---

## Idempotency

Running the import more than once on the same export is safe. Files are matched by their output filename (which encodes the conversation UUID), so existing files are skipped unless `--overwrite` is passed. This means you can re-run after adding new conversations to your export without duplicating anything.

---

## Notes

- The Claude.ai export format uses `sender: "human"` and `sender: "assistant"`. These are mapped to the standard `role: "user"` and `role: "assistant"` fields that Mage expects.
- Tool calls and results in Claude.ai's web interface differ from the standard API format — they are embedded within assistant messages rather than alternating as separate turns. The conversion handles this transparently.
- All output is UTF-8 encoded with readable JSON formatting (`indent=2`).

---

## Contributing

This tool is part of the [Mage Lab community tools](https://github.com/magelab) collection. Community tools are loaded by Mage when `EXTRA_TOOLS=true` is set and are intended to be independently useful scripts that any Mage user can drop in and run.

If Claude.ai changes their export format, the relevant section to update is `_extract_text_from_content()` and `_load_conversations()` in the script.

Pull requests and issue reports welcome.
