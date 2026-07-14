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


# ---------------------------------------------------------------------------
# mage-memory (SQLite graph.db) backend
# ---------------------------------------------------------------------------

import sqlite3

_MIN_SCHEMA = """
CREATE TABLE entities (name TEXT PRIMARY KEY, entity_type TEXT NOT NULL,
    sensitivity TEXT NOT NULL DEFAULT 'ecosystem');
CREATE TABLE observations (id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_name TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE,
    content TEXT NOT NULL, sensitivity TEXT DEFAULT 'ecosystem', created_by TEXT);
CREATE TABLE relations (id INTEGER PRIMARY KEY AUTOINCREMENT,
    from_entity TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE,
    to_entity TEXT NOT NULL REFERENCES entities(name) ON DELETE CASCADE,
    relation_type TEXT NOT NULL, sensitivity TEXT DEFAULT 'ecosystem',
    UNIQUE(from_entity, to_entity, relation_type));
"""


def _graph(tmp_path):
    """A graph.db with the minimal mage-memory schema + a native entity."""
    p = tmp_path / "graph.db"
    c = sqlite3.connect(str(p))
    c.executescript(_MIN_SCHEMA)
    c.execute("INSERT INTO entities (name, entity_type) VALUES ('Native', 'Bug')")
    c.execute("INSERT INTO observations (entity_name, content) VALUES ('Native', 'native fact')")
    c.commit(); c.close()
    return p


def _projects(tmp_path):
    proj = tmp_path / "projects"
    mem = proj / "-Users-kmertens-Sapient-Artifice-demo" / "memory"
    _write_memory(mem, "foo-rule", "feedback", "Always foo. See [[bar-note]].")
    _write_memory(mem, "bar-note", "project", "Bar context.")
    return proj


class TestMageMemoryBackend:
    def test_missing_db_errors(self, tmp_path):
        r = s.sync_claude_code_memory(projects_dir=str(_projects(tmp_path)),
                                      store=str(tmp_path / "nope.db"), backend="mage-memory")
        assert "graph db not found" in r.get("error", "")

    def test_writes_cli_entities_preserves_native(self, tmp_path):
        proj, db = _projects(tmp_path), _graph(tmp_path)
        r = s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory")
        assert r["cli_entities"] == 2 and r["cli_relations"] == 1
        c = sqlite3.connect(str(db))
        names = {row[0] for row in c.execute("SELECT name FROM entities")}
        assert {"foo-rule", "bar-note", "Native"} <= names
        # native untouched
        assert c.execute("SELECT content FROM observations WHERE entity_name='Native'").fetchone()[0] == "native fact"
        # origin marker present on cli entities
        marked = c.execute("SELECT COUNT(DISTINCT entity_name) FROM observations WHERE content LIKE 'origin: claude-code-cli%'").fetchone()[0]
        assert marked == 2
        # link -> relation
        assert c.execute("SELECT COUNT(*) FROM relations WHERE from_entity='foo-rule' AND to_entity='bar-note'").fetchone()[0] == 1
        c.close()

    def test_idempotent(self, tmp_path):
        proj, db = _projects(tmp_path), _graph(tmp_path)
        s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory", no_backup=True)
        s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory", no_backup=True)
        c = sqlite3.connect(str(db))
        # no duplication: 3 entities, 2 obs per cli entity (desc + provenance), native intact
        assert c.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 3
        assert c.execute("SELECT COUNT(*) FROM observations WHERE entity_name='foo-rule'").fetchone()[0] == 2
        assert c.execute("SELECT COUNT(*) FROM relations").fetchone()[0] == 1
        c.close()

    def test_prunes_removed_memory(self, tmp_path):
        proj, db = _projects(tmp_path), _graph(tmp_path)
        s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory", no_backup=True)
        (proj / "-Users-kmertens-Sapient-Artifice-demo" / "memory" / "bar-note.md").unlink()
        s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory", no_backup=True)
        c = sqlite3.connect(str(db))
        names = {row[0] for row in c.execute("SELECT name FROM entities")}
        assert "bar-note" not in names
        assert {"foo-rule", "Native"} <= names
        assert c.execute("SELECT COUNT(*) FROM relations WHERE to_entity='bar-note'").fetchone()[0] == 0
        c.close()

    def test_dry_run_writes_nothing(self, tmp_path):
        proj, db = _projects(tmp_path), _graph(tmp_path)
        r = s.sync_claude_code_memory(projects_dir=str(proj), store=str(db), backend="mage-memory", dry_run=True)
        assert r.get("would_write") and r["cli_entities"] == 2
        c = sqlite3.connect(str(db))
        assert c.execute("SELECT COUNT(*) FROM entities").fetchone()[0] == 1  # only Native
        c.close()
