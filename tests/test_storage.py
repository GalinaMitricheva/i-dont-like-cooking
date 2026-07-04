from datetime import time

from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    NutritionGoal,
    UserProfile,
)
from idlcooking.application.planning import PlanningService
from idlcooking.domain.planning import InventoryItem, RecipeCandidate
from idlcooking.domain.schedule import PlanningSchedule
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    PlanningCycleRepository,
    ProfileRepository,
    ScheduleRepository,
    UserRepository,
)


def test_user_profile_and_schedule_round_trip() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    profiles = ProfileRepository(connection)
    schedules = ScheduleRepository(connection)

    user_id = users.upsert_telegram_user(telegram_user_id=12345, timezone="Europe/Berlin")
    profile = UserProfile(
        household_size=2,
        cooking_effort_minutes=15,
        allergies=("peanut",),
        hard_restrictions=("pork",),
        disliked_ingredients=("cilantro",),
        favorite_tags=("rice", "simple"),
        activity_level=ActivityLevel.MODERATE,
        nutrition_goal=NutritionGoal.REDUCE_WASTE,
        body_metrics=BodyMetrics(height_cm=170, weight_kg=70, age=35, sex="female"),
    )
    schedule = PlanningSchedule(weekday=6, at_time=time(10, 30), timezone="Europe/Berlin")

    profiles.save_profile(user_id, profile)
    schedules.save_schedule(user_id, schedule)

    assert users.get_user_id_by_telegram_id(12345) == user_id
    assert profiles.get_profile(user_id) == profile
    assert schedules.get_schedule(user_id) == schedule


def test_planning_cycle_repository_saves_generated_plan_summary() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    cycles = PlanningCycleRepository(connection)
    user_id = users.upsert_telegram_user(telegram_user_id=12345)
    plan = PlanningService(
        recipes=(
            RecipeCandidate(
                title="Fast rice",
                source_url="https://example.com/fast-rice",
                ingredients=("rice", "eggs"),
                active_time_minutes=10,
            ),
        )
    ).generate_weekly_plan(UserProfile(), inventory=(InventoryItem(name="rice"),), days=1)

    planning_cycle_id = cycles.save_generated_plan(user_id, plan)

    assert cycles.get_latest_cycle_summary(user_id) == {
        "id": planning_cycle_id,
        "status": "generated",
        "menu_count": 1,
        "shopping_count": 2,
    }


def test_delete_user_cascades_to_profile_schedule_and_planning_cycles() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    profiles = ProfileRepository(connection)
    schedules = ScheduleRepository(connection)
    cycles = PlanningCycleRepository(connection)

    user_id = users.upsert_telegram_user(telegram_user_id=12345)
    profiles.save_profile(user_id, UserProfile())
    schedules.save_schedule(user_id, PlanningSchedule())
    plan = PlanningService(
        recipes=(
            RecipeCandidate(
                title="Fast rice",
                source_url="https://example.com/fast-rice",
                ingredients=("rice", "eggs"),
                active_time_minutes=10,
            ),
        )
    ).generate_weekly_plan(UserProfile(), days=1)
    cycles.save_generated_plan(user_id, plan)

    users.delete_user(12345)

    assert users.get_user_id_by_telegram_id(12345) is None
    assert profiles.get_profile(user_id) is None
    assert schedules.get_schedule(user_id) is None
    assert cycles.get_latest_cycle_summary(user_id) is None
