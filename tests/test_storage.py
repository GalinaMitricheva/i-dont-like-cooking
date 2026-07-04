from datetime import time

from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    NutritionGoal,
    UserProfile,
)
from idlcooking.domain.schedule import PlanningSchedule
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import ProfileRepository, ScheduleRepository, UserRepository


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
