import json
import sqlite3
from datetime import time

from idlcooking.application.planning import GeneratedPlan
from idlcooking.domain.feedback import Rating, RecipeFeedback
from idlcooking.domain.planning import RecipeCandidate
from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    BudgetLevel,
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

    def get_language(self, telegram_user_id: int) -> str:
        row = self.connection.execute(
            "SELECT language FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return row["language"] if row else "en"

    def delete_user(self, telegram_user_id: int) -> None:
        self.connection.execute(
            "DELETE FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        )
        self.connection.commit()

    def get_consent_version(self, telegram_user_id: int) -> str | None:
        row = self.connection.execute(
            "SELECT consent_version FROM users WHERE telegram_user_id = ?",
            (telegram_user_id,),
        ).fetchone()
        return row["consent_version"] if row else None

    def record_consent(self, telegram_user_id: int, consent_version: str) -> None:
        self.connection.execute(
            "UPDATE users SET consent_version = ? WHERE telegram_user_id = ?",
            (consent_version, telegram_user_id),
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
                budget_level,
                activity_level,
                nutrition_goal,
                body_metrics_json,
                updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                household_size = excluded.household_size,
                cooking_effort_minutes = excluded.cooking_effort_minutes,
                allergies_json = excluded.allergies_json,
                hard_restrictions_json = excluded.hard_restrictions_json,
                disliked_ingredients_json = excluded.disliked_ingredients_json,
                favorite_tags_json = excluded.favorite_tags_json,
                budget_level = excluded.budget_level,
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
                profile.budget_level.value,
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
            budget_level=BudgetLevel(row["budget_level"]),
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
            INSERT INTO planning_schedules
                (user_id, weekday, at_time, timezone, enabled, updated_at)
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

    def get_enabled_schedules_with_telegram_ids(
        self,
    ) -> list[tuple[int, PlanningSchedule, str | None]]:
        rows = self.connection.execute(
            """
            SELECT
                users.telegram_user_id AS telegram_user_id,
                planning_schedules.weekday AS weekday,
                planning_schedules.at_time AS at_time,
                planning_schedules.timezone AS timezone,
                planning_schedules.last_triggered_at AS last_triggered_at
            FROM planning_schedules
            JOIN users ON users.id = planning_schedules.user_id
            WHERE planning_schedules.enabled = 1
            """
        ).fetchall()
        results = []
        for row in rows:
            hour, minute = row["at_time"].split(":", maxsplit=1)
            schedule = PlanningSchedule(
                weekday=row["weekday"],
                at_time=time(hour=int(hour), minute=int(minute)),
                timezone=row["timezone"],
            )
            results.append((int(row["telegram_user_id"]), schedule, row["last_triggered_at"]))
        return results

    def mark_schedule_triggered(self, telegram_user_id: int, occurrence_iso: str) -> None:
        self.connection.execute(
            """
            UPDATE planning_schedules
            SET last_triggered_at = ?
            WHERE user_id = (SELECT id FROM users WHERE telegram_user_id = ?)
            """,
            (occurrence_iso, telegram_user_id),
        )
        self.connection.commit()


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
                ingredients_json,
                steps_summary
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    item.recipe.steps_summary,
                )
                for item in plan.menu
            ],
        )
        self.connection.executemany(
            """
            INSERT INTO shopping_list_items (
                planning_cycle_id,
                name,
                quantity,
                category,
                already_have,
                optional
            )
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    planning_cycle_id,
                    item.name,
                    item.quantity,
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

    def get_latest_cycle_id(self, user_id: int) -> int | None:
        row = self.connection.execute(
            "SELECT id FROM planning_cycles WHERE user_id = ? ORDER BY id DESC LIMIT 1",
            (user_id,),
        ).fetchone()
        return int(row["id"]) if row else None

    def get_latest_cycle(self, user_id: int) -> dict[str, object] | None:
        row = self.connection.execute(
            """
            SELECT id, status, generated_at, accepted_at
            FROM planning_cycles
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 1
            """,
            (user_id,),
        ).fetchone()
        if row is None:
            return None
        return {
            "id": int(row["id"]),
            "status": row["status"],
            "generated_at": row["generated_at"],
            "accepted_at": row["accepted_at"],
        }

    def get_menu_day_count(self, planning_cycle_id: int) -> int:
        """Number of days the plan covers, derived from the persisted menu items."""
        row = self.connection.execute(
            "SELECT MAX(day_index) AS max_day FROM menu_items WHERE planning_cycle_id = ?",
            (planning_cycle_id,),
        ).fetchone()
        if row is None or row["max_day"] is None:
            return 0
        return int(row["max_day"]) + 1

    def get_latest_cycle_menu_items(
        self, user_id: int
    ) -> tuple[int, list[dict[str, str]]] | None:
        planning_cycle_id = self.get_latest_cycle_id(user_id)
        if planning_cycle_id is None:
            return None

        item_rows = self.connection.execute(
            """
            SELECT DISTINCT title, source_url
            FROM menu_items
            WHERE planning_cycle_id = ?
            ORDER BY id ASC
            """,
            (planning_cycle_id,),
        ).fetchall()
        items = [{"title": row["title"], "source_url": row["source_url"]} for row in item_rows]
        return planning_cycle_id, items

    def get_menu_items_by_day(self, planning_cycle_id: int) -> dict[int, list[dict[str, object]]]:
        rows = self.connection.execute(
            """
            SELECT
                day_index,
                meal_type,
                title,
                source_url,
                active_time_minutes,
                ingredients_json,
                steps_summary
            FROM menu_items
            WHERE planning_cycle_id = ?
            ORDER BY id ASC
            """,
            (planning_cycle_id,),
        ).fetchall()
        grouped: dict[int, list[dict[str, object]]] = {}
        for row in rows:
            grouped.setdefault(row["day_index"], []).append(
                {
                    "meal_type": row["meal_type"],
                    "title": row["title"],
                    "source_url": row["source_url"],
                    "active_time_minutes": row["active_time_minutes"],
                    "ingredients": _tuple_from_json(row["ingredients_json"]),
                    "steps_summary": row["steps_summary"],
                }
            )
        return grouped

    def mark_cycle_status(self, planning_cycle_id: int, status: str) -> None:
        # Stamp accepted_at the first time a cycle is accepted so "day X of the plan"
        # can be measured from acceptance (issue #35). COALESCE keeps the original
        # timestamp if the same cycle is somehow accepted twice.
        if status == "accepted":
            self.connection.execute(
                """
                UPDATE planning_cycles
                SET status = ?, accepted_at = COALESCE(accepted_at, CURRENT_TIMESTAMP)
                WHERE id = ?
                """,
                (status, planning_cycle_id),
            )
        else:
            self.connection.execute(
                "UPDATE planning_cycles SET status = ? WHERE id = ?",
                (status, planning_cycle_id),
            )
        self.connection.commit()

    def get_shopping_list_lines(self, planning_cycle_id: int) -> list[dict[str, object]]:
        rows = self.connection.execute(
            """
            SELECT name, quantity, category, already_have, optional, checked
            FROM shopping_list_items
            WHERE planning_cycle_id = ?
            ORDER BY category ASC, already_have ASC, name ASC
            """,
            (planning_cycle_id,),
        ).fetchall()
        return [
            {
                "name": row["name"],
                "quantity": row["quantity"],
                "category": row["category"],
                "already_have": bool(row["already_have"]),
                "optional": bool(row["optional"]),
                "checked": bool(row["checked"]),
            }
            for row in rows
        ]


class RecipeRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def upsert_recipe(self, recipe: RecipeCandidate) -> None:
        self.connection.execute(
            """
            INSERT INTO recipes (
                source_url,
                title,
                ingredients_json,
                active_time_minutes,
                tags_json,
                protein_grams,
                steps_summary,
                fetched_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(source_url) DO UPDATE SET
                title = excluded.title,
                ingredients_json = excluded.ingredients_json,
                active_time_minutes = excluded.active_time_minutes,
                tags_json = excluded.tags_json,
                protein_grams = excluded.protein_grams,
                steps_summary = excluded.steps_summary,
                fetched_at = CURRENT_TIMESTAMP
            """,
            (
                recipe.source_url,
                recipe.title,
                _json_tuple(recipe.ingredients),
                recipe.active_time_minutes,
                _json_tuple(recipe.tags),
                recipe.protein_grams,
                recipe.steps_summary,
            ),
        )
        self.connection.commit()

    def get_all_recipes(self) -> list[RecipeCandidate]:
        rows = self.connection.execute(
            "SELECT * FROM recipes ORDER BY id ASC",
        ).fetchall()
        return [
            RecipeCandidate(
                title=row["title"],
                source_url=row["source_url"],
                ingredients=_tuple_from_json(row["ingredients_json"]),
                active_time_minutes=row["active_time_minutes"],
                tags=_tuple_from_json(row["tags_json"]),
                protein_grams=row["protein_grams"],
                steps_summary=row["steps_summary"],
            )
            for row in rows
        ]


class FeedbackRepository:
    def __init__(self, connection: sqlite3.Connection) -> None:
        self.connection = connection

    def save_feedback(
        self, user_id: int, planning_cycle_id: int, feedback: RecipeFeedback
    ) -> None:
        self.connection.execute(
            """
            INSERT INTO feedback (
                user_id,
                planning_cycle_id,
                recipe_source_url,
                recipe_title,
                cooked_status,
                rating,
                effort_feedback,
                cost_feedback,
                notes
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                planning_cycle_id,
                feedback.recipe_source_url,
                feedback.recipe_title,
                feedback.cooked_status.value,
                feedback.rating.value,
                feedback.effort_feedback,
                feedback.cost_feedback,
                feedback.notes,
            ),
        )
        self.connection.commit()

    def get_recipe_urls_by_rating(self, user_id: int, rating: Rating) -> frozenset[str]:
        rows = self.connection.execute(
            "SELECT DISTINCT recipe_source_url FROM feedback WHERE user_id = ? AND rating = ?",
            (user_id, rating.value),
        ).fetchall()
        return frozenset(row["recipe_source_url"] for row in rows)
