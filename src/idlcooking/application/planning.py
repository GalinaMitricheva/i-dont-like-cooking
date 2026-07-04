from dataclasses import dataclass

from idlcooking.domain.planning import InventoryItem, MenuItem, RecipeCandidate, select_weekly_menu
from idlcooking.domain.profile import UserProfile
from idlcooking.domain.shopping import ShoppingListItem, build_shopping_list

SEED_RECIPES: tuple[RecipeCandidate, ...] = (
    RecipeCandidate(
        title="Rice eggs bowl",
        source_url="https://example.com/recipes/rice-eggs-bowl",
        ingredients=("rice", "eggs", "cucumber", "soy sauce"),
        active_time_minutes=12,
        tags=("simple", "rice", "vegetarian"),
        protein_grams=28,
    ),
    RecipeCandidate(
        title="Chicken couscous tray",
        source_url="https://example.com/recipes/chicken-couscous-tray",
        ingredients=("chicken", "couscous", "tomato", "zucchini"),
        active_time_minutes=18,
        tags=("simple", "batch", "high-protein"),
        protein_grams=35,
    ),
    RecipeCandidate(
        title="Tuna bean salad",
        source_url="https://example.com/recipes/tuna-bean-salad",
        ingredients=("tuna", "white beans", "tomato", "lettuce"),
        active_time_minutes=10,
        tags=("no-cook", "simple", "high-protein"),
        protein_grams=32,
    ),
    RecipeCandidate(
        title="Lentil tomato soup",
        source_url="https://example.com/recipes/lentil-tomato-soup",
        ingredients=("red lentils", "tomato", "carrot", "onion"),
        active_time_minutes=15,
        tags=("simple", "batch", "vegan"),
        protein_grams=24,
    ),
    RecipeCandidate(
        title="Greek yogurt breakfast",
        source_url="https://example.com/recipes/greek-yogurt-breakfast",
        ingredients=("greek yogurt", "oats", "banana", "nuts"),
        active_time_minutes=5,
        tags=("breakfast", "no-cook", "simple"),
        protein_grams=25,
    ),
    RecipeCandidate(
        title="Pasta with tomato and cottage cheese",
        source_url="https://example.com/recipes/tomato-cottage-pasta",
        ingredients=("pasta", "tomato", "cottage cheese", "spinach"),
        active_time_minutes=17,
        tags=("simple", "vegetarian"),
        protein_grams=30,
    ),
    RecipeCandidate(
        title="Microwave potato with tuna",
        source_url="https://example.com/recipes/microwave-potato-tuna",
        ingredients=("potato", "tuna", "yogurt", "cucumber"),
        active_time_minutes=14,
        tags=("simple", "microwave", "high-protein"),
        protein_grams=33,
    ),
)


@dataclass(frozen=True)
class GeneratedPlan:
    menu: list[MenuItem]
    shopping_list: list[ShoppingListItem]


class PlanningService:
    def __init__(self, recipes: tuple[RecipeCandidate, ...] = SEED_RECIPES) -> None:
        self.recipes = recipes

    def generate_weekly_plan(
        self,
        profile: UserProfile,
        inventory: tuple[InventoryItem, ...] = (),
        days: int = 7,
        include_lunch_leftovers: bool = False,
    ) -> GeneratedPlan:
        menu = select_weekly_menu(
            list(self.recipes),
            profile,
            inventory,
            days=days,
            include_lunch_leftovers=include_lunch_leftovers,
        )
        shopping_list = build_shopping_list(menu, inventory)
        return GeneratedPlan(menu=menu, shopping_list=shopping_list)
