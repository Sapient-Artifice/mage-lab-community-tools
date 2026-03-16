from __future__ import annotations

import json
import os
from pathlib import Path
from sqlalchemy import create_engine, event, select
from sqlalchemy.orm import declarative_base, sessionmaker

# Store data outside the plugin directory so upgrades don't wipe the DB.
_data_dir = Path(os.environ.get("SCHEDULER_DATA_DIR", Path.home() / ".mage_scheduler"))
_data_dir.mkdir(parents=True, exist_ok=True)

DB_PATH = _data_dir / "mage_scheduler.db"
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
    from models import TaskRequest, Action, Settings, RecurringTask, TaskDependency  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()
    _seed_default_actions()


def _ask_assistant_command() -> str:
    """Return the canonical command for the ask_assistant action.

    Uses the venv Python that owns this installation so the path stays correct
    regardless of which machine or directory the plugin lives in.
    """
    script = Path(__file__).resolve().parent / "scripts" / "ask_assistant.py"
    venv_python = Path(__file__).resolve().parent.parent / ".venv" / "bin" / "python"
    python = str(venv_python) if venv_python.exists() else "/usr/bin/python3"
    return f"{python} {script}"


def _seed_default_actions() -> None:
    from models import Action

    command = _ask_assistant_command()
    with SessionLocal() as session:
        existing = session.execute(
            select(Action).where(Action.name == "ask_assistant")
        ).scalar_one_or_none()
        if existing is None:
            action = Action(
                name="ask_assistant",
                description="Send a scheduled message to the assistant.",
                command=command,
                allowed_env_json=json.dumps(["MESSAGE"]),
            )
            session.add(action)
        else:
            # Keep the command current — stale paths cause silent failures after
            # the plugin is moved, renamed, or reinstalled on a new machine.
            existing.command = command
        session.commit()


def _migrate_schema() -> None:
    with engine.begin() as connection:
        columns = {row[1] for row in connection.exec_driver_sql("PRAGMA table_info(task_requests)").fetchall()}
        if not columns:
            return
        _rename_column_if_exists(connection, "task_requests", columns, "celery_task_id", "job_id", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "intent_version", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "source", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "action_id", "INTEGER")
        _add_column_if_missing(connection, "task_requests", columns, "action_name", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "cwd", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "env_json", "TEXT")
        _add_column_if_missing(connection, "task_requests", columns, "notify_on_complete", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(connection, "task_requests", columns, "max_retries", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(connection, "task_requests", columns, "retry_delay", "INTEGER NOT NULL DEFAULT 60")
        _add_column_if_missing(connection, "task_requests", columns, "retry_count", "INTEGER NOT NULL DEFAULT 0")
        _add_column_if_missing(connection, "task_requests", columns, "recurring_task_id", "INTEGER")
        _add_column_if_missing(connection, "task_requests", columns, "retain_result", "INTEGER NOT NULL DEFAULT 0")

        action_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(actions)").fetchall()
        }
        if action_columns:
            _add_column_if_missing(connection, "actions", action_columns, "default_cwd", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_env_json", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_command_dirs_json", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "allowed_cwd_dirs_json", "TEXT")
            _add_column_if_missing(connection, "actions", action_columns, "max_retries", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(connection, "actions", action_columns, "retry_delay", "INTEGER NOT NULL DEFAULT 60")
            _add_column_if_missing(connection, "actions", action_columns, "retain_result", "INTEGER NOT NULL DEFAULT 0")

        settings_columns = {
            row[1] for row in connection.exec_driver_sql("PRAGMA table_info(settings)").fetchall()
        }
        if settings_columns:
            _add_column_if_missing(connection, "settings", settings_columns, "allowed_command_dirs_json", "TEXT")
            _add_column_if_missing(connection, "settings", settings_columns, "allowed_cwd_dirs_json", "TEXT")
            _add_column_if_missing(connection, "settings", settings_columns, "cleanup_enabled", "INTEGER NOT NULL DEFAULT 0")
            _add_column_if_missing(connection, "settings", settings_columns, "task_retention_days", "INTEGER NOT NULL DEFAULT 30")


def _rename_column_if_exists(
    connection,
    table_name: str,
    columns: set[str],
    old_name: str,
    new_name: str,
    column_type: str,
) -> None:
    if new_name in columns:
        return  # already renamed
    if old_name in columns:
        connection.exec_driver_sql(
            f"ALTER TABLE {table_name} RENAME COLUMN {old_name} TO {new_name}"
        )
    else:
        # Neither exists — add the new column fresh
        connection.exec_driver_sql(
            f"ALTER TABLE {table_name} ADD COLUMN {new_name} {column_type}"
        )


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
