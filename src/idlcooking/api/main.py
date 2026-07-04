from fastapi import FastAPI

from idlcooking import __version__
from idlcooking.api.schemas import (
    GeneratedPlanResponse,
    GeneratePlanPayload,
    MenuItemResponse,
    ProfilePayload,
    ProfileResponse,
    ShoppingListItemResponse,
)
from idlcooking.application.planning import PlanningService
from idlcooking.config import get_settings
from idlcooking.domain.planning import InventoryItem
from idlcooking.domain.profile import ActivityLevel, BudgetLevel, NutritionGoal, UserProfile
from idlcooking.domain.schedule import PlanningSchedule
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    PlanningCycleRepository,
    ProfileRepository,
    ScheduleRepository,
    UserRepository,
)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="I don't like cooking",
        version=__version__,
        description="Backend API for a Telegram-first weekly meal planning service.",
    )
    connection = connect(settings.database_url)
    initialize_database(connection)
    users = UserRepository(connection)
    profiles = ProfileRepository(connection)
    schedules = ScheduleRepository(connection)
    cycles = PlanningCycleRepository(connection)
    planning = PlanningService()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "environment": settings.app_env}

    @app.get("/ready")
    def ready() -> dict[str, str]:
        return {"status": "ready"}

    @app.put("/telegram-users/{telegram_user_id}/profile")
    def save_profile(telegram_user_id: int, payload: ProfilePayload) -> ProfileResponse:
        user_id = users.upsert_telegram_user(telegram_user_id)
        profile = UserProfile(
            household_size=payload.household_size,
            cooking_effort_minutes=payload.cooking_effort_minutes,
            allergies=tuple(payload.allergies),
            hard_restrictions=tuple(payload.hard_restrictions),
            disliked_ingredients=tuple(payload.disliked_ingredients),
            favorite_tags=tuple(payload.favorite_tags),
            budget_level=BudgetLevel(payload.budget_level),
            activity_level=ActivityLevel(payload.activity_level),
            nutrition_goal=NutritionGoal(payload.nutrition_goal),
        )
        profiles.save_profile(user_id, profile)
        schedules.save_schedule(user_id, schedules.get_schedule(user_id) or PlanningSchedule())
        return ProfileResponse(telegram_user_id=telegram_user_id, **payload.model_dump())

    @app.get("/telegram-users/{telegram_user_id}/profile")
    def get_profile(telegram_user_id: int) -> ProfileResponse | dict[str, str]:
        user_id = users.get_user_id_by_telegram_id(telegram_user_id)
        if user_id is None:
            return {"status": "not_found"}
        profile = profiles.get_profile(user_id)
        if profile is None:
            return {"status": "not_found"}
        return ProfileResponse(
            telegram_user_id=telegram_user_id,
            household_size=profile.household_size,
            cooking_effort_minutes=profile.cooking_effort_minutes,
            allergies=list(profile.allergies),
            hard_restrictions=list(profile.hard_restrictions),
            disliked_ingredients=list(profile.disliked_ingredients),
            favorite_tags=list(profile.favorite_tags),
            budget_level=profile.budget_level.value,
            activity_level=profile.activity_level.value,
            nutrition_goal=profile.nutrition_goal.value,
        )

    @app.post("/telegram-users/{telegram_user_id}/plan")
    def generate_plan(
        telegram_user_id: int,
        payload: GeneratePlanPayload,
    ) -> GeneratedPlanResponse:
        user_id = users.upsert_telegram_user(telegram_user_id)
        profile = profiles.get_profile(user_id) or UserProfile()
        inventory = tuple(
            InventoryItem(
                name=item.name,
                category=item.category,
                urgency=item.urgency,
                confidence=item.confidence,
            )
            for item in payload.inventory
        )
        generated = planning.generate_weekly_plan(profile, inventory, days=payload.days)
        planning_cycle_id = cycles.save_generated_plan(user_id, generated)
        return GeneratedPlanResponse(
            telegram_user_id=telegram_user_id,
            planning_cycle_id=planning_cycle_id,
            menu=[
                MenuItemResponse(
                    day_index=item.day_index,
                    meal_type=item.meal_type.value,
                    title=item.recipe.title,
                    source_url=item.recipe.source_url,
                    active_time_minutes=item.recipe.active_time_minutes,
                    score=item.score,
                    reason=item.reason,
                )
                for item in generated.menu
            ],
            shopping_list=[
                ShoppingListItemResponse(
                    name=item.name,
                    category=item.category,
                    already_have=item.already_have,
                    optional=item.optional,
                )
                for item in generated.shopping_list
            ],
        )

    return app


app = create_app()
