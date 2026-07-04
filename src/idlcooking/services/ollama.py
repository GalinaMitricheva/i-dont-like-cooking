from dataclasses import dataclass


@dataclass(frozen=True)
class RecognizedFoodItem:
    name: str
    category: str
    state: str = "unknown"
    confidence: float = 0.0
    urgency: int = 0


class OllamaVisionAdapter:
    """Placeholder contract for the local Ollama refrigerator recognition adapter."""

    def __init__(self, base_url: str, model: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model

    async def recognize_food(self, image_bytes: bytes) -> list[RecognizedFoodItem]:
        if not image_bytes:
            return []
        raise NotImplementedError("Ollama HTTP integration will be added in the vision milestone.")
