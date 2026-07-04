from dataclasses import dataclass, field
from enum import StrEnum

from idlcooking.domain.profile import UserProfile


class MealType(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    DINNER = "dinner"
    SNACK = "snack"


MEAL_TYPE_ORDER: dict[MealType, int] = {
    MealType.BREAKFAST: 0,
    MealType.LUNCH: 1,
    MealType.DINNER: 2,
    MealType.SNACK: 3,
}


@dataclass(frozen=True)
class InventoryItem:
    name: str
    category: str = "other"
    urgency: int = 0
    confidence: float = 1.0


@dataclass(frozen=True)
class RecipeCandidate:
    title: str
    source_url: str
    ingredients: tuple[str, ...]
    active_time_minutes: int
    tags: tuple[str, ...] = field(default_factory=tuple)
    protein_grams: int | None = None
    steps_summary: str = ""


@dataclass(frozen=True)
class MenuItem:
    day_index: int
    meal_type: MealType
    recipe: RecipeCandidate
    score: float
    reason: str


def violates_profile(recipe: RecipeCandidate, profile: UserProfile) -> bool:
    blocked_terms = (
        *profile.allergies,
        *profile.hard_restrictions,
        *profile.disliked_ingredients,
    )
    searchable = " ".join((*recipe.ingredients, *recipe.tags, recipe.title)).lower()
    return any(term.lower() in searchable for term in blocked_terms if term.strip())


def score_recipe(
    recipe: RecipeCandidate,
    profile: UserProfile,
    inventory: tuple[InventoryItem, ...] = (),
) -> float:
    if violates_profile(recipe, profile):
        return float("-inf")

    score = 100.0
    score -= max(recipe.active_time_minutes - profile.cooking_effort_minutes, 0) * 2.5
    score += max(profile.cooking_effort_minutes - recipe.active_time_minutes, 0) * 0.5

    recipe_text = " ".join(recipe.ingredients).lower()
    for item in inventory:
        if item.name.lower() in recipe_text:
            score += 8 + item.urgency * 3

    for tag in profile.favorite_tags:
        if tag.lower() in {recipe_tag.lower() for recipe_tag in recipe.tags}:
            score += 6

    if recipe.protein_grams is not None and recipe.protein_grams >= 25:
        score += 5

    return score


def select_weekly_menu(
    recipes: list[RecipeCandidate],
    profile: UserProfile,
    inventory: tuple[InventoryItem, ...] = (),
    days: int = 7,
    include_lunch_leftovers: bool = False,
) -> list[MenuItem]:
    scored = [
        (score_recipe(recipe, profile, inventory), recipe)
        for recipe in recipes
        if not violates_profile(recipe, profile)
    ]
    ranked = sorted(scored, key=lambda item: item[0], reverse=True)
    selected = ranked[:days]

    dinners = [
        MenuItem(
            day_index=index,
            meal_type=MealType.DINNER,
            recipe=recipe,
            score=score,
            reason="Low effort, profile-safe, and uses available food where possible.",
        )
        for index, (score, recipe) in enumerate(selected)
    ]

    if not include_lunch_leftovers:
        return dinners

    lunches = [
        MenuItem(
            day_index=dinner.day_index + 1,
            meal_type=MealType.LUNCH,
            recipe=dinner.recipe,
            score=dinner.score,
            reason="Leftovers from the previous day's dinner.",
        )
        for dinner in dinners
        if dinner.day_index + 1 < days
    ]

    return sorted(
        dinners + lunches,
        key=lambda item: (item.day_index, MEAL_TYPE_ORDER[item.meal_type]),
    )
