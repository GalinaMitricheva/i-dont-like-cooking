import re
from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction

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


# Substitution / serving notes introduced by a trailing comma + keyword ("..., sub water",
# "..., or use X", "..., to taste"). These describe *how* to use an ingredient, not a
# separate thing to buy, so they're trimmed off the display name (issue #29).
_TRAILING_ASIDE_PATTERN = re.compile(
    r"\s*,\s*(?:sub|substitute|or|to serve|for serving|to taste|optional|plus more)\b.*$",
    re.IGNORECASE,
)


def _strip_parenthetical_asides(text: str) -> str:
    """Remove parenthetical asides such as "(minced)" or "(or more onion)".

    Real scraped recipes commonly tack these onto the ingredient name; they don't
    change what needs to be bought, so leaving them in causes near-duplicate
    shopping list lines for what is really the same ingredient.
    """
    without_parens = re.sub(r"\([^)]*\)", "", text)
    # Scraped lines sometimes carry an *unbalanced* paren — an orphan ")" left after a
    # balanced pair was stripped (e.g. "wine (red), sub water)"), or a stray "(" — which
    # the balanced-pair regex above never touches. Drop any that survive (issue #29).
    without_parens = without_parens.replace("(", "").replace(")", "")
    without_aside = _TRAILING_ASIDE_PATTERN.sub("", without_parens)
    return re.sub(r"\s+", " ", without_aside).strip(" ,")


def _singularize(word: str) -> str:
    """Best-effort singularization of a single word for dedup purposes only.

    Deliberately conservative: leaves short words and words ending in "ss"/"us"
    alone (e.g. "hummus", "grass") to avoid mangling names that only happen to
    end in "s".
    """
    lowered = word.lower()
    if len(word) <= 3 or lowered.endswith(("ss", "us")):
        return word
    if lowered.endswith("ies"):
        return word[:-3] + "y"
    if lowered.endswith("oes"):
        return word[:-2]
    if lowered.endswith("s"):
        return word[:-1]
    return word


def _matching_key(name: str) -> str:
    """Normalize an ingredient name for deduplication across recipes.

    Distinct from the display name: strips parenthetical asides and singularizes
    only the last word, so "garlic clove" and "garlic cloves (minced)" merge into
    one shopping list line while "garlic clove" and "garlic powder" (a genuinely
    different thing to buy) do not.
    """
    cleaned = _strip_parenthetical_asides(name).lower()
    words = cleaned.split(" ")
    if not words or not words[0]:
        return cleaned
    words[-1] = _singularize(words[-1])
    return " ".join(words)


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


# Cooking fractions rarely need a finer denominator than eighths (1/2, 1/3, 2/3, 1/4,
# 3/4, 1/8, ... and their sums), so cap the reconstructed fraction there.
_MAX_FRACTION_DENOMINATOR = 8


def _format_amount(value: float) -> str:
    """Format a combined amount for display.

    Whole numbers print bare. A value that is a clean small-denominator fraction (or a
    sum of them, e.g. 1/3 + 1/3 -> "2/3") prints as a fraction — "2/3", "1 1/2" — rather
    than the long decimal ``f"{value:g}"`` used to emit (e.g. "0.666667"; issue #30).
    Anything that isn't a clean fraction falls back to at most two decimal places.
    """
    rounded = round(value)
    if abs(value - rounded) < 1e-9:
        return str(rounded)
    fraction = Fraction(value).limit_denominator(_MAX_FRACTION_DENOMINATOR)
    if fraction.denominator != 1 and abs(float(fraction) - value) < 1e-6:
        whole, remainder = divmod(fraction.numerator, fraction.denominator)
        fraction_text = f"{remainder}/{fraction.denominator}"
        return f"{whole} {fraction_text}" if whole else fraction_text
    return f"{round(value, 2):g}"


def _normalize_unit(unit: str) -> str:
    """Singularize a unit for comparison, e.g. "cups" and "cup" both -> "cup"."""
    return unit[:-1] if len(unit) > 1 and unit.endswith("s") else unit


def _pluralize_unit(unit: str, amount: float) -> str:
    # Amounts of one or less stay singular ("1 cup", "2/3 cup"); only genuine plurals
    # (> 1) get an "s".
    if not unit or amount <= 1:
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
    available = {_matching_key(item.name) for item in inventory}
    names: dict[str, str] = {}
    categories: dict[str, Category] = {}
    quantities: dict[str, list[str]] = {}

    for menu_item in menu:
        for ingredient_line in menu_item.recipe.ingredients:
            raw_name, quantity = _parse_ingredient_line(ingredient_line)
            name = _strip_parenthetical_asides(raw_name)
            if not name:
                continue
            key = _matching_key(name)
            if key not in names:
                names[key] = name
                categories[key] = _categorize(name)
                quantities[key] = []
            if quantity:
                quantities[key].append(quantity)

    needed = {
        key: ShoppingListItem(
            name=name,
            quantity=_combine_quantities(quantities[key]),
            category=categories[key].value,
            already_have=key in available,
            optional=categories[key] == Category.SPICES_AND_SAUCES,
        )
        for key, name in names.items()
    }

    return sorted(
        needed.values(),
        key=lambda item: (item.category, item.already_have, item.name.lower()),
    )
