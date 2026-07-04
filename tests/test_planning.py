from idlcooking.domain.planning import InventoryItem, RecipeCandidate, select_weekly_menu
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
