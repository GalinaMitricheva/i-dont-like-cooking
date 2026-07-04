from datetime import time

from idlcooking.application.planning import PlanningService
from idlcooking.domain.feedback import CookedStatus, Rating, RecipeFeedback
from idlcooking.domain.planning import InventoryItem, RecipeCandidate
from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    BudgetLevel,
    NutritionGoal,
    UserProfile,
)
from idlcooking.domain.schedule import PlanningSchedule
from idlcooking.storage import connect, initialize_database
from idlcooking.storage.repositories import (
    FeedbackRepository,
    PlanningCycleRepository,
    ProfileRepository,
    RecipeRepository,
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
        budget_level=BudgetLevel.LOW,
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


def test_user_consent_is_absent_until_recorded() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    users.upsert_telegram_user(telegram_user_id=12345)

    assert users.get_consent_version(12345) is None

    users.record_consent(12345, "v1")

    assert users.get_consent_version(12345) == "v1"


def test_recipe_repository_caches_and_upserts_by_source_url() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    recipes = RecipeRepository(connection)

    recipe = RecipeCandidate(
        title="Fast rice",
        source_url="https://example.com/fast-rice",
        ingredients=("rice", "eggs"),
        active_time_minutes=10,
        tags=("simple",),
        protein_grams=20,
        steps_summary="Cook rice, fry eggs, combine.",
    )
    recipes.upsert_recipe(recipe)

    assert recipes.get_all_recipes() == [recipe]

    updated = RecipeCandidate(
        title="Fast rice (updated)",
        source_url="https://example.com/fast-rice",
        ingredients=("rice", "eggs", "soy sauce"),
        active_time_minutes=12,
    )
    recipes.upsert_recipe(updated)

    cached = recipes.get_all_recipes()
    assert len(cached) == 1
    assert cached[0].title == "Fast rice (updated)"
    assert cached[0].ingredients == ("rice", "eggs", "soy sauce")


def test_get_latest_cycle_menu_items_deduplicates_lunch_leftovers() -> None:
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
    ).generate_weekly_plan(UserProfile(), days=2, include_lunch_leftovers=True)
    cycles.save_generated_plan(user_id, plan)

    result = cycles.get_latest_cycle_menu_items(user_id)

    assert result is not None
    planning_cycle_id, items = result
    assert planning_cycle_id == 1
    # The lunch leftover repeats the same dinner recipe; it must not appear twice.
    assert items == [{"title": "Fast rice", "source_url": "https://example.com/fast-rice"}]


def test_feedback_repository_saves_and_filters_by_rating() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    cycles = PlanningCycleRepository(connection)
    feedback = FeedbackRepository(connection)
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
    ).generate_weekly_plan(UserProfile(), days=1)
    planning_cycle_id = cycles.save_generated_plan(user_id, plan)

    feedback.save_feedback(
        user_id,
        planning_cycle_id,
        RecipeFeedback(
            recipe_source_url="https://example.com/fast-rice",
            recipe_title="Fast rice",
            cooked_status=CookedStatus.COOKED,
            rating=Rating.LIKED,
        ),
    )
    feedback.save_feedback(
        user_id,
        planning_cycle_id,
        RecipeFeedback(
            recipe_source_url="https://example.com/other",
            recipe_title="Other dish",
            cooked_status=CookedStatus.COOKED,
            rating=Rating.DISLIKED,
            effort_feedback="too_much_effort",
        ),
    )

    assert feedback.get_recipe_urls_by_rating(user_id, Rating.LIKED) == frozenset(
        {"https://example.com/fast-rice"}
    )
    assert feedback.get_recipe_urls_by_rating(user_id, Rating.DISLIKED) == frozenset(
        {"https://example.com/other"}
    )
    assert feedback.get_recipe_urls_by_rating(user_id, Rating.NEUTRAL) == frozenset()


def test_planning_cycle_repository_accept_and_shopping_list_actions() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    cycles = PlanningCycleRepository(connection)
    user_id = users.upsert_telegram_user(telegram_user_id=12345)

    assert cycles.get_latest_cycle_id(user_id) is None

    plan = PlanningService(
        recipes=(
            RecipeCandidate(
                title="Fast rice",
                source_url="https://example.com/fast-rice",
                ingredients=("2 cups rice", "eggs"),
                active_time_minutes=10,
            ),
        )
    ).generate_weekly_plan(UserProfile(), inventory=(InventoryItem(name="rice"),), days=1)
    planning_cycle_id = cycles.save_generated_plan(user_id, plan)

    assert cycles.get_latest_cycle_id(user_id) == planning_cycle_id

    cycles.mark_cycle_status(planning_cycle_id, "accepted")
    assert cycles.get_latest_cycle_summary(user_id)["status"] == "accepted"

    lines = cycles.get_shopping_list_lines(planning_cycle_id)
    assert [(item["name"], item["quantity"], item["already_have"]) for item in lines] == [
        ("eggs", "", False),
        ("rice", "2 cups", True),
    ]

    cycles.mark_all_items_bought(planning_cycle_id)
    lines_after = cycles.get_shopping_list_lines(planning_cycle_id)
    assert all(item["checked"] for item in lines_after)


def test_planning_cycle_repository_returns_menu_items_grouped_by_day() -> None:
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
                steps_summary="Cook rice. Fry eggs. Combine.",
            ),
            RecipeCandidate(
                title="Lentil soup",
                source_url="https://example.com/lentil-soup",
                ingredients=("lentils", "carrot"),
                active_time_minutes=15,
            ),
        )
    ).generate_weekly_plan(UserProfile(), days=2, include_lunch_leftovers=True)
    planning_cycle_id = cycles.save_generated_plan(user_id, plan)

    by_day = cycles.get_menu_items_by_day(planning_cycle_id)

    assert set(by_day.keys()) == {0, 1}
    assert [item["meal_type"] for item in by_day[0]] == ["dinner"]
    assert [item["meal_type"] for item in by_day[1]] == ["lunch", "dinner"]
    day0_dinner = by_day[0][0]
    assert day0_dinner["ingredients"] == ("rice", "eggs")
    assert day0_dinner["steps_summary"] == "Cook rice. Fry eggs. Combine."


def test_schedule_repository_lists_enabled_schedules_with_telegram_ids() -> None:
    connection = connect("sqlite:///:memory:")
    initialize_database(connection)
    users = UserRepository(connection)
    schedules = ScheduleRepository(connection)

    enabled_user_id = users.upsert_telegram_user(telegram_user_id=111)
    schedules.save_schedule(enabled_user_id, PlanningSchedule(weekday=5, at_time=time(9, 0)))

    disabled_user_id = users.upsert_telegram_user(telegram_user_id=222)
    schedules.save_schedule(disabled_user_id, PlanningSchedule(enabled=False))

    results = schedules.get_enabled_schedules_with_telegram_ids()

    assert [telegram_user_id for telegram_user_id, _, _ in results] == [111]
    _, schedule, last_triggered_at = results[0]
    assert schedule.weekday == 5
    assert last_triggered_at is None

    schedules.mark_schedule_triggered(111, "2026-07-04T09:00:00+00:00")
    results_after = schedules.get_enabled_schedules_with_telegram_ids()
    assert results_after[0][2] == "2026-07-04T09:00:00+00:00"
