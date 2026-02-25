from __future__ import annotations

import json
from pathlib import Path
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "mage_scheduler.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)


@event.listens_for(engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _):
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA busy_timeout=5000")
    cur.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    # Import models to register them with SQLAlchemy
    from models import TaskRequest, Action, Settings  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_default_actions()


_ASK_ASSISTANT_SCRIPT = Path(__file__).resolve().parent / "scripts" / "ask_assistant.py"


def _seed_default_actions() -> None:
    from models import Action

    with SessionLocal() as session:
        existing = session.execute(
            select(Action).where(Action.name == "ask_assistant")
        ).scalar_one_or_none()
        if existing is None:
            action = Action(
                name="ask_assistant",
                description="Send a scheduled message to the assistant.",
                command=f"/usr/bin/python3 {_ASK_ASSISTANT_SCRIPT}",
                allowed_env_json=json.dumps(["MESSAGE"]),
            )
            session.add(action)
            session.commit()


def _migrate_schema() -> None:
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(task_requests)").fetchall()}
        if not columns:
            return
        _add_column_if_missing(connection, "task_requests", columns, "intent_version", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "source", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "action_id", "INTEGER")
        _add_column_if_missing(connection, "task_requests", columns, "action_name", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "cwd", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "env_json", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "notify_on_complete", "INTEGER NOT NULL DEFAULT 0")

        action_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(actions)").fetchall()
        }
        if action_columns:
            _add_column_if_missing(connection, "actions", action_columns, "default_cwd", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_env_json", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_command_dirs_json", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_cwd_dirs_json", "TEXT")

        settings_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)").fetchall()
        }
        if settings_columns:
            _add_column_if_missing(connection, "settings", settings_columns, "allowed_command_dirs_json", "TEXT")
            _add_column_if_missing(connection, "settings", settings_columns, "allowed_cwd_dirs_json", "TEXT")


def _add_column_if_missing(
    connection,
    table_name: str,
    columns: set[str],
    name: str,
    column_type: str,
) -> None:
    if name in columns:
        return
    connection.exec_driver_sql(f"ALTER TABLE {table_name} ADD COLUMN {name} {column_type}")
