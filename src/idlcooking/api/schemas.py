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
