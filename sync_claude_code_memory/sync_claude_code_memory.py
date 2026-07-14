#!/usr/bin/env python3
"""Sync Claude Code CLI memory into Mage Lab's knowledge-graph memory.

The Claude Code CLI keeps a per-project **markdown memory tree** at
``~/.claude/projects/<project>/memory/*.md`` — each file has YAML frontmatter
(``name``, ``description``, ``metadata.type``) and a body that may contain
``[[links]]`` to other memories. Mage Lab's memory is the reference
``@modelcontextprotocol/server-memory`` **knowledge graph** (JSONL of
``entity`` and ``relation`` records). This tool mirrors the former into the
latter so Mage has an integrated view of what you're working on across tools.

CLI usage:

    python sync_claude_code_memory.py [--projects-dir DIR] [--store PATH]
                              [--only PROJECT ...] [--dry-run] [--no-backup]

    --projects-dir  Root of the CLI project memory (default: ~/.claude/projects).
                    Point at an rsync backup to avoid touching live data.
    --store         Path to the memory-server JSONL store
                    (default: ~/Mage/memory/memory.jsonl).
    --only          Restrict to one or more project directory names.
    --dry-run       Report what would change without writing.
    --no-backup     Skip the pre-write timestamped backup (not recommended).

Mage tool usage:

    Ask the assistant to run sync_claude_code_memory.

Design notes:

    * Mapping — one memory file -> one entity:
        name        = frontmatter 'name' (falls back to the file stem)
        entityType  = title-cased metadata.type (Feedback/Project/Reference/User)
        observations= [description] + body paragraphs + a provenance line
        [[link]]    -> a 'relates_to' relation (only when the target is also
                       in this sync's entity set, so no dangling relations)

    * Ownership / idempotency — the sync only manages entities it created,
      identified by an ``origin: claude-code-cli`` observation marker. On every run
      it rebuilds that owned subset from the markdown and leaves every
      Mage-native entity/relation untouched. Re-running is a no-op if nothing
      changed.

    * Safety — writes atomically (temp file + rename) after a timestamped
      backup of the store, so a crash mid-write can't corrupt the graph.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

ORIGIN_MARKER = "origin: claude-code-cli"
DEFAULT_PROJECTS_DIR = Path.home() / ".claude" / "projects"
DEFAULT_STORE = Path.home() / "Mage" / "memory" / "memory.jsonl"
_LINK_RE = re.compile(r"\[\[([^\]]+)\]\]")
_PROJECT_PREFIX = "-Users-" + (os.environ.get("USER") or "") + "-"


# ---------------------------------------------------------------------------
# Frontmatter parsing (targeted — PyYAML is not a dependency)
# ---------------------------------------------------------------------------

def _unquote(v: str) -> str:
    v = v.strip()
    if len(v) >= 2 and v[0] == v[-1] and v[0] in ("'", '"'):
        return v[1:-1]
    return v


def _parse_frontmatter(raw: str) -> Dict[str, Any]:
    """Extract the fields we need (name, description, metadata.type).

    Handles the observed shape: top-level ``key: value`` plus an indented
    ``metadata:`` block. Not a full YAML parser — deliberately narrow.
    """
    out: Dict[str, Any] = {"metadata": {}}
    in_meta = False
    for line in raw.splitlines():
        if not line.strip():
            continue
        indented = line[0] in (" ", "\t")
        key, sep, val = line.strip().partition(":")
        if not sep:
            continue
        key = key.strip()
        val = _unquote(val)
        if indented:
            if in_meta:
                out["metadata"][key] = val
        else:
            if key == "metadata":
                in_meta = True
            else:
                in_meta = False
                out[key] = val
    return out


def parse_memory_file(path: Path) -> Optional[Dict[str, Any]]:
    """Return {name, description, mtype, body, links} for one memory file."""
    try:
        text = path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return None
    if not text.lstrip().startswith("---"):
        return None
    # Split on the first two '---' fences.
    stripped = text.lstrip()
    parts = stripped.split("---", 2)
    if len(parts) < 3:
        return None
    fm = _parse_frontmatter(parts[1])
    body = parts[2].lstrip("\n")
    name = (fm.get("name") or path.stem).strip()
    if not name:
        return None
    links = []
    for m in _LINK_RE.findall(body):
        t = m.strip()
        if t and t != name and t not in links:
            links.append(t)
    return {
        "name": name,
        "description": (fm.get("description") or "").strip(),
        "mtype": (fm.get("metadata", {}).get("type") or "").strip(),
        "body": body,
        "links": links,
    }


# ---------------------------------------------------------------------------
# Mapping memory -> entity/relation
# ---------------------------------------------------------------------------

def _project_label(project_dir_name: str) -> str:
    """Human-ish label for a project dir (strip the encoded home prefix)."""
    label = project_dir_name
    if label.startswith(_PROJECT_PREFIX):
        label = label[len(_PROJECT_PREFIX):]
    return label or project_dir_name


def _entity_type(mtype: str) -> str:
    return mtype.strip().title() if mtype.strip() else "Memory"


_DESC_FALLBACK_MAX = 280


def _observations(
    rec: Dict[str, Any], project_label: str, rel_path: str, source_path: str
) -> List[str]:
    """Thin-index observations: the memory's one-line summary + a pointer.

    We deliberately do NOT copy the full body into the graph — dense memories
    would bloat read_graph and overflow the assistant's context. The body stays
    in the source file, retrievable on demand via the pointer below.
    """
    obs: List[str] = []
    desc = rec["description"].strip()
    if desc:
        obs.append(desc)
    else:
        # No description — fall back to the first body line so the node isn't empty.
        for line in rec["body"].splitlines():
            line = line.strip()
            if line:
                obs.append(line[:_DESC_FALLBACK_MAX])
                break
    obs.append(
        f"{ORIGIN_MARKER} | project: {project_label} | file: {rel_path} | "
        f"full text: {source_path}"
    )
    return obs


def build_desired_graph(
    projects_dir: Path, only: Optional[List[str]] = None
) -> Tuple[List[dict], List[dict], List[str]]:
    """Scan the memory tree and return (entities, relations, warnings)."""
    warnings: List[str] = []
    files: List[Tuple[str, Path]] = []
    for proj_dir in sorted(projects_dir.glob("*")):
        mem = proj_dir / "memory"
        if not mem.is_dir():
            continue
        if only and proj_dir.name not in only:
            continue
        for f in sorted(mem.glob("*.md")):
            if f.name == "MEMORY.md":
                continue
            files.append((proj_dir.name, f))

    entities: List[dict] = []
    name_to_source: Dict[str, str] = {}
    parsed: List[Tuple[str, Dict[str, Any]]] = []  # (project_label, rec)
    for proj_name, f in files:
        rec = parse_memory_file(f)
        if rec is None:
            warnings.append(f"skipped (unparseable frontmatter): {f}")
            continue
        label = _project_label(proj_name)
        name = rec["name"]
        source = f"{label}/{f.name}"
        if name in name_to_source:
            new_name = f"{name} ({label})"
            warnings.append(
                f"name collision '{name}' ({source} vs {name_to_source[name]}); "
                f"renamed this one to '{new_name}'"
            )
            name = new_name
            rec["name"] = name
        name_to_source[name] = source
        parsed.append((label, rec, f.name))  # type: ignore[arg-type]
        entities.append({
            "type": "entity",
            "name": name,
            "entityType": _entity_type(rec["mtype"]),
            "observations": _observations(rec, label, f.name, str(f)),
        })

    known = {e["name"] for e in entities}
    relations: List[dict] = []
    seen = set()
    for label, rec, _fname in parsed:
        for target in rec["links"]:
            if target in known and target != rec["name"]:
                key = (rec["name"], target)
                if key not in seen:
                    seen.add(key)
                    relations.append({
                        "type": "relation",
                        "from": rec["name"],
                        "to": target,
                        "relationType": "relates_to",
                    })
    return entities, relations, warnings


# ---------------------------------------------------------------------------
# Store I/O + reconcile
# ---------------------------------------------------------------------------

def _load_store(store: Path) -> Tuple[List[dict], List[dict]]:
    entities, relations = [], []
    if not store.exists():
        return entities, relations
    for line in store.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            o = json.loads(line)
        except json.JSONDecodeError:
            continue
        if o.get("type") == "entity":
            entities.append(o)
        elif o.get("type") == "relation":
            relations.append(o)
    return entities, relations


def _is_owned(entity: dict) -> bool:
    return any(
        isinstance(o, str) and o.startswith(ORIGIN_MARKER)
        for o in entity.get("observations", [])
    )


def reconcile(
    store_entities: List[dict],
    store_relations: List[dict],
    desired_entities: List[dict],
    desired_relations: List[dict],
) -> Tuple[List[dict], List[dict], Dict[str, int]]:
    """Replace the sync-owned subset; leave Mage-native records untouched."""
    prev_owned_names = {e["name"] for e in store_entities if _is_owned(e)}
    native_entities = [e for e in store_entities if not _is_owned(e)]
    # A relation is owned if it touches a previously-owned entity name.
    native_relations = [
        r for r in store_relations
        if r.get("from") not in prev_owned_names and r.get("to") not in prev_owned_names
    ]

    out_entities = native_entities + desired_entities
    out_relations = native_relations + desired_relations
    stats = {
        "native_entities": len(native_entities),
        "native_relations": len(native_relations),
        "cli_entities": len(desired_entities),
        "cli_relations": len(desired_relations),
        "prev_cli_entities": len(prev_owned_names),
    }
    return out_entities, out_relations, stats


def _write_store(store: Path, entities: List[dict], relations: List[dict]) -> None:
    store.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, ensure_ascii=False) for e in entities]
    lines += [json.dumps(r, ensure_ascii=False) for r in relations]
    tmp = store.with_suffix(store.suffix + ".tmp")
    tmp.write_text("\n".join(lines), encoding="utf-8")
    os.replace(tmp, store)


def _backup(store: Path) -> Optional[str]:
    if not store.exists():
        return None
    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    bdir = store.parent / "backups"
    bdir.mkdir(parents=True, exist_ok=True)
    dest = bdir / f"{store.stem}-{ts}{store.suffix}"
    shutil.copy2(store, dest)
    return str(dest)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def sync_claude_code_memory(
    projects_dir: Optional[str] = None,
    store: Optional[str] = None,
    only: Optional[List[str]] = None,
    dry_run: bool = False,
    no_backup: bool = False,
) -> dict:
    """Mirror the CLI memory tree into Mage's knowledge-graph store."""
    proj = Path(projects_dir).expanduser() if projects_dir else DEFAULT_PROJECTS_DIR
    store_path = Path(store).expanduser() if store else DEFAULT_STORE

    if not proj.is_dir():
        return {"error": f"projects_dir not found: {proj}"}

    desired_entities, desired_relations, warnings = build_desired_graph(proj, only)
    store_entities, store_relations = _load_store(store_path)
    out_entities, out_relations, stats = reconcile(
        store_entities, store_relations, desired_entities, desired_relations
    )

    result = {
        "store": str(store_path),
        "projects_scanned": sorted({
            _project_label(p.name)
            for p in proj.glob("*") if (p / "memory").is_dir()
            and (not only or p.name in only)
        }),
        "warnings": warnings,
        "dry_run": dry_run,
        **stats,
        "total_entities_after": len(out_entities),
        "total_relations_after": len(out_relations),
    }

    if dry_run:
        result["would_write"] = True
        return result

    backup = None if no_backup else _backup(store_path)
    _write_store(store_path, out_entities, out_relations)
    result["backup"] = backup
    result["written"] = True
    return result


# ---------------------------------------------------------------------------
# Mage tool registration
# ---------------------------------------------------------------------------

try:
    from utils.functions_metadata import function_schema  # noqa: PLC0415

    sync_claude_code_memory = function_schema(
        name="sync_claude_code_memory",
        description=(
            "Sync the Claude Code CLI markdown memory tree "
            "(~/.claude/projects/*/memory) into Mage Lab's knowledge-graph "
            "memory store (memory.jsonl). Each memory file becomes an entity "
            "with observations and [[link]]-derived relations. Only sync-owned "
            "entities (tagged origin: claude-code-cli) are managed; Mage-native "
            "memory is left untouched. Idempotent; backs up the store first."
        ),
        required_params=[],
        optional_params=["projects_dir", "store", "only", "dry_run", "no_backup"],
    )(sync_claude_code_memory)
except ImportError:
    pass


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _cli() -> None:
    parser = argparse.ArgumentParser(
        description="Sync Claude Code CLI memory into Mage's knowledge graph.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument("--projects-dir", default=None,
                        help="Root of CLI project memory (default: ~/.claude/projects).")
    parser.add_argument("--store", default=None,
                        help="memory-server JSONL store (default: ~/Mage/memory/memory.jsonl).")
    parser.add_argument("--only", nargs="*", default=None,
                        help="Restrict to these project directory names.")
    parser.add_argument("--dry-run", action="store_true", default=False,
                        help="Report changes without writing.")
    parser.add_argument("--no-backup", action="store_true", default=False,
                        help="Skip the pre-write backup (not recommended).")
    args = parser.parse_args()
    result = sync_claude_code_memory(
        projects_dir=args.projects_dir,
        store=args.store,
        only=args.only,
        dry_run=args.dry_run,
        no_backup=args.no_backup,
    )
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # Non-zero exit on a logical error so the scheduler records a failed run.
    if result.get("error"):
        sys.exit(1)


if __name__ == "__main__":
    _cli()
