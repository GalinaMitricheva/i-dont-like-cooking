import re
from dataclasses import dataclass
from enum import StrEnum

from idlcooking.domain.planning import InventoryItem, MenuItem


class Category(StrEnum):
    PRODUCE = "produce"
    PROTEIN = "protein"
    DAIRY_AND_EGGS = "dairy_and_eggs"
    GRAINS_AND_BAKERY = "grains_and_bakery"
    PANTRY = "pantry"
    FROZEN = "frozen"
    SPICES_AND_SAUCES = "spices_and_sauces"
    OTHER = "other"


# Ordered so more specific/overlapping keywords (e.g. "egg" vs. general protein terms)
# are checked first. Matching is a simple substring search on the ingredient name, so
# categorization is a best-effort heuristic, not a precise lookup.
_CATEGORY_KEYWORDS: tuple[tuple[Category, tuple[str, ...]], ...] = (
    (
        Category.DAIRY_AND_EGGS,
        ("egg", "milk", "cheese", "yogurt", "butter", "cream", "feta", "mozzarella", "parmesan"),
    ),
    (
        Category.PROTEIN,
        (
            "chicken", "beef", "pork", "turkey", "tuna", "salmon", "shrimp", "tofu",
            "lentil", "bean", "chickpea", "meatloaf",
        ),
    ),
    (
        Category.PRODUCE,
        (
            "onion", "garlic", "tomato", "lettuce", "spinach", "carrot", "potato",
            "cucumber", "bell pepper", "zucchini", "avocado", "lime", "lemon", "banana",
            "apple", "cilantro", "parsley", "basil", "mushroom", "broccoli", "celery",
        ),
    ),
    (
        Category.GRAINS_AND_BAKERY,
        ("rice", "pasta", "bread", "flour", "oats", "couscous", "quinoa", "tortilla", "noodle"),
    ),
    (Category.FROZEN, ("frozen",)),
    (
        Category.SPICES_AND_SAUCES,
        (
            "salt", "pepper", "cumin", "paprika", "oregano", "thyme", "cinnamon",
            "soy sauce", "vinegar", "oil", "sauce", "spice", "seasoning", "chili",
        ),
    ),
)

_QUANTITY_PATTERN = re.compile(
    r"^(?P<quantity>[\d½¼¾⅓⅔⅛]+(?:[\-/]\d+)?\s*"
    r"(?:cups?|tbsp|tablespoons?|tsp|teaspoons?|oz|ounces?|lbs?|pounds?|g|grams?|"
    r"kg|kilograms?|ml|milliliters?|l|liters?|cloves?|cans?|pinch(?:es)?|"
    r"slices?|pieces?|pkg|packages?)?)\s+(?P<name>.+)$",
    re.IGNORECASE,
)


def _parse_ingredient_line(text: str) -> tuple[str, str]:
    """Best-effort split of a free-text ingredient line into (name, quantity).

    Falls back to treating the whole line as the name when no leading quantity is
    recognized, since quantities are only ever available "where possible" (PRD 6.7).
    """
    stripped = text.strip()
    match = _QUANTITY_PATTERN.match(stripped)
    if match:
        return match.group("name").strip(), match.group("quantity").strip()
    return stripped, ""


def _categorize(name: str) -> Category:
    # Word-boundary matching (rather than plain substring) avoids false positives like
    # "veggies" containing "egg", while `\w*` after the keyword still matches plurals
    # such as "eggs" or "beans".
    lowered = name.lower()
    for category, keywords in _CATEGORY_KEYWORDS:
        if any(re.search(rf"\b{re.escape(keyword)}\w*\b", lowered) for keyword in keywords):
            return category
    return Category.OTHER


@dataclass(frozen=True)
class ShoppingListItem:
    name: str
    quantity: str = ""
    category: str = Category.OTHER.value
    already_have: bool = False
    optional: bool = False


def build_shopping_list(
    menu: list[MenuItem],
    inventory: tuple[InventoryItem, ...] = (),
) -> list[ShoppingListItem]:
    available = {item.name.lower() for item in inventory}
    needed: dict[str, ShoppingListItem] = {}

    for menu_item in menu:
        for ingredient_line in menu_item.recipe.ingredients:
            name, quantity = _parse_ingredient_line(ingredient_line)
            normalized = name.lower()
            if not normalized or normalized in needed:
                continue
            category = _categorize(name)
            needed[normalized] = ShoppingListItem(
                name=name,
                quantity=quantity,
                category=category.value,
                already_have=normalized in available,
                optional=category == Category.SPICES_AND_SAUCES,
            )

    return sorted(
        needed.values(),
        key=lambda item: (item.category, item.already_have, item.name.lower()),
    )
