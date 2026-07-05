import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


def _table_exists(connection: sqlite3.Connection, table: str) -> bool:
    row = connection.execute(
        "SELECT name FROM sqlite_master WHERE type = 'table' AND name = ?", (table,)
    ).fetchone()
    return row is not None


def _column_exists(connection: sqlite3.Connection, table: str, column: str) -> bool:
    rows = connection.execute(f"PRAGMA table_info({table})").fetchall()
    return any(row["name"] == column for row in rows)


@dataclass(frozen=True)
class Migration:
    """A single, idempotent schema change applied in order by `initialize_database`."""

    description: str
    sql: str
    is_applied: Callable[[sqlite3.Connection], bool]


# Ordered from the very first schema this project shipped to the current one. Each
# entry backfills a real change from this project's history (see issue #17), so an
# existing local database self-heals to the current schema instead of erroring with
# "no such column"/"no such table" on startup.
MIGRATIONS: tuple[Migration, ...] = (
    Migration(
        description="create core tables (users, user_profiles, planning_schedules)",
        sql="""
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
        """,
        is_applied=lambda c: _table_exists(c, "users"),
    ),
    Migration(
        description="create planning_cycles, menu_items, shopping_list_items",
        sql="""
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
                category TEXT NOT NULL DEFAULT 'other',
                already_have INTEGER NOT NULL DEFAULT 0,
                optional INTEGER NOT NULL DEFAULT 0,
                checked INTEGER NOT NULL DEFAULT 0,
                FOREIGN KEY (planning_cycle_id) REFERENCES planning_cycles (id) ON DELETE CASCADE
            );
        """,
        is_applied=lambda c: _table_exists(c, "planning_cycles"),
    ),
    Migration(
        description="add user_profiles.budget_level",
        sql="ALTER TABLE user_profiles ADD COLUMN budget_level TEXT NOT NULL DEFAULT 'moderate';",
        is_applied=lambda c: _column_exists(c, "user_profiles", "budget_level"),
    ),
    Migration(
        description="create recipes table",
        sql="""
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
        """,
        is_applied=lambda c: _table_exists(c, "recipes"),
    ),
    Migration(
        description="create feedback table",
        sql="""
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
        """,
        is_applied=lambda c: _table_exists(c, "feedback"),
    ),
    Migration(
        description="add shopping_list_items.quantity",
        sql="ALTER TABLE shopping_list_items ADD COLUMN quantity TEXT NOT NULL DEFAULT '';",
        is_applied=lambda c: _column_exists(c, "shopping_list_items", "quantity"),
    ),
    Migration(
        description="add planning_schedules.last_triggered_at",
        sql="ALTER TABLE planning_schedules ADD COLUMN last_triggered_at TEXT;",
        is_applied=lambda c: _column_exists(c, "planning_schedules", "last_triggered_at"),
    ),
    Migration(
        description="add menu_items.steps_summary",
        sql="ALTER TABLE menu_items ADD COLUMN steps_summary TEXT NOT NULL DEFAULT '';",
        is_applied=lambda c: _column_exists(c, "menu_items", "steps_summary"),
    ),
)


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
    """Bring the database up to the current schema.

    Applies each migration in `MIGRATIONS` that hasn't already run, based on the
    actual tables/columns present rather than solely on `PRAGMA user_version`. This
    lets a database created before migrations existed (whose `user_version` is 0)
    self-heal without erroring on already-applied steps.
    """
    for migration in MIGRATIONS:
        if migration.is_applied(connection):
            continue
        connection.executescript(migration.sql)

    connection.execute(f"PRAGMA user_version = {len(MIGRATIONS)}")
    connection.commit()
