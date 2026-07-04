import sqlite3
from pathlib import Path


SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    language TEXT NOT NULL DEFAULT 'ru',
    timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
    consent_version TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INTEGER PRIMARY KEY,
    household_size INTEGER NOT NULL DEFAULT 1,
    cooking_effort_minutes INTEGER NOT NULL DEFAULT 20,
    allergies_json TEXT NOT NULL DEFAULT '[]',
    hard_restrictions_json TEXT NOT NULL DEFAULT '[]',
    disliked_ingredients_json TEXT NOT NULL DEFAULT '[]',
    favorite_tags_json TEXT NOT NULL DEFAULT '[]',
    activity_level TEXT NOT NULL DEFAULT 'light',
    nutrition_goal TEXT NOT NULL DEFAULT 'maintain',
    body_metrics_json TEXT,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS planning_schedules (
    user_id INTEGER PRIMARY KEY,
    weekday INTEGER NOT NULL DEFAULT 5,
    at_time TEXT NOT NULL DEFAULT '09:00',
    timezone TEXT NOT NULL DEFAULT 'Europe/Berlin',
    enabled INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);
"""


def connect(database_url: str) -> sqlite3.Connection:
    if not database_url.startswith("sqlite:///"):
        raise ValueError("Only sqlite:/// database URLs are supported in the local MVP.")

    database_path = database_url.removeprefix("sqlite:///")
    if database_path != ":memory:":
        Path(database_path).parent.mkdir(parents=True, exist_ok=True)

    connection = sqlite3.connect(database_path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def initialize_database(connection: sqlite3.Connection) -> None:
    connection.executescript(SCHEMA_SQL)
    connection.commit()
