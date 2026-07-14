# sync_claude_code_memory

Mirror the **Claude Code CLI memory tree** into **Mage Lab's knowledge-graph memory**, so Mage has an integrated, cross-tool view of what you're working on.

This is the memory counterpart to `import_claude_code_sessions` (which imports CLI *chats*). It is Claude Code–specific by design: Mage is model-agnostic (dozens of models across frontier providers), and other sources can sync into the same graph under their own provenance namespace.

---

## ⚠️ Do this FIRST: give the memory store a durable home

**The reference `@modelcontextprotocol/server-memory` (the memory server the MCP foundation publishes, which Mage runs via `npx`) defaults its store to a file *inside the npx package cache* — and that cache is ephemeral.**

With no `MEMORY_FILE_PATH` set, the graph is written to:

```
~/.npm/_npx/<hash>/node_modules/@modelcontextprotocol/server-memory/dist/memory.jsonl
```

That `<hash>` is tied to the resolved package version. So an `npm cache clean`, an npx cache eviction, or a package version bump **silently creates a fresh, empty store under a new hash** — the graph appears to "reset" and the old data is orphaned (and, in practice, lost). For something meant to be a *permanent record of your work*, this is quicksand — it's how a prior manual sync's data disappeared.

**Fix it before syncing anything.** Point the server at a stable absolute path in `~/.config/magelab/mcp_servers.json`:

```json
"memory": {
  "command": "npx",
  "args": ["-y", "@modelcontextprotocol/server-memory"],
  "env": { "MEMORY_FILE_PATH": "/Users/<you>/Mage/memory/memory.jsonl" },
  "enabled": true
}
```

Then: migrate any existing `memory.jsonl` from the cache to that path, and **restart the memory server (reload Mage)** so it loads the new location. (The server also auto-migrates a legacy `memory.json` to `memory.jsonl`.) Only after the store is on bedrock should you run this sync — otherwise everything it writes is still living in the cache and can vanish.

---

## What it does

The Claude Code CLI keeps a per-project markdown memory tree at `~/.claude/projects/<project>/memory/*.md` — each file has YAML frontmatter (`name`, `description`, `metadata.type`) and a body that may contain `[[links]]` to other memories.

Mage's memory is the reference [`@modelcontextprotocol/server-memory`](https://github.com/modelcontextprotocol/servers/tree/main/src/memory) knowledge graph, stored as JSONL (`entity` / `relation` records). This tool maps one onto the other:

| CLI memory | → | Knowledge graph |
|---|---|---|
| a `*.md` file | → | an **entity** (`name`, `entityType` = title-cased `metadata.type`) |
| `description` (the one-line summary) | → | the entity's content observation |
| each `[[link]]` | → | a **`relates_to` relation** (only when the target is also in the set — no dangling edges) |
| — | → | a provenance observation: `origin: claude-code-cli \| project: … \| file: … \| full text: <path>` |

**Thin-index by design.** The entity carries the memory's *summary* and a **pointer to the source file** — not the full body. Dumping dense memory bodies as observations makes `read_graph` enormous and overflows the assistant's context (some research memories are 10–25 KB each). The graph stays a small, queryable map; the full prose lives in the source files and is retrievable on demand via the pointer.

`MEMORY.md` index files are skipped.

## Safety & idempotency

- **Non-destructive to Mage-native memory.** The sync only manages entities it created, identified by the `origin: claude-code-cli` observation marker. Every run rebuilds *that owned subset* and leaves all Mage-native entities/relations untouched. Deleting a CLI memory prunes its entity on the next run; nothing else is affected.
- **Idempotent.** Re-running with unchanged input produces an identical store.
- **Atomic + backed up.** The store is copied to `<store-dir>/backups/` before each write, and the new store is written to a temp file and renamed into place, so a crash mid-write can't corrupt the graph.

## Usage

**CLI:**
```bash
python sync_claude_code_memory.py [--projects-dir DIR] [--store PATH] \
                                  [--only PROJECT ...] [--dry-run] [--no-backup]
```
- `--projects-dir` — root of the CLI memory (default `~/.claude/projects`). Point at an rsync backup to avoid reading live data.
- `--store` — the memory-server JSONL store (default `~/Mage/memory/memory.jsonl`).
- `--only` — restrict to one or more project directory names.
- `--dry-run` — report what would change without writing.

**As a Mage tool:** ask the assistant to run `sync_claude_code_memory`.

> The durable-store step above (`MEMORY_FILE_PATH`) is a prerequisite, not optional — see [Do this FIRST](#️-do-this-first-give-the-memory-store-a-durable-home).

## Tests

```bash
uv run --with pytest python -m pytest tests/ -q
```
