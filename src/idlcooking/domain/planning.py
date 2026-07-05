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
    liked_recipe_urls: frozenset[str] = frozenset(),
    disliked_recipe_urls: frozenset[str] = frozenset(),
) -> float:
    if violates_profile(recipe, profile) or recipe.source_url in disliked_recipe_urls:
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

    if recipe.source_url in liked_recipe_urls:
        score += 20

    return score


def _eligible_recipes(
    recipes: list[RecipeCandidate],
    profile: UserProfile,
    disliked_recipe_urls: frozenset[str],
) -> list[RecipeCandidate]:
    return [
        recipe
        for recipe in recipes
        if not violates_profile(recipe, profile) and recipe.source_url not in disliked_recipe_urls
    ]


def _is_breakfast_tagged(recipe: RecipeCandidate) -> bool:
    return any("breakfast" in tag.lower() for tag in recipe.tags)


# Category strings are messy free text scraped from many different sites (see
# recipe_discovery.CURATED_RECIPE_URLS), so this is a best-effort heuristic rather than a
# precise classification. A recipe is only treated as "not a full meal" when none of its
# tags affirmatively say otherwise, so e.g. a recipe tagged both "Appetizer" and "Dinner"
# (legitimately servable as either) is not excluded.
_MEAL_AFFIRMING_KEYWORDS = (
    "dinner", "lunch", "main course", "main dish", "main meal", "entree", "entrée",
)
_NON_MEAL_KEYWORDS = ("appetizer", "side dish", "side", "dessert", "sauce", "snack")


def _is_non_meal_tagged(recipe: RecipeCandidate) -> bool:
    tags_lower = [tag.lower() for tag in recipe.tags]
    if any(keyword in tag for tag in tags_lower for keyword in _MEAL_AFFIRMING_KEYWORDS):
        return False
    return any(keyword in tag for tag in tags_lower for keyword in _NON_MEAL_KEYWORDS)


def _rank_recipes(
    recipes: list[RecipeCandidate],
    profile: UserProfile,
    inventory: tuple[InventoryItem, ...],
    liked_recipe_urls: frozenset[str],
    disliked_recipe_urls: frozenset[str],
) -> list[tuple[float, RecipeCandidate]]:
    scored = [
        (score_recipe(recipe, profile, inventory, liked_recipe_urls, disliked_recipe_urls), recipe)
        for recipe in recipes
    ]
    return sorted(scored, key=lambda item: item[0], reverse=True)


def _cycle_ranked(
    ranked: list[tuple[float, RecipeCandidate]], days: int
) -> list[tuple[float, RecipeCandidate]]:
    """Fill `days` slots from `ranked`, cycling through it if it's smaller than `days`.

    A plain top-N slice leaves later days with no meal at all once the candidate pool
    runs out. Cycling by index instead guarantees every day gets something, and since
    consecutive days advance by exactly one position in the pool, two adjacent days
    only ever repeat the same recipe when the whole pool has just one candidate.
    """
    if not ranked:
        return []
    return [ranked[day % len(ranked)] for day in range(days)]


def select_weekly_menu(
    recipes: list[RecipeCandidate],
    profile: UserProfile,
    inventory: tuple[InventoryItem, ...] = (),
    days: int = 7,
    include_dinner_leftovers: bool = False,
    include_breakfast: bool = False,
    liked_recipe_urls: frozenset[str] = frozenset(),
    disliked_recipe_urls: frozenset[str] = frozenset(),
) -> list[MenuItem]:
    eligible = _eligible_recipes(recipes, profile, disliked_recipe_urls)

    # Avoid quick breakfast recipes (which tend to score well on low active time)
    # crowding out lunch-appropriate ones, unless there's nothing else to choose from.
    # Within that, prefer recipes that aren't tagged as clearly non-meal categories
    # (appetizer/side/dessert/sauce/snack), falling back progressively rather than
    # jumping straight to "every eligible recipe" so a side dish or dessert doesn't
    # stand in for a whole lunch unless there's truly nothing else.
    non_breakfast = [recipe for recipe in eligible if not _is_breakfast_tagged(recipe)]
    lunch_candidates = (
        [recipe for recipe in non_breakfast if not _is_non_meal_tagged(recipe)]
        or non_breakfast
        or eligible
    )
    ranked = _rank_recipes(
        lunch_candidates, profile, inventory, liked_recipe_urls, disliked_recipe_urls
    )
    selected = _cycle_ranked(ranked, days)

    lunches = [
        MenuItem(
            day_index=index,
            meal_type=MealType.LUNCH,
            recipe=recipe,
            score=score,
            reason="Low effort, profile-safe, and uses available food where possible.",
        )
        for index, (score, recipe) in enumerate(selected)
    ]

    dinners = (
        [
            MenuItem(
                day_index=lunch.day_index,
                meal_type=MealType.DINNER,
                recipe=lunch.recipe,
                score=lunch.score,
                reason="Leftovers from today's lunch.",
            )
            for lunch in lunches
        ]
        if include_dinner_leftovers
        else []
    )

    breakfasts = (
        _select_breakfasts(
            eligible, profile, inventory, days, liked_recipe_urls, disliked_recipe_urls
        )
        if include_breakfast
        else []
    )

    return sorted(
        lunches + dinners + breakfasts,
        key=lambda item: (item.day_index, MEAL_TYPE_ORDER[item.meal_type]),
    )


def _select_breakfasts(
    eligible: list[RecipeCandidate],
    profile: UserProfile,
    inventory: tuple[InventoryItem, ...],
    days: int,
    liked_recipe_urls: frozenset[str],
    disliked_recipe_urls: frozenset[str],
) -> list[MenuItem]:
    breakfast_candidates = [
        recipe for recipe in eligible if _is_breakfast_tagged(recipe)
    ] or eligible

    ranked = _rank_recipes(
        breakfast_candidates, profile, inventory, liked_recipe_urls, disliked_recipe_urls
    )

    return [
        MenuItem(
            day_index=day,
            meal_type=MealType.BREAKFAST,
            recipe=recipe,
            score=score,
            reason="Quick breakfast option.",
        )
        for day, (score, recipe) in enumerate(_cycle_ranked(ranked, days))
    ]
