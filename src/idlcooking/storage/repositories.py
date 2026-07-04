import json
import sqlite3
from datetime import time

from idlcooking.application.planning import GeneratedPlan
from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    NutritionGoal,
    UserProfile,
)
from idlcooking.domain.schedule import PlanningSchedule


def _json_tuple(values: tuple[str, ...]) -> str:
    return json.dumps(list(values), ensure_ascii=True)


def _tuple_from_json(value: str) -> tuple[str, ...]:
    return tuple(json.loads(value or "[]"))


def _body_metrics_to_json(metrics: BodyMetrics | None) -> str | None:
    if metrics is None:
        return None
    return json.dumps(
        {
            "height_cm": metrics.height_cm,
            "weight_kg": metrics.weight_kg,
            "age": metrics.age,
            "sex": metrics.sex,
        },
        ensure_ascii=True,
    )


def _body_metrics_from_json(value: str | None) -> BodyMetrics | None:
    if not value:
        return None
    data = json.loads(value)
    return BodyMetrics(
        height_cm=data["height_cm"],
        weight_kg=data["weight_kg"],
        age=data["age"],
        sex=data["sex"],
    )


class UserRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_telegram_user(
        self,
        telegram_user_id: int,
        *,
        language: str = "en",
        timezone: str = "Europe/Berlin",
        consent_version: str | None = None,
    ) -> int:
        self.connection.execute(
            """
            INSERT INTO users (telegram_user_id, language, timezone, consent_version)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(telegram_user_id) DO UPDATE SET
                language = excluded.language,
                timezone = excluded.timezone
            """,
            (telegram_user_id, language, timezone, consent_version),
        )
        self.connection.commit()
        row = self.connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return int(row["id"])

    def get_user_id_by_telegram_id(self, telegram_user_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT id FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return int(row["id"]) if row else None

    def delete_user(self, telegram_user_id: int) -> None:
        self.connection.execute(
            "DELETE FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        self.connection.commit()


class ProfileRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def save_profile(self, user_id: int, profile: UserProfile) -> None:
        self.connection.execute(
            """
            INSERT INTO user_profiles (
                user_id,
                household_size,
                cooking_effort_minutes,
                allergies_json,
                hard_restrictions_json,
                disliked_ingredients_json,
                favorite_tags_json,
                activity_level,
                nutrition_goal,
                body_metrics_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                household_size = excluded.household_size,
                cooking_effort_minutes = excluded.cooking_effort_minutes,
                allergies_json = excluded.allergies_json,
                hard_restrictions_json = excluded.hard_restrictions_json,
                disliked_ingredients_json = excluded.disliked_ingredients_json,
                favorite_tags_json = excluded.favorite_tags_json,
                activity_level = excluded.activity_level,
                nutrition_goal = excluded.nutrition_goal,
                body_metrics_json = excluded.body_metrics_json,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                profile.household_size,
                profile.cooking_effort_minutes,
                _json_tuple(profile.allergies),
                _json_tuple(profile.hard_restrictions),
                _json_tuple(profile.disliked_ingredients),
                _json_tuple(profile.favorite_tags),
                profile.activity_level.value,
                profile.nutrition_goal.value,
                _body_metrics_to_json(profile.body_metrics),
            ),
        )
        self.connection.commit()

    def get_profile(self, user_id: int) -> UserProfile | None:
        row = self.connection.execute(
            "SELECT * FROM user_profiles WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        return UserProfile(
            household_size=row["household_size"],
            cooking_effort_minutes=row["cooking_effort_minutes"],
            allergies=_tuple_from_json(row["allergies_json"]),
            hard_restrictions=_tuple_from_json(row["hard_restrictions_json"]),
            disliked_ingredients=_tuple_from_json(row["disliked_ingredients_json"]),
            favorite_tags=_tuple_from_json(row["favorite_tags_json"]),
            activity_level=ActivityLevel(row["activity_level"]),
            nutrition_goal=NutritionGoal(row["nutrition_goal"]),
            body_metrics=_body_metrics_from_json(row["body_metrics_json"]),
        )


class ScheduleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def save_schedule(self, user_id: int, schedule: PlanningSchedule) -> None:
        self.connection.execute(
            """
            INSERT INTO planning_schedules (user_id, weekday, at_time, timezone, enabled, updated_at)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                weekday = excluded.weekday,
                at_time = excluded.at_time,
                timezone = excluded.timezone,
                enabled = excluded.enabled,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                user_id,
                schedule.weekday,
                schedule.at_time.strftime("%H:%M"),
                schedule.timezone,
                int(schedule.enabled),
            ),
        )
        self.connection.commit()

    def get_schedule(self, user_id: int) -> PlanningSchedule | None:
        row = self.connection.execute(
            "SELECT * FROM planning_schedules WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        if row is None:
            return None

        hour, minute = row["at_time"].split(":", maxsplit=1)
        return PlanningSchedule(
            weekday=row["weekday"],
            at_time=time(hour=int(hour), minute=int(minute)),
            timezone=row["timezone"],
            enabled=bool(row["enabled"]),
        )


class PlanningCycleRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def save_generated_plan(self, user_id: int, plan: GeneratedPlan) -> int:
        cursor = self.connection.execute(
            "INSERT INTO planning_cycles (user_id, status) VALUES (?, 'generated')",
            (user_id,),
        )
        planning_cycle_id = int(cursor.lastrowid)

        self.connection.executemany(
            """
            INSERT INTO menu_items (
                planning_cycle_id,
                day_index,
                meal_type,
                title,
                source_url,
                active_time_minutes,
                score,
                reason,
                ingredients_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    planning_cycle_id,
                    item.day_index,
                    item.meal_type.value,
                    item.recipe.title,
                    item.recipe.source_url,
                    item.recipe.active_time_minutes,
                    item.score,
                    item.reason,
                    _json_tuple(item.recipe.ingredients),
                )
                for item in plan.menu
            ],
        )
        self.connection.executemany(
            """
            INSERT INTO shopping_list_items (
                planning_cycle_id,
                name,
                category,
                already_have,
                optional
            )
            VALUES (?, ?, ?, ?, ?)
            """,
            [
                (
                    planning_cycle_id,
                    item.name,
                    item.category,
                    int(item.already_have),
                    int(item.optional),
                )
                for item in plan.shopping_list
            ],
        )
        self.connection.commit()
        return planning_cycle_id

    def get_latest_cycle_summary(self, user_id: int) -> dict[str, int | str] | None:
        row = self.connection.execute(
            """
            SELECT
                planning_cycles.id,
                planning_cycles.status,
                COUNT(DISTINCT menu_items.id) AS menu_count,
                COUNT(DISTINCT shopping_list_items.id) AS shopping_count
            FROM planning_cycles
            LEFT JOIN menu_items ON menu_items.planning_cycle_id = planning_cycles.id
            LEFT JOIN shopping_list_items
                ON shopping_list_items.planning_cycle_id = planning_cycles.id
            WHERE planning_cycles.user_id = ?
            GROUP BY planning_cycles.id
            ORDER BY planning_cycles.id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "status": row["status"],
            "menu_count": int(row["menu_count"]),
            "shopping_count": int(row["shopping_count"]),
        }
