from dataclasses import dataclass
from enum import StrEnum


class CookedStatus(StrEnum):
    COOKED = "cooked"
    SKIPPED = "skipped"
    REPLACED = "replaced"


class Rating(StrEnum):
    LIKED = "liked"
    NEUTRAL = "neutral"
    DISLIKED = "disliked"


@dataclass(frozen=True)
class RecipeFeedback:
    recipe_source_url: str
    recipe_title: str
    cooked_status: CookedStatus
    rating: Rating
    effort_feedback: str | None = None
    cost_feedback: str | None = None
    notes: str = ""
