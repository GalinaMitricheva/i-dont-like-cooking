from dataclasses import dataclass

from idlcooking.domain.planning import InventoryItem, MenuItem


@dataclass(frozen=True)
class ShoppingListItem:
    name: str
    category: str = "other"
    already_have: bool = False
    optional: bool = False


def build_shopping_list(
    menu: list[MenuItem],
    inventory: tuple[InventoryItem, ...] = (),
) -> list[ShoppingListItem]:
    available = {item.name.lower() for item in inventory}
    needed: dict[str, ShoppingListItem] = {}

    for menu_item in menu:
        for ingredient in menu_item.recipe.ingredients:
            normalized = ingredient.strip().lower()
            if not normalized or normalized in needed:
                continue
            needed[normalized] = ShoppingListItem(
                name=ingredient.strip(),
                already_have=normalized in available,
            )

    return sorted(needed.values(), key=lambda item: (item.already_have, item.name.lower()))
