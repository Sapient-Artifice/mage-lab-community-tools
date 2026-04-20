# Claude Code Session Import

Import [Claude Code](https://code.claude.com) CLI session transcripts into Mage Lab's unified chat archive.

This is the CLI companion to [`claud-import-chats/import_claude_history.py`](../claud-import-chats/import_claude_history.py), which handles server-side Claude.ai chat exports. Both tools produce the same output format so that GUI and CLI conversations land in a single searchable archive.

## What it does

Claude Code stores every terminal session as a `.jsonl` file under `~/.claude/projects/`. This tool reads those files, extracts the conversation (user prompts, assistant responses, tool calls, tool results), and writes each session as a Mage-compatible JSON chat file.

Each output file includes a system message with provenance metadata — project path, git branch, session ID, Claude Code version, timestamps — so you always know where a conversation came from.

Output filenames use the prefix `claude-code-` (vs. `claude-` for GUI chats) so you can distinguish origin at a glance:

```
claude-code-2026-04-15-sunny-hatching-neumann-31f3f224.json
```

## Quick start

No dependencies beyond Python 3.8+. Copy the script into your `~/Mage/Tools` directory, or run it standalone:

```bash
python import_claude_code_sessions.py
```

That's it. With no arguments, it reads from `~/.claude/projects/` and writes to `~/Mage/Chats/`.

## Recommended workflow: backup + import

The simplest setup is a single shell script that backs up and imports in sequence. Save this as `~/Mage/Scheduler/scripts/claude-code-backup-and-import.sh` and schedule it with Mage Lab's scheduler:

```bash
#!/bin/bash
set -euo pipefail

mkdir -p ~/backups/claude-code/projects/

echo "Starting backup: $(date)"
rsync -a --delete ~/.claude/projects/ ~/backups/claude-code/projects/
rsync -a ~/.claude/history.jsonl ~/backups/claude-code/
echo "Backup completed: $(date)"

echo "Starting import: $(date)"
python3 ~/Mage/Tools/import_claude_code_sessions.py ~/backups/claude-code/projects/ --overwrite
echo "Import completed: $(date)"
```

The key points:
- **Import from the backup copy**, not `~/.claude/projects/` directly — avoids reading files that Claude Code may be writing mid-session.
- **`--overwrite`** regenerates existing files on each run, so long-running sessions that accumulated new messages since last import stay up to date.
- The script runs both steps together. If you want to retry the import independently of the backup (or run them on different schedules), split them into two separate scheduler tasks and set the import as a dependent job of the backup.

On each run the tool skips sessions that haven't changed (by output filename match when not using `--overwrite`), so without that flag it's naturally incremental — no state file, no database, no tracking to manage.

## Usage

```
python import_claude_code_sessions.py [input_dir] [output_dir] [options]
```

| Argument | Default | Description |
|---|---|---|
| `input_dir` | `~/.claude/projects` | Path to the `projects/` directory (or a backup copy of it) |
| `output_dir` | `~/Mage/Chats` | Where to write converted chat files |

| Option | Description |
|---|---|
| `--thinking` | Include Claude's extended thinking blocks as `[Extended thinking: ...]` annotations |
| `--overwrite` | Replace existing output files instead of skipping them |
| `--include-agents` | Also import sub-agent session files (`agent-*.jsonl`), which are excluded by default |

## Example output

```
Claude Code session import complete.
  Source: /Users/you/backups/claude-code/projects
  Scanned: 28 session file(s)
  Imported: 3 session(s) → /Users/you/Mage/Chats
    + claude-code-2026-04-17-fix-auth-middleware-a1b2c3d4.json (42 messages, /Users/you/Projects/webapp)
    + claude-code-2026-04-18-add-rate-limiting-e5f6a7b8.json (18 messages, /Users/you/Projects/webapp)
    + claude-code-2026-04-19-sunny-hatching-neumann-31f3f224.json (7 messages, /Users/you/Projects/sapient-artifice)
  Skipped: 23 (already exist)
  Empty: 2 (no conversation content)
  Errors: 0
  Date range: 2026-04-17 → 2026-04-19
  Total output size: 94.3 KB
```

## Mage tool registration

When running inside Mage Lab, the script auto-registers as a callable tool via `function_schema`. Ask the assistant to run `import_claude_code_sessions` and optionally provide a path to your backup directory.

## Security note

Claude Code session transcripts are stored in plaintext and may contain sensitive data. If a tool read a `.env` file or a command printed a credential during a session, that value is present in the `.jsonl` file and will be carried into the converted chat output.

Encrypt your backups accordingly, and consider using Claude Code's `permissions.deny` rules to prevent reads of credential files in the first place.

## How it relates to `import_claude_history.py`

| | `import_claude_history.py` | `import_claude_code_sessions.py` |
|---|---|---|
| **Source** | Claude.ai server-side export (`conversations.json` or `.zip`) | Local `~/.claude/projects/` session files |
| **Trigger** | Manual — request export from Settings → Privacy | Automated — runs on schedule against rsync backup |
| **Filename prefix** | `claude-` | `claude-code-` |
| **Output format** | Identical | Identical |

Both produce `[{role, content}, ...]` JSON files with a leading system message. They can coexist in the same `~/Mage/Chats` directory without collisions.

## License

MIT — see the repository root [LICENSE](../LICENSE) for details.
