from idlcooking.domain.planning import (
    InventoryItem,
    MealType,
    MenuItem,
    RecipeCandidate,
    select_weekly_menu,
)
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.shopping import (
    Category,
    _categorize,
    _combine_quantities,
    _matching_key,
    _parse_ingredient_line,
    _strip_parenthetical_asides,
    build_shopping_list,
)


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


def test_dinner_leftovers_reuse_the_same_days_lunch() -> None:
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

    menu = select_weekly_menu(recipes, profile, days=2, include_dinner_leftovers=True)

    assert [(item.day_index, item.meal_type) for item in menu] == [
        (0, MealType.LUNCH),
        (0, MealType.DINNER),
        (1, MealType.LUNCH),
        (1, MealType.DINNER),
    ]
    # Each day's dinner reuses that same day's lunch recipe instead of a fresh
    # selection, and every day gets a lunch (issue #22: no day is ever skipped).
    assert menu[1].recipe == menu[0].recipe
    assert menu[3].recipe == menu[2].recipe


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

    menu = select_weekly_menu(recipes, profile, days=2, include_dinner_leftovers=True)
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


def test_parse_ingredient_line_extracts_quantity_and_name() -> None:
    assert _parse_ingredient_line("2 cups rice, cooked") == ("rice, cooked", "2 cups")
    assert _parse_ingredient_line("1/2 cup panko bread crumbs") == (
        "panko bread crumbs",
        "1/2 cup",
    )


def test_parse_ingredient_line_falls_back_without_a_recognized_quantity() -> None:
    assert _parse_ingredient_line("salt and pepper to taste") == (
        "salt and pepper to taste",
        "",
    )
    assert _parse_ingredient_line("garlic") == ("garlic", "")


def test_categorize_maps_common_ingredients() -> None:
    assert _categorize("large eggs") == Category.DAIRY_AND_EGGS
    assert _categorize("ground turkey") == Category.PROTEIN
    assert _categorize("garlic, minced") == Category.PRODUCE
    assert _categorize("panko bread crumbs") == Category.GRAINS_AND_BAKERY
    assert _categorize("soy sauce") == Category.SPICES_AND_SAUCES
    assert _categorize("something unrecognized") == Category.OTHER


def test_categorize_uses_word_boundaries_to_avoid_false_positives() -> None:
    # "veggies" contains the substring "egg"; plain substring matching would
    # wrongly categorize it as dairy_and_eggs.
    assert _categorize("and/or veggies, for serving") == Category.OTHER


def test_build_shopping_list_groups_by_category_and_marks_spices_optional() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Fried rice",
            source_url="https://example.com/fried-rice",
            ingredients=("2 cups rice", "2 eggs", "1 tablespoon soy sauce", "carrot"),
            active_time_minutes=15,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=1)
    shopping_list = build_shopping_list(menu)

    by_name = {item.name: item for item in shopping_list}
    assert by_name["rice"].quantity == "2 cups"
    assert by_name["rice"].category == Category.GRAINS_AND_BAKERY.value
    assert by_name["eggs"].category == Category.DAIRY_AND_EGGS.value
    assert by_name["soy sauce"].category == Category.SPICES_AND_SAUCES.value
    assert by_name["soy sauce"].optional is True
    assert by_name["carrot"].category == Category.PRODUCE.value
    assert by_name["carrot"].optional is False
    # Grouped by category: items in the same category stay contiguous.
    categories_in_order = [item.category for item in shopping_list]
    assert categories_in_order == sorted(categories_in_order)


def test_shopping_list_sums_matching_quantities_across_recipes() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Rice bowl A",
            source_url="https://example.com/a",
            ingredients=("2 cups rice",),
            active_time_minutes=10,
        ),
        RecipeCandidate(
            title="Rice bowl B",
            source_url="https://example.com/b",
            ingredients=("1 cup rice",),
            active_time_minutes=12,
        ),
        RecipeCandidate(
            title="Rice bowl C",
            source_url="https://example.com/c",
            ingredients=("3 cups rice",),
            active_time_minutes=14,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=3)
    shopping_list = build_shopping_list(menu)

    by_name = {item.name: item for item in shopping_list}
    assert by_name["rice"].quantity == "6 cups"


def test_combine_quantities_sums_matching_units_regardless_of_plural() -> None:
    assert _combine_quantities(["2 cups", "1 cup"]) == "3 cups"
    assert _combine_quantities(["1 clove", "2 cloves"]) == "3 cloves"
    assert _combine_quantities(["1 cup"]) == "1 cup"


def test_combine_quantities_handles_fractions() -> None:
    assert _combine_quantities(["1/2 cup", "1/2 cup"]) == "1 cup"


def test_combine_quantities_ignores_missing_amounts() -> None:
    assert _combine_quantities(["2", ""]) == "2"
    assert _combine_quantities(["", ""]) == ""


def test_combine_quantities_falls_back_to_listing_when_unparseable() -> None:
    assert _combine_quantities(["a pinch", "2 cups"]) == "a pinch + 2 cups"


def test_shopping_list_lists_quantities_separately_when_units_differ() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="A",
            source_url="https://example.com/a",
            ingredients=("2 cups rice",),
            active_time_minutes=10,
        ),
        RecipeCandidate(
            title="B",
            source_url="https://example.com/b",
            ingredients=("1 tablespoon rice",),
            active_time_minutes=12,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=2)
    shopping_list = build_shopping_list(menu)

    by_name = {item.name: item for item in shopping_list}
    assert by_name["rice"].quantity == "2 cups + 1 tablespoon"


def test_strip_parenthetical_asides_removes_trailing_and_embedded_notes() -> None:
    assert _strip_parenthetical_asides("garlic cloves (minced)") == "garlic cloves"
    assert _strip_parenthetical_asides("garlic powder (or more onion)") == "garlic powder"
    assert _strip_parenthetical_asides("garlic powder (, optional but recommended)") == (
        "garlic powder"
    )
    assert _strip_parenthetical_asides("carrot") == "carrot"


def test_matching_key_merges_singular_plural_and_parenthetical_variants() -> None:
    assert _matching_key("garlic clove") == _matching_key("garlic cloves (minced)")
    assert _matching_key("eggs") == _matching_key("egg")
    assert _matching_key("tomatoes") == _matching_key("tomato")


def test_matching_key_keeps_genuinely_different_ingredients_apart() -> None:
    # Garlic cloves and garlic powder are different things to buy; they must not merge.
    assert _matching_key("garlic clove") != _matching_key("garlic powder")
    assert _matching_key("hummus") == "hummus"  # not mangled into "hummu"
    assert _matching_key("grass-fed beef") != _matching_key("grass")


def test_build_shopping_list_merges_differently_worded_garlic_lines() -> None:
    # Verbatim-style messy ingredient lines pulled from real recipe scrapes (issue #18).
    def menu_item(ingredient: str, day_index: int) -> MenuItem:
        return MenuItem(
            day_index=day_index,
            meal_type=MealType.DINNER,
            recipe=RecipeCandidate(
                title=f"Recipe {day_index}",
                source_url=f"https://example.com/{day_index}",
                ingredients=(ingredient,),
                active_time_minutes=10,
            ),
            score=1.0,
            reason="",
        )

    menu = [
        menu_item("1 garlic clove", 0),
        menu_item("2 garlic cloves (minced)", 1),
        menu_item("1 teaspoon garlic powder", 2),
        menu_item("1/2 tsp garlic powder (or more onion)", 3),
    ]

    shopping_list = build_shopping_list(menu)

    by_name = {item.name: item for item in shopping_list}
    # The two clove lines merge into one line (keeping the first-seen wording);
    # the two powder lines merge into another. Cloves and powder stay separate
    # since they're different things to buy.
    assert set(by_name) == {"garlic clove", "garlic powder"}
    # "clove"/"cloves" here is part of the ingredient name, not a recognized
    # leading quantity unit, so the bare counts (1 + 2) sum unitless.
    assert by_name["garlic clove"].quantity == "3"
    assert by_name["garlic powder"].quantity == "1 teaspoon + 1/2 tsp"


def test_breakfast_prefers_recipes_tagged_breakfast() -> None:
    profile = UserProfile()
    breakfast_recipe = RecipeCandidate(
        title="Oats and banana",
        source_url="https://example.com/oats",
        ingredients=("oats", "banana"),
        active_time_minutes=5,
        tags=("breakfast", "no-cook"),
    )
    dinner_recipe = RecipeCandidate(
        title="Chicken couscous tray",
        source_url="https://example.com/couscous",
        ingredients=("chicken", "couscous"),
        active_time_minutes=18,
    )

    menu = select_weekly_menu(
        [dinner_recipe, breakfast_recipe], profile, days=1, include_breakfast=True
    )

    breakfasts = [item for item in menu if item.meal_type == MealType.BREAKFAST]
    assert len(breakfasts) == 1
    assert breakfasts[0].recipe.title == "Oats and banana"
    # Lunch selection is unaffected by breakfast filtering.
    lunches = [item for item in menu if item.meal_type == MealType.LUNCH]
    assert lunches[0].recipe.title == "Chicken couscous tray"


def test_breakfast_cycles_through_a_smaller_candidate_pool() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Oats and banana",
            source_url="https://example.com/oats",
            ingredients=("oats", "banana"),
            active_time_minutes=5,
            tags=("breakfast",),
        ),
        RecipeCandidate(
            title="Scrambled eggs",
            source_url="https://example.com/eggs",
            ingredients=("eggs",),
            active_time_minutes=5,
            tags=("breakfast",),
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=4, include_breakfast=True)

    breakfasts = [item for item in menu if item.meal_type == MealType.BREAKFAST]
    assert len(breakfasts) == 4
    # Only 2 breakfast candidates for 4 days: day 2 repeats day 0's pick, day 3 repeats day 1's.
    assert breakfasts[0].recipe == breakfasts[2].recipe
    assert breakfasts[1].recipe == breakfasts[3].recipe


def test_breakfast_falls_back_to_all_recipes_when_none_are_tagged() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Chicken couscous tray",
            source_url="https://example.com/couscous",
            ingredients=("chicken", "couscous"),
            active_time_minutes=18,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=1, include_breakfast=True)

    breakfasts = [item for item in menu if item.meal_type == MealType.BREAKFAST]
    assert len(breakfasts) == 1
    assert breakfasts[0].recipe.title == "Chicken couscous tray"


def test_breakfast_is_excluded_by_default() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title="Oats and banana",
            source_url="https://example.com/oats",
            ingredients=("oats", "banana"),
            active_time_minutes=5,
            tags=("breakfast",),
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=1)

    assert all(item.meal_type != MealType.BREAKFAST for item in menu)


def test_lunch_selection_avoids_non_meal_categories_when_real_mains_exist() -> None:
    profile = UserProfile()
    guacamole = RecipeCandidate(
        title="Guacamole",
        source_url="https://example.com/guacamole",
        ingredients=("avocado",),
        active_time_minutes=5,
        tags=("Appetizer",),
    )
    meatloaf = RecipeCandidate(
        title="Meatloaf",
        source_url="https://example.com/meatloaf",
        ingredients=("beef",),
        active_time_minutes=15,
        tags=("Dinner",),
    )

    menu = select_weekly_menu([guacamole, meatloaf], profile, days=1)

    assert menu[0].recipe.title == "Meatloaf"


def test_lunch_selection_falls_back_to_non_meal_categories_when_pool_is_thin() -> None:
    # Only an appetizer is available; it's still better than leaving a day unplanned.
    profile = UserProfile()
    guacamole = RecipeCandidate(
        title="Guacamole",
        source_url="https://example.com/guacamole",
        ingredients=("avocado",),
        active_time_minutes=5,
        tags=("Appetizer",),
    )

    menu = select_weekly_menu([guacamole], profile, days=1)

    assert menu[0].recipe.title == "Guacamole"


def test_lunch_selection_keeps_recipes_with_both_non_meal_and_meal_tags() -> None:
    # Tagged both Appetizer and Dinner (legitimately servable as either); the explicit
    # "Dinner" tag should win rather than excluding it as a non-meal category.
    profile = UserProfile()
    meatballs = RecipeCandidate(
        title="Turkey meatballs",
        source_url="https://example.com/meatballs",
        ingredients=("turkey",),
        active_time_minutes=15,
        tags=("Appetizer", "Dinner"),
    )
    side_dish = RecipeCandidate(
        title="Mashed potatoes",
        source_url="https://example.com/mashed-potatoes",
        ingredients=("potato",),
        active_time_minutes=10,
        tags=("Side Dish",),
    )

    menu = select_weekly_menu([meatballs, side_dish], profile, days=1)

    assert menu[0].recipe.title == "Turkey meatballs"


def test_lunch_selection_cycles_through_a_thin_pool_instead_of_leaving_days_unplanned() -> None:
    # Issue #25: only 2 candidates for a 4-day plan used to leave days 2 and 3 with
    # no lunch at all; cycling must fill every day instead.
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
            active_time_minutes=12,
        ),
    ]

    menu = select_weekly_menu(recipes, profile, days=4)

    assert len(menu) == 4
    # No two adjacent days repeat the same recipe.
    assert all(menu[day].recipe != menu[day + 1].recipe for day in range(3))
    # Day 2 repeats day 0's pick, day 3 repeats day 1's, since only 2 candidates exist.
    assert menu[0].recipe == menu[2].recipe
    assert menu[1].recipe == menu[3].recipe


def test_lunch_selection_has_zero_repeats_when_the_pool_is_abundant() -> None:
    profile = UserProfile()
    recipes = [
        RecipeCandidate(
            title=f"Recipe {index}",
            source_url=f"https://example.com/recipe-{index}",
            ingredients=("filler",),
            active_time_minutes=10,
        )
        for index in range(5)
    ]

    menu = select_weekly_menu(recipes, profile, days=5)

    titles = [item.recipe.title for item in menu]
    assert len(titles) == len(set(titles)) == 5
