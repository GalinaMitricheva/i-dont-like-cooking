import logging
from dataclasses import dataclass
from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

from idlcooking.application.planning import SEED_RECIPES, PlanningService
from idlcooking.domain.feedback import Rating, RecipeFeedback
from idlcooking.domain.planning import InventoryItem, RecipeCandidate
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.schedule import PlanningSchedule, weekday_name
from idlcooking.services.recipe_discovery import RecipeDiscoveryService
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    FeedbackRepository,
    PlanningCycleRepository,
    ProfileRepository,
    RecipeRepository,
    ScheduleRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

CONSENT_VERSION = "v1"

_CATEGORY_LABELS: dict[str, str] = {
    "produce": "Produce",
    "protein": "Protein",
    "dairy_and_eggs": "Dairy and eggs",
    "grains_and_bakery": "Grains and bakery",
    "pantry": "Pantry",
    "frozen": "Frozen",
    "spices_and_sauces": "Spices and sauces",
    "other": "Other",
}


def _format_shopping_list(
    items: list[tuple[str, str, str, bool, bool]],
) -> tuple[str, ...]:
    """Format (name, quantity, category, already_have, optional) tuples, grouped by category.

    Items are expected to already be sorted by category (see build_shopping_list and
    PlanningCycleRepository.get_shopping_list_lines), so a category header is only
    emitted when the category changes from one item to the next.
    """
    lines: list[str] = []
    current_category: str | None = None
    for name, quantity, category, already_have, optional in items:
        if category != current_category:
            if current_category is not None:
                lines.append("")
            current_category = category
            lines.append(f"{_CATEGORY_LABELS.get(category, category.title())}:")
        prefix = f"{quantity} " if quantity else ""
        if already_have:
            suffix = " (already have)"
        elif optional:
            suffix = " (optional)"
        else:
            suffix = ""
        lines.append(f"- {prefix}{name}{suffix}")
    return tuple(lines)


@dataclass(frozen=True)
class TelegramPlanSummary:
    planning_cycle_id: int
    menu_lines: tuple[str, ...]
    shopping_lines: tuple[str, ...]


@dataclass(frozen=True)
class TelegramCurrentPlanStatus:
    menu_lines: tuple[str, ...]
    current_day: int
    total_days: int
    plan_complete: bool
    next_planning_at: str | None


@dataclass(frozen=True)
class TelegramProfileSummary:
    household_size: int
    cooking_effort_minutes: int
    planning_weekday: int
    planning_time: str
    timezone: str


@dataclass(frozen=True)
class TelegramScheduleSummary:
    weekday: int
    weekday_name: str
    at_time: str
    timezone: str


@dataclass(frozen=True)
class TelegramFeedbackMenuItem:
    title: str
    source_url: str


@dataclass(frozen=True)
class TelegramRecipeDetail:
    meal_type: str
    title: str
    source_url: str
    active_time_minutes: int
    ingredients: tuple[str, ...]
    steps_summary: str


class TelegramPlanningFacade:
    def __init__(
        self,
        database_url: str,
        recipe_discovery: RecipeDiscoveryService | None = None,
    ) -> None:
        self.connection = connect(database_url)
        initialize_database(self.connection)
        self.users = UserRepository(self.connection)
        self.profiles = ProfileRepository(self.connection)
        self.schedules = ScheduleRepository(self.connection)
        self.cycles = PlanningCycleRepository(self.connection)
        self.recipe_catalog = RecipeRepository(self.connection)
        self.recipe_discovery = recipe_discovery or RecipeDiscoveryService()
        self.feedback = FeedbackRepository(self.connection)

    def ensure_user_defaults(
        self,
        telegram_user_id: int,
        *,
        language: str = "en",
        timezone: str = "Europe/Berlin",
    ) -> int:
        user_id = self.users.upsert_telegram_user(
            telegram_user_id,
            language=language,
            timezone=timezone,
        )
        if self.profiles.get_profile(user_id) is None:
            self.profiles.save_profile(user_id, UserProfile())
        if self.schedules.get_schedule(user_id) is None:
            schedule = PlanningSchedule(timezone=timezone)
            self.schedules.save_schedule(user_id, schedule)
            self._seed_schedule_as_up_to_date(telegram_user_id, schedule)
        return user_id

    def _seed_schedule_as_up_to_date(
        self, telegram_user_id: int, schedule: PlanningSchedule
    ) -> None:
        """Mark a schedule as already covered through now.

        Without this, a freshly created or just-changed schedule with no
        last_triggered_at would look "due" for whatever occurrence most
        recently passed, firing a plan immediately instead of waiting for the
        user's actual next scheduled day/time.
        """
        now = datetime.now(UTC)
        occurrence = schedule.latest_occurrence_before_or_at(now)
        self.schedules.mark_schedule_triggered(telegram_user_id, occurrence.isoformat())

    def delete_user_data(self, telegram_user_id: int) -> None:
        self.users.delete_user(telegram_user_id)

    def has_user_consented(self, telegram_user_id: int) -> bool:
        return self.users.get_consent_version(telegram_user_id) == CONSENT_VERSION

    def record_consent(
        self,
        telegram_user_id: int,
        *,
        language: str = "en",
        timezone: str = "Europe/Berlin",
    ) -> int:
        user_id = self.ensure_user_defaults(telegram_user_id, language=language, timezone=timezone)
        self.users.record_consent(telegram_user_id, CONSENT_VERSION)
        return user_id

    def save_profile(self, telegram_user_id: int, profile: UserProfile) -> None:
        user_id = self.ensure_user_defaults(telegram_user_id)
        self.profiles.save_profile(user_id, profile)

    def get_profile_summary(self, telegram_user_id: int) -> TelegramProfileSummary:
        user_id = self.ensure_user_defaults(telegram_user_id)
        profile = self.profiles.get_profile(user_id) or UserProfile()
        schedule = self.schedules.get_schedule(user_id) or PlanningSchedule()
        return TelegramProfileSummary(
            household_size=profile.household_size,
            cooking_effort_minutes=profile.cooking_effort_minutes,
            planning_weekday=schedule.weekday,
            planning_time=schedule.at_time.strftime("%H:%M"),
            timezone=schedule.timezone,
        )

    def get_schedule_summary(self, telegram_user_id: int) -> TelegramScheduleSummary:
        user_id = self.ensure_user_defaults(telegram_user_id)
        schedule = self.schedules.get_schedule(user_id) or PlanningSchedule()
        return TelegramScheduleSummary(
            weekday=schedule.weekday,
            weekday_name=weekday_name(schedule.weekday),
            at_time=schedule.at_time.strftime("%H:%M"),
            timezone=schedule.timezone,
        )

    def update_schedule(
        self,
        telegram_user_id: int,
        *,
        weekday: int,
        at_time: time,
        timezone: str,
    ) -> TelegramScheduleSummary:
        user_id = self.ensure_user_defaults(telegram_user_id, timezone=timezone)
        schedule = PlanningSchedule(weekday=weekday, at_time=at_time, timezone=timezone)
        self.schedules.save_schedule(user_id, schedule)
        self._seed_schedule_as_up_to_date(telegram_user_id, schedule)
        return self.get_schedule_summary(telegram_user_id)

    def get_due_telegram_user_ids(self, now: datetime) -> list[int]:
        due: list[int] = []
        for telegram_user_id, schedule, last_triggered_at in (
            self.schedules.get_enabled_schedules_with_telegram_ids()
        ):
            occurrence = schedule.latest_occurrence_before_or_at(now)
            if last_triggered_at and datetime.fromisoformat(last_triggered_at) >= occurrence:
                continue
            due.append(telegram_user_id)
        return due

    def mark_schedule_triggered(self, telegram_user_id: int, now: datetime) -> None:
        user_id = self.ensure_user_defaults(telegram_user_id)
        schedule = self.schedules.get_schedule(user_id) or PlanningSchedule()
        occurrence = schedule.latest_occurrence_before_or_at(now)
        self.schedules.mark_schedule_triggered(telegram_user_id, occurrence.isoformat())

    def get_language(self, telegram_user_id: int) -> str:
        return self.users.get_language(telegram_user_id)

    def _recipe_pool(self) -> tuple[RecipeCandidate, ...]:
        cached = self.recipe_catalog.get_all_recipes()
        if cached:
            return tuple(cached)

        try:
            discovered = self.recipe_discovery.discover()
        except Exception:
            logger.warning("Recipe discovery failed, falling back to seed recipes", exc_info=True)
            discovered = []

        if not discovered:
            return SEED_RECIPES

        for recipe in discovered:
            self.recipe_catalog.upsert_recipe(recipe)
        return tuple(discovered)

    def generate_plan_from_text_inventory(
        self,
        telegram_user_id: int,
        inventory_text: str = "",
        include_dinner_leftovers: bool = True,
        include_breakfast: bool = False,
        days: int = 7,
    ) -> TelegramPlanSummary:
        user_id = self.ensure_user_defaults(telegram_user_id)
        profile = self.profiles.get_profile(user_id) or UserProfile()
        inventory = tuple(
            InventoryItem(name=name.strip())
            for name in inventory_text.replace(";", ",").split(",")
            if name.strip()
        )
        planning = PlanningService(recipes=self._recipe_pool())
        generated = planning.generate_weekly_plan(
            profile,
            inventory,
            days=days,
            include_dinner_leftovers=include_dinner_leftovers,
            include_breakfast=include_breakfast,
            liked_recipe_urls=self.feedback.get_recipe_urls_by_rating(user_id, Rating.LIKED),
            disliked_recipe_urls=self.feedback.get_recipe_urls_by_rating(user_id, Rating.DISLIKED),
        )
        planning_cycle_id = self.cycles.save_generated_plan(user_id, generated)

        menu_lines = tuple(
            f"Day {item.day_index + 1} ({item.meal_type.value}): {item.recipe.title} "
            f"({item.recipe.active_time_minutes} min)"
            for item in generated.menu
        )
        shopping_lines = _format_shopping_list(
            [
                (item.name, item.quantity, item.category, item.already_have, item.optional)
                for item in generated.shopping_list
            ]
        )
        return TelegramPlanSummary(
            planning_cycle_id=planning_cycle_id,
            menu_lines=menu_lines,
            shopping_lines=shopping_lines,
        )

    def get_latest_cycle_feedback_targets(
        self, telegram_user_id: int
    ) -> tuple[int, list[TelegramFeedbackMenuItem]] | None:
        user_id = self.ensure_user_defaults(telegram_user_id)
        result = self.cycles.get_latest_cycle_menu_items(user_id)
        if result is None:
            return None
        planning_cycle_id, items = result
        return planning_cycle_id, [
            TelegramFeedbackMenuItem(title=item["title"], source_url=item["source_url"])
            for item in items
        ]

    def record_feedback(
        self,
        telegram_user_id: int,
        planning_cycle_id: int,
        feedback: RecipeFeedback,
    ) -> None:
        user_id = self.ensure_user_defaults(telegram_user_id)
        self.feedback.save_feedback(user_id, planning_cycle_id, feedback)

    def accept_latest_cycle(self, telegram_user_id: int) -> bool:
        user_id = self.ensure_user_defaults(telegram_user_id)
        cycle_id = self.cycles.get_latest_cycle_id(user_id)
        if cycle_id is None:
            return False
        self.cycles.mark_cycle_status(cycle_id, "accepted")
        return True

    def is_latest_cycle_accepted(self, telegram_user_id: int) -> bool:
        user_id = self.ensure_user_defaults(telegram_user_id)
        summary = self.cycles.get_latest_cycle_summary(user_id)
        return summary is not None and summary["status"] == "accepted"

    def get_current_plan_status(
        self, telegram_user_id: int, now: datetime | None = None
    ) -> TelegramCurrentPlanStatus | None:
        """Status of the user's active (accepted) plan for the /currentplan command.

        Returns None when there is no accepted plan yet, so the caller can steer the
        user to /plan. "Current day" is counted from acceptance (issue #35), measured
        in the schedule's timezone so day boundaries match the user's local calendar.
        """
        now = now or datetime.now(UTC)
        user_id = self.ensure_user_defaults(telegram_user_id)
        cycle = self.cycles.get_latest_cycle(user_id)
        if cycle is None or cycle["status"] != "accepted":
            return None

        summary = self.get_latest_plan_summary(telegram_user_id)
        menu_lines = summary.menu_lines if summary else ()
        total_days = self.cycles.get_menu_day_count(int(cycle["id"]))

        schedule = self.schedules.get_schedule(user_id) or PlanningSchedule()
        zone = ZoneInfo(schedule.timezone)
        started = cycle["accepted_at"] or cycle["generated_at"]
        current_day = 1
        if started:
            # SQLite CURRENT_TIMESTAMP is naive UTC ("YYYY-MM-DD HH:MM:SS").
            started_date = (
                datetime.fromisoformat(str(started)).replace(tzinfo=UTC).astimezone(zone).date()
            )
            today = now.astimezone(zone).date()
            current_day = max(1, (today - started_date).days + 1)

        plan_complete = total_days > 0 and current_day > total_days
        displayed_day = min(current_day, total_days) if total_days else current_day

        next_run = schedule.next_run_after(now)
        next_planning_at = (
            f"{next_run.strftime('%A, %d %b %H:%M')} ({schedule.timezone})"
            if next_run is not None
            else None
        )

        return TelegramCurrentPlanStatus(
            menu_lines=menu_lines,
            current_day=displayed_day,
            total_days=total_days,
            plan_complete=plan_complete,
            next_planning_at=next_planning_at,
        )

    def get_latest_shopping_list_lines(self, telegram_user_id: int) -> tuple[str, ...]:
        user_id = self.ensure_user_defaults(telegram_user_id)
        cycle_id = self.cycles.get_latest_cycle_id(user_id)
        if cycle_id is None:
            return ()
        items = self.cycles.get_shopping_list_lines(cycle_id)
        return _format_shopping_list(
            [
                (
                    item["name"],
                    item["quantity"],
                    item["category"],
                    item["already_have"],
                    item["optional"],
                )
                for item in items
            ]
        )

    def get_latest_recipe_details_by_day(
        self, telegram_user_id: int
    ) -> list[list[TelegramRecipeDetail]]:
        user_id = self.ensure_user_defaults(telegram_user_id)
        cycle_id = self.cycles.get_latest_cycle_id(user_id)
        if cycle_id is None:
            return []
        grouped = self.cycles.get_menu_items_by_day(cycle_id)
        if not grouped:
            return []
        return [
            [
                TelegramRecipeDetail(
                    meal_type=item["meal_type"],
                    title=item["title"],
                    source_url=item["source_url"],
                    active_time_minutes=item["active_time_minutes"],
                    ingredients=item["ingredients"],
                    steps_summary=item["steps_summary"],
                )
                for item in grouped.get(day, [])
            ]
            for day in range(max(grouped) + 1)
        ]

    def get_latest_plan_summary(self, telegram_user_id: int) -> TelegramPlanSummary | None:
        """Rebuild the plan summary from persisted data, without regenerating a new cycle."""
        user_id = self.ensure_user_defaults(telegram_user_id)
        cycle_id = self.cycles.get_latest_cycle_id(user_id)
        if cycle_id is None:
            return None
        days = self.get_latest_recipe_details_by_day(telegram_user_id)
        menu_lines = tuple(
            f"Day {day_index + 1} ({item.meal_type}): {item.title} ({item.active_time_minutes} min)"
            for day_index, items in enumerate(days)
            for item in items
        )
        return TelegramPlanSummary(
            planning_cycle_id=cycle_id,
            menu_lines=menu_lines,
            shopping_lines=self.get_latest_shopping_list_lines(telegram_user_id),
        )
