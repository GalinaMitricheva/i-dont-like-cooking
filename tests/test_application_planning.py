from idlcooking.application.planning import PlanningService
from idlcooking.domain.planning import InventoryItem, RecipeCandidate
from idlcooking.domain.profile import UserProfile


def test_planning_service_generates_menu_and_shopping_list() -> None:
    recipes = (
        RecipeCandidate(
            title="Fast rice",
            source_url="https://example.com/fast-rice",
            ingredients=("rice", "eggs"),
            active_time_minutes=10,
            tags=("simple",),
        ),
    )
    service = PlanningService(recipes=recipes)

    plan = service.generate_weekly_plan(
        UserProfile(),
        inventory=(InventoryItem(name="rice"),),
        days=1,
    )

    assert [item.recipe.title for item in plan.menu] == ["Fast rice"]
    assert [(item.name, item.already_have) for item in plan.shopping_list] == [
        ("eggs", False),
        ("rice", True),
    ]
