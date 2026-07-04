from dataclasses import dataclass
from datetime import time

from idlcooking.application.planning import PlanningService
from idlcooking.domain.planning import InventoryItem
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.schedule import PlanningSchedule, weekday_name
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    PlanningCycleRepository,
    ProfileRepository,
    ScheduleRepository,
    UserRepository,
)

CONSENT_VERSION = "v1"


@dataclass(frozen=True)
class TelegramPlanSummary:
    planning_cycle_id: int
    menu_lines: tuple[str, ...]
    shopping_lines: tuple[str, ...]


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


class TelegramPlanningFacade:
    def __init__(self, database_url: str) -> None:
        self.connection = connect(database_url)
        initialize_database(self.connection)
        self.users = UserRepository(self.connection)
        self.profiles = ProfileRepository(self.connection)
        self.schedules = ScheduleRepository(self.connection)
        self.cycles = PlanningCycleRepository(self.connection)
        self.planning = PlanningService()

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
            self.schedules.save_schedule(user_id, PlanningSchedule(timezone=timezone))
        return user_id

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
        self.schedules.save_schedule(
            user_id,
            PlanningSchedule(weekday=weekday, at_time=at_time, timezone=timezone),
        )
        return self.get_schedule_summary(telegram_user_id)

    def generate_plan_from_text_inventory(
        self,
        telegram_user_id: int,
        inventory_text: str = "",
        include_lunch_leftovers: bool = True,
    ) -> TelegramPlanSummary:
        user_id = self.ensure_user_defaults(telegram_user_id)
        profile = self.profiles.get_profile(user_id) or UserProfile()
        inventory = tuple(
            InventoryItem(name=name.strip())
            for name in inventory_text.replace(";", ",").split(",")
            if name.strip()
        )
        generated = self.planning.generate_weekly_plan(
            profile, inventory, days=7, include_lunch_leftovers=include_lunch_leftovers
        )
        planning_cycle_id = self.cycles.save_generated_plan(user_id, generated)

        menu_lines = tuple(
            f"Day {item.day_index + 1} ({item.meal_type.value}): {item.recipe.title} "
            f"({item.recipe.active_time_minutes} min)"
            for item in generated.menu
        )
        shopping_lines = tuple(
            f"- {item.name}{' (already have)' if item.already_have else ''}"
            for item in generated.shopping_list
        )
        return TelegramPlanSummary(
            planning_cycle_id=planning_cycle_id,
            menu_lines=menu_lines,
            shopping_lines=shopping_lines,
        )
