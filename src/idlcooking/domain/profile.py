from dataclasses import dataclass, field
from enum import StrEnum


class ActivityLevel(StrEnum):
    SEDENTARY = "sedentary"
    LIGHT = "light"
    MODERATE = "moderate"
    ACTIVE = "active"


class NutritionGoal(StrEnum):
    MAINTAIN = "maintain"
    LOSE = "lose"
    GAIN = "gain"
    EAT_REGULARLY = "eat_regularly"
    REDUCE_WASTE = "reduce_waste"


@dataclass(frozen=True)
class BodyMetrics:
    height_cm: int
    weight_kg: float
    age: int
    sex: str


@dataclass(frozen=True)
class UserProfile:
    household_size: int = 1
    cooking_effort_minutes: int = 20
    allergies: tuple[str, ...] = field(default_factory=tuple)
    hard_restrictions: tuple[str, ...] = field(default_factory=tuple)
    disliked_ingredients: tuple[str, ...] = field(default_factory=tuple)
    favorite_tags: tuple[str, ...] = field(default_factory=tuple)
    activity_level: ActivityLevel = ActivityLevel.LIGHT
    nutrition_goal: NutritionGoal = NutritionGoal.MAINTAIN
    body_metrics: BodyMetrics | None = None


ACTIVITY_MULTIPLIERS: dict[ActivityLevel, float] = {
    ActivityLevel.SEDENTARY: 1.2,
    ActivityLevel.LIGHT: 1.375,
    ActivityLevel.MODERATE: 1.55,
    ActivityLevel.ACTIVE: 1.725,
}


def estimate_daily_calories(profile: UserProfile) -> int | None:
    """Estimate non-medical daily calories with Mifflin-St Jeor when data exists."""
    metrics = profile.body_metrics
    if metrics is None:
        return None

    sex_adjustment = 5 if metrics.sex.lower() in {"male", "m"} else -161
    bmr = 10 * metrics.weight_kg + 6.25 * metrics.height_cm - 5 * metrics.age + sex_adjustment
    calories = bmr * ACTIVITY_MULTIPLIERS[profile.activity_level]

    if profile.nutrition_goal == NutritionGoal.LOSE:
        calories -= 300
    elif profile.nutrition_goal == NutritionGoal.GAIN:
        calories += 250

    return round(calories)
