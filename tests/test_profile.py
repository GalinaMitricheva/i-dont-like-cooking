from idlcooking.domain.profile import (
    ActivityLevel,
    BodyMetrics,
    NutritionGoal,
    UserProfile,
    estimate_daily_calories,
)


def test_estimate_daily_calories_is_optional_without_body_metrics() -> None:
    assert estimate_daily_calories(UserProfile()) is None


def test_estimate_daily_calories_applies_goal_adjustment() -> None:
    maintain = UserProfile(
        activity_level=ActivityLevel.LIGHT,
        nutrition_goal=NutritionGoal.MAINTAIN,
        body_metrics=BodyMetrics(height_cm=170, weight_kg=70, age=35, sex="female"),
    )
    lose = UserProfile(
        activity_level=ActivityLevel.LIGHT,
        nutrition_goal=NutritionGoal.LOSE,
        body_metrics=BodyMetrics(height_cm=170, weight_kg=70, age=35, sex="female"),
    )

    assert estimate_daily_calories(maintain) - estimate_daily_calories(lose) == 300
