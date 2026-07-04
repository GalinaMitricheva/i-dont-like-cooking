from dataclasses import dataclass

from idlcooking.application.planning import PlanningService
from idlcooking.domain.planning import InventoryItem
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.schedule import PlanningSchedule
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    PlanningCycleRepository,
    ProfileRepository,
    ScheduleRepository,
    UserRepository,
)


@dataclass(frozen=True)
class TelegramPlanSummary:
    planning_cycle_id: int
    menu_lines: tuple[str, ...]
    shopping_lines: tuple[str, ...]


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
        language: str = "ru",
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

    def generate_plan_from_text_inventory(
        self,
        telegram_user_id: int,
        inventory_text: str = "",
    ) -> TelegramPlanSummary:
        user_id = self.ensure_user_defaults(telegram_user_id)
        profile = self.profiles.get_profile(user_id) or UserProfile()
        inventory = tuple(
            InventoryItem(name=name.strip())
            for name in inventory_text.replace(";", ",").split(",")
            if name.strip()
        )
        generated = self.planning.generate_weekly_plan(profile, inventory, days=7)
        planning_cycle_id = self.cycles.save_generated_plan(user_id, generated)

        menu_lines = tuple(
            f"{item.day_index + 1}. {item.recipe.title} ({item.recipe.active_time_minutes} min)"
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
