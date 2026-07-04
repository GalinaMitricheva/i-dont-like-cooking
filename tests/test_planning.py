from idlcooking.domain.planning import (
    InventoryItem,
    MealType,
    RecipeCandidate,
    select_weekly_menu,
)
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.shopping import build_shopping_list


def test_menu_excludes_allergies_and_prefers_inventory() -> None:
    profile = UserProfile(
        cooking_effort_minutes=20,
        allergies=("peanut",),
        favorite_tags=("simple",),
    )
    inventory = (InventoryItem(name="rice", urgency=2),)
    recipes = [
        RecipeCandidate(
            title="Peanut noodles",
            source_url="https://example.com/peanut",
            ingredients=("noodles", "peanut sauce"),
            active_time_minutes=10,
            tags=("simple",),
        ),
        RecipeCandidate(
            title="Rice eggs bowl",
            source_url="https://example.com/rice-eggs",
            ingredients=("rice", "eggs", "cucumber"),
            active_time_minutes=12,
            tags=("simple",),
            protein_grams=28,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, inventory, days=1)

    assert [item.recipe.title for item in menu] == ["Rice eggs bowl"]


def test_shopping_list_marks_inventory_as_already_available() -> None:
    profile = UserProfile()
    inventory = (InventoryItem(name="rice"),)
    recipes = [
        RecipeCandidate(
            title="Rice eggs bowl",
            source_url="https://example.com/rice-eggs",
            ingredients=("rice", "eggs"),
            active_time_minutes=12,
        )
    ]
    menu = select_weekly_menu(recipes, profile, inventory, days=1)

    shopping_list = build_shopping_list(menu, inventory)

    assert [(item.name, item.already_have) for item in shopping_list] == [
        ("eggs", False),
        ("rice", True),
    ]


def test_lunch_leftovers_reuse_previous_days_dinner() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Rice eggs bowl",
            source_url="https://example.com/rice-eggs",
            ingredients=("rice", "eggs"),
            active_time_minutes=12,
        ),
        RecipeCandidate(
            title="Lentil soup",
            source_url="https://example.com/lentil-soup",
            ingredients=("lentils", "carrot"),
            active_time_minutes=15,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=2, include_lunch_leftovers=True)

    assert [(item.day_index, item.meal_type) for item in menu] == [
        (0, MealType.DINNER),
        (1, MealType.LUNCH),
        (1, MealType.DINNER),
    ]
    # The day-1 lunch reuses the day-0 dinner recipe instead of a fresh selection.
    assert menu[1].recipe == menu[0].recipe


def test_lunch_leftovers_do_not_duplicate_shopping_list_items() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Rice eggs bowl",
            source_url="https://example.com/rice-eggs",
            ingredients=("rice", "eggs"),
            active_time_minutes=12,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=2, include_lunch_leftovers=True)
    shopping_list = build_shopping_list(menu)

    assert [item.name for item in shopping_list] == ["eggs", "rice"]


def test_disliked_recipes_are_excluded_from_selection() -> None:
    profile = UserProfile()
    liked_recipe = RecipeCandidate(
        title="Lentil soup",
        source_url="https://example.com/lentil-soup",
        ingredients=("lentils", "carrot"),
        active_time_minutes=15,
    )
    disliked_recipe = RecipeCandidate(
        title="Rice eggs bowl",
        source_url="https://example.com/rice-eggs",
        ingredients=("rice", "eggs"),
        active_time_minutes=12,
    )

    menu = select_weekly_menu(
        [disliked_recipe, liked_recipe],
        profile,
        days=1,
        disliked_recipe_urls=frozenset({disliked_recipe.source_url}),
    )

    assert [item.recipe.title for item in menu] == ["Lentil soup"]


def test_liked_recipes_are_ranked_higher() -> None:
    profile = UserProfile()
    recipe_a = RecipeCandidate(
        title="Rice eggs bowl",
        source_url="https://example.com/rice-eggs",
        ingredients=("rice", "eggs"),
        active_time_minutes=12,
    )
    recipe_b = RecipeCandidate(
        title="Lentil soup",
        source_url="https://example.com/lentil-soup",
        ingredients=("lentils", "carrot"),
        active_time_minutes=12,
    )

    menu = select_weekly_menu(
        [recipe_a, recipe_b],
        profile,
        days=1,
        liked_recipe_urls=frozenset({recipe_b.source_url}),
    )

    assert menu[0].recipe.title == "Lentil soup"
