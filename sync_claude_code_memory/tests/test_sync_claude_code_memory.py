"""Tests for sync_claude_code_memory — the CLI-memory → knowledge-graph sync."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sync_claude_code_memory as s  # noqa: E402


def _write_memory(mem: Path, name: str, mtype: str, body: str, description: str = "d"):
    mem.mkdir(parents=True, exist_ok=True)
    (mem / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\nmetadata:\n"
        f"  node_type: memory\n  type: {mtype}\n---\n\n{body}\n",
        encoding="utf-8",
    )


@pytest.fixture
def sandbox(tmp_path):
    proj = tmp_path / "projects"
    store = tmp_path / "memory.jsonl"
    mem = proj / "-Users-kmertens-Sapient-Artifice-demo" / "memory"
    _write_memory(mem, "foo-rule", "feedback", "Always foo. See [[bar-note]].")
    _write_memory(mem, "bar-note", "project", "Bar context.")
    (mem / "MEMORY.md").write_text("# index\n", encoding="utf-8")
    # native, non-owned data that must survive
    store.write_text(
        json.dumps({"type": "entity", "name": "Native", "entityType": "Bug",
                    "observations": ["native fact"]}) + "\n" +
        json.dumps({"type": "relation", "from": "Native", "to": "Native",
                    "relationType": "self"}) + "\n",
        encoding="utf-8",
    )
    return proj, store


def _load(store):
    ents, rels = [], []
    for line in store.read_text().splitlines():
        o = json.loads(line)
        (ents if o["type"] == "entity" else rels).append(o)
    return ents, rels


def test_creates_entities_and_link_relations(sandbox):
    proj, store = sandbox
    r = s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    assert r["cli_entities"] == 2 and r["cli_relations"] == 1
    ents, rels = _load(store)
    names = {e["name"] for e in ents}
    assert {"foo-rule", "bar-note"} <= names
    assert any(x["from"] == "foo-rule" and x["to"] == "bar-note"
               and x["relationType"] == "relates_to" for x in rels)


def test_native_data_preserved(sandbox):
    proj, store = sandbox
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    ents, rels = _load(store)
    assert any(e["name"] == "Native" for e in ents), "native entity dropped"
    assert any(x.get("relationType") == "self" for x in rels), "native relation dropped"


def test_ownership_marker_and_provenance(sandbox):
    proj, store = sandbox
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    ents, _ = _load(store)
    foo = next(e for e in ents if e["name"] == "foo-rule")
    assert any(o.startswith(s.ORIGIN_MARKER) for o in foo["observations"])
    assert s._is_owned(foo) and not s._is_owned(
        next(e for e in ents if e["name"] == "Native"))


def test_idempotent(sandbox):
    proj, store = sandbox
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    first = store.read_text()
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store), no_backup=True)
    assert store.read_text() == first


def test_removed_memory_is_pruned_from_graph(sandbox):
    proj, store = sandbox
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    # delete a memory file, re-sync: its entity should disappear, native stays
    mem = proj / "-Users-kmertens-Sapient-Artifice-demo" / "memory"
    (mem / "bar-note.md").unlink()
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store), no_backup=True)
    ents, rels = _load(store)
    names = {e["name"] for e in ents}
    assert "bar-note" not in names
    assert "foo-rule" in names and "Native" in names
    # the dangling link relation is gone too
    assert not any(x["to"] == "bar-note" for x in rels)


def test_mage_type_not_touched_when_dry_run(sandbox):
    proj, store = sandbox
    before = store.read_text()
    r = s.sync_claude_code_memory(projects_dir=str(proj), store=str(store), dry_run=True)
    assert r["dry_run"] and r.get("would_write")
    assert store.read_text() == before  # dry run writes nothing


def test_thin_index_no_body_dump(tmp_path):
    """Entities carry the summary + a file pointer, NOT the full body."""
    proj = tmp_path / "projects"
    store = tmp_path / "m.jsonl"
    mem = proj / "-Users-kmertens-x" / "memory"
    mem.mkdir(parents=True)
    (mem / "big.md").write_text(
        "---\nname: big\ndescription: one-line summary\nmetadata:\n  type: project\n---\n\n"
        "SECRET_BODY_MARKER paragraph one.\n\nSECRET_BODY_MARKER paragraph two.\n",
        encoding="utf-8")
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    ents, _ = _load(store)
    big = next(e for e in ents if e["name"] == "big")
    assert big["observations"][0] == "one-line summary"
    assert not any("SECRET_BODY_MARKER" in o for o in big["observations"])
    assert any("full text:" in o and "big.md" in o for o in big["observations"])
    assert len(big["observations"]) == 2


def test_quoted_description_with_colon(tmp_path):
    proj = tmp_path / "projects"
    store = tmp_path / "m.jsonl"
    mem = proj / "-Users-kmertens-x" / "memory"
    mem.mkdir(parents=True)
    (mem / "q.md").write_text(
        '---\nname: q\ndescription: "Note: colons: kept"\nmetadata:\n  type: reference\n---\n\nbody\n',
        encoding="utf-8")
    s.sync_claude_code_memory(projects_dir=str(proj), store=str(store))
    ents, _ = _load(store)
    q = next(e for e in ents if e["name"] == "q")
    assert q["observations"][0] == "Note: colons: kept"
    assert q["entityType"] == "Reference"
