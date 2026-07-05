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
    # Number of portions the recipe makes (issue #39). None when the source didn't say.
    servings: int | None = None


@dataclass(frozen=True)
class MenuItem:
    day_index: int
    meal_type: MealType
    recipe: RecipeCandidate
    score: float
    reason: str
    # True when this meal is the reheated surplus of another meal (a leftover dinner),
    # so it can be shown as a leftover rather than an accidental repeat (issue #28).
    is_leftover: bool = False


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
_NON_MEAL_KEYWORDS = ("appetizer", "side dish", "side", "dessert", "sauce", "snack", "salad")
_SALAD_KEYWORD = "salad"


def _is_non_meal_tagged(recipe: RecipeCandidate) -> bool:
    """Whether a recipe reads as "not a full meal" and so shouldn't anchor a lunch.

    An affirmative meal tag always wins, so a composed main-course salad (e.g. chicken
    Caesar or cobb, tagged both "Salad" and "Main Course") stays eligible — a conservative
    rule that keeps legitimate protein-heavy mains rather than banning all salads (issue
    #40). Otherwise a non-meal tag excludes it. Because many scraped/seed salads only
    signal "salad" in the *title*, a plain salad is also caught by its title, not just its
    tags.
    """
    tags_lower = [tag.lower() for tag in recipe.tags]
    if any(keyword in tag for tag in tags_lower for keyword in _MEAL_AFFIRMING_KEYWORDS):
        return False
    if any(keyword in tag for tag in tags_lower for keyword in _NON_MEAL_KEYWORDS):
        return True
    return _SALAD_KEYWORD in recipe.title.lower()


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


def _yields_leftovers(recipe: RecipeCandidate, profile: UserProfile) -> bool:
    """Whether cooking this recipe once produces enough for a separate leftover meal.

    A leftover dinner only genuinely exists when the lunch is batch-cooked beyond the
    household's single sitting (issue #39). ``servings`` counts individual portions, and
    one household meal consumes ``household_size`` of them, so a spare meal needs at least
    twice that. When ``servings`` is unknown we keep the historical batch-cook default
    rather than fabricating a separate dinner for the whole (mostly yield-less) scraped pool.
    """
    if recipe.servings is None:
        return True
    return recipe.servings >= 2 * max(profile.household_size, 1)


def _prefer_leftover_yielders(
    ranked: list[tuple[float, RecipeCandidate]], profile: UserProfile
) -> list[tuple[float, RecipeCandidate]]:
    """Stable-sort leftover-yielding recipes ahead of single-portion ones (issue #39).

    Used only when dinner leftovers are requested, so more days are anchored by a
    batch-cookable lunch. Single-portion mains stay in the pool (they're fine as a
    lunch); they just aren't preferred for days meant to carry a leftover dinner.
    """
    yielders = [item for item in ranked if _yields_leftovers(item[1], profile)]
    others = [item for item in ranked if not _yields_leftovers(item[1], profile)]
    return yielders + others


def _distinct_dinner(
    ranked: list[tuple[float, RecipeCandidate]], lunch_recipe: RecipeCandidate
) -> tuple[float, RecipeCandidate]:
    """Best-ranked recipe that isn't the given lunch, for a separately-planned dinner.

    Falls back to the lunch itself only when the pool holds nothing else to cook.
    """
    for scored in ranked:
        if scored[1] != lunch_recipe:
            return scored
    return ranked[0]


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
    # When dinner leftovers are on, bias the lunch cycle toward recipes that actually
    # make enough for a second meal (issue #39), so more days can batch-cook once.
    if include_dinner_leftovers:
        ranked = _prefer_leftover_yielders(ranked, profile)
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
        _select_dinners(lunches, ranked, profile) if include_dinner_leftovers else []
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


def _select_dinners(
    lunches: list[MenuItem],
    ranked: list[tuple[float, RecipeCandidate]],
    profile: UserProfile,
) -> list[MenuItem]:
    """Pair each day's lunch with a dinner (issues #28, #39).

    A lunch that batch-cooks beyond one household sitting carries into dinner as a marked
    leftover; a single-portion lunch gets a separately-planned dinner instead of a faked
    repeat.
    """
    dinners: list[MenuItem] = []
    for lunch in lunches:
        if _yields_leftovers(lunch.recipe, profile):
            dinners.append(
                MenuItem(
                    day_index=lunch.day_index,
                    meal_type=MealType.DINNER,
                    recipe=lunch.recipe,
                    score=lunch.score,
                    reason="Leftovers from today's lunch.",
                    is_leftover=True,
                )
            )
        else:
            score, recipe = _distinct_dinner(ranked, lunch.recipe)
            dinners.append(
                MenuItem(
                    day_index=lunch.day_index,
                    meal_type=MealType.DINNER,
                    recipe=recipe,
                    score=score,
                    reason="Freshly cooked dinner (lunch makes only one portion).",
                    is_leftover=False,
                )
            )
    return dinners


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
