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


_AMOUNT_UNIT_PATTERN = re.compile(r"^(?P<amount>[\d.]+|\d+/\d+)\s*(?P<unit>[a-zA-Z]*)$")


def _parse_amount(text: str) -> float | None:
    if "/" in text:
        numerator, _, denominator = text.partition("/")
        try:
            return float(numerator) / float(denominator)
        except (ValueError, ZeroDivisionError):
            return None
    try:
        return float(text)
    except ValueError:
        return None


def _format_amount(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


def _normalize_unit(unit: str) -> str:
    """Singularize a unit for comparison, e.g. "cups" and "cup" both -> "cup"."""
    return unit[:-1] if len(unit) > 1 and unit.endswith("s") else unit


def _pluralize_unit(unit: str, amount: float) -> str:
    if not unit or amount == 1:
        return unit
    return unit if unit.endswith("s") else f"{unit}s"


def _combine_quantities(quantities: list[str]) -> str:
    """Combine quantities for the same ingredient across multiple recipes.

    Sums amounts that share a recognized unit (e.g. "2 cups" + "1 cup" -> "3 cups").
    Falls back to listing every occurrence when units differ or a quantity is not a
    plain number/unit, rather than silently keeping only the first one.
    """
    non_empty = [quantity for quantity in quantities if quantity]
    if not non_empty:
        return ""
    if len(non_empty) == 1:
        return non_empty[0]

    parsed: list[tuple[float, str]] = []
    for quantity in non_empty:
        match = _AMOUNT_UNIT_PATTERN.match(quantity.strip())
        amount = _parse_amount(match.group("amount")) if match else None
        if match is None or amount is None:
            parsed = []
            break
        parsed.append((amount, _normalize_unit(match.group("unit").strip().lower())))

    units = {unit for _, unit in parsed}
    if parsed and len(units) == 1:
        total = sum(amount for amount, _ in parsed)
        unit = _pluralize_unit(next(iter(units)), total)
        return f"{_format_amount(total)} {unit}".strip()

    return " + ".join(non_empty)


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
    names: dict[str, str] = {}
    categories: dict[str, Category] = {}
    quantities: dict[str, list[str]] = {}

    for menu_item in menu:
        for ingredient_line in menu_item.recipe.ingredients:
            name, quantity = _parse_ingredient_line(ingredient_line)
            normalized = name.lower()
            if not normalized:
                continue
            if normalized not in names:
                names[normalized] = name
                categories[normalized] = _categorize(name)
                quantities[normalized] = []
            if quantity:
                quantities[normalized].append(quantity)

    needed = {
        normalized: ShoppingListItem(
            name=name,
            quantity=_combine_quantities(quantities[normalized]),
            category=categories[normalized].value,
            already_have=normalized in available,
            optional=categories[normalized] == Category.SPICES_AND_SAUCES,
        )
        for normalized, name in names.items()
    }

    return sorted(
        needed.values(),
        key=lambda item: (item.category, item.already_have, item.name.lower()),
    )
