import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_user_id INTEGER NOT NULL UNIQUE,
    language TEXT NOT NULL DEFAULT 'en',
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
    budget_level TEXT NOT NULL DEFAULT 'moderate',
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

CREATE TABLE IF NOT EXISTS planning_cycles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'generated',
    generated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS menu_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planning_cycle_id INTEGER NOT NULL,
    day_index INTEGER NOT NULL,
    meal_type TEXT NOT NULL,
    title TEXT NOT NULL,
    source_url TEXT NOT NULL,
    active_time_minutes INTEGER NOT NULL,
    score REAL NOT NULL,
    reason TEXT NOT NULL,
    ingredients_json TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (planning_cycle_id) REFERENCES planning_cycles (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS shopping_list_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    planning_cycle_id INTEGER NOT NULL,
    name TEXT NOT NULL,
    quantity TEXT NOT NULL DEFAULT '',
    category TEXT NOT NULL DEFAULT 'other',
    already_have INTEGER NOT NULL DEFAULT 0,
    optional INTEGER NOT NULL DEFAULT 0,
    checked INTEGER NOT NULL DEFAULT 0,
    FOREIGN KEY (planning_cycle_id) REFERENCES planning_cycles (id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS recipes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_url TEXT NOT NULL UNIQUE,
    title TEXT NOT NULL,
    ingredients_json TEXT NOT NULL DEFAULT '[]',
    active_time_minutes INTEGER NOT NULL DEFAULT 20,
    tags_json TEXT NOT NULL DEFAULT '[]',
    protein_grams INTEGER,
    steps_summary TEXT NOT NULL DEFAULT '',
    fetched_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    planning_cycle_id INTEGER NOT NULL,
    recipe_source_url TEXT NOT NULL,
    recipe_title TEXT NOT NULL,
    cooked_status TEXT NOT NULL DEFAULT 'cooked',
    rating TEXT NOT NULL DEFAULT 'neutral',
    effort_feedback TEXT,
    cost_feedback TEXT,
    notes TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users (id) ON DELETE CASCADE,
    FOREIGN KEY (planning_cycle_id) REFERENCES planning_cycles (id) ON DELETE CASCADE
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
