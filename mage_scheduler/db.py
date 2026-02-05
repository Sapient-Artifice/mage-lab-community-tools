from __future__ import annotations

from pathlib import Path
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

DB_PATH = Path(__file__).resolve().parent / "mage_scheduler.db"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def init_db() -> None:
    # Import models to register them with SQLAlchemy
    from models import TaskRequest, Action, Settings  # noqa: F401

    Base.metadata.create_all(bind=engine)
    _migrate_schema()


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
