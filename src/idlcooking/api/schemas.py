from pydantic import BaseModel, Field


class ProfilePayload(BaseModel):
    household_size: int = Field(default=1, ge=1, le=12)
    cooking_effort_minutes: int = Field(default=20, ge=5, le=120)
    allergies: list[str] = Field(default_factory=list)
    hard_restrictions: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    favorite_tags: list[str] = Field(default_factory=list)
    activity_level: str = "light"
    nutrition_goal: str = "maintain"


class ProfileResponse(ProfilePayload):
    telegram_user_id: int


class InventoryItemPayload(BaseModel):
    name: str
    category: str = "other"
    urgency: int = Field(default=0, ge=0, le=3)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)


class GeneratePlanPayload(BaseModel):
    inventory: list[InventoryItemPayload] = Field(default_factory=list)
    days: int = Field(default=7, ge=1, le=7)


class MenuItemResponse(BaseModel):
    day_index: int
    meal_type: str
    title: str
    source_url: str
    active_time_minutes: int
    score: float
    reason: str


class ShoppingListItemResponse(BaseModel):
    name: str
    category: str
    already_have: bool
    optional: bool


class GeneratedPlanResponse(BaseModel):
    telegram_user_id: int
    planning_cycle_id: int
    menu: list[MenuItemResponse]
    shopping_list: list[ShoppingListItemResponse]
