import logging
import re
from collections.abc import Callable
from typing import Protocol

from idlcooking.domain.planning import RecipeCandidate

logger = logging.getLogger(__name__)

_HTML_TAG_RE = re.compile(r"<[^>]+>")
_MAX_FIELD_LENGTH = 500
_FALLBACK_ACTIVE_TIME_MINUTES = 30

# Small curated allow-list of simple, low-effort recipes, verified to parse cleanly with
# recipe-scrapers. Scraping the open web is inherently unreliable (pages 404, get rate
# limited, or change markup), which is exactly why discovered recipes are cached in the
# `recipes` table and SEED_RECIPES exists as a last-resort fallback (see RecipeDiscoveryService
# and TelegramPlanningFacade._recipe_pool).
CURATED_RECIPE_URLS: tuple[str, ...] = (
    "https://www.allrecipes.com/recipe/16354/easy-meatloaf/",
    "https://www.allrecipes.com/recipe/158968/spinach-and-feta-turkey-burgers/",
    "https://www.bbcgoodfood.com/recipes/easy-pancakes",
    "https://cookieandkate.com/best-guacamole-recipe/",
    "https://www.loveandlemons.com/lentil-soup/",
    "https://www.loveandlemons.com/hummus-recipe/",
)


class ScrapedRecipe(Protocol):
    def title(self) -> str: ...
    def ingredients(self) -> list[str]: ...
    def total_time(self) -> int | None: ...
    def instructions(self) -> str: ...
    def category(self) -> str | None: ...


def _sanitize(text: str, max_length: int = _MAX_FIELD_LENGTH) -> str:
    text = _HTML_TAG_RE.sub("", text or "")
    text = " ".join(text.split())
    return text[:max_length]


def _summarize_instructions(instructions: str) -> str:
    return _sanitize(instructions, max_length=200)


def _default_scraper_factory(url: str) -> ScrapedRecipe:
    from recipe_scrapers import scrape_me

    return scrape_me(url)


class RecipeDiscoveryError(Exception):
    """Raised when a single recipe page cannot be fetched or parsed."""


class RecipeDiscoveryService:
    """Fetches and parses recipes from a curated URL allow-list via recipe-scrapers.

    Failures are per-URL and non-fatal: a broken or blocked page is skipped and logged
    rather than aborting the whole discovery run, matching the product's reliability
    requirement to degrade gracefully when recipe search fails.
    """

    def __init__(
        self,
        source_urls: tuple[str, ...] = CURATED_RECIPE_URLS,
        scraper_factory: Callable[[str], ScrapedRecipe] = _default_scraper_factory,
    ) -> None:
        self.source_urls = source_urls
        self._scraper_factory = scraper_factory

    def discover(self) -> list[RecipeCandidate]:
        discovered: list[RecipeCandidate] = []
        for url in self.source_urls:
            try:
                discovered.append(self._scrape_one(url))
            except Exception:
                logger.warning("Failed to scrape recipe from %s", url, exc_info=True)
        return discovered

    def _scrape_one(self, url: str) -> RecipeCandidate:
        try:
            scraper = self._scraper_factory(url)
            title = scraper.title()
            ingredients = scraper.ingredients()
        except Exception as exc:
            raise RecipeDiscoveryError(f"Could not scrape {url}") from exc

        try:
            active_time_minutes = int(scraper.total_time())
        except Exception:
            active_time_minutes = _FALLBACK_ACTIVE_TIME_MINUTES

        try:
            category = scraper.category() or ""
        except Exception:
            category = ""

        try:
            steps_summary = _summarize_instructions(scraper.instructions())
        except Exception:
            steps_summary = ""

        return RecipeCandidate(
            title=_sanitize(title, max_length=200),
            source_url=url,
            ingredients=tuple(_sanitize(item, max_length=200) for item in ingredients if item),
            active_time_minutes=active_time_minutes,
            tags=tuple(_sanitize(tag) for tag in category.split(",") if tag.strip()),
            steps_summary=steps_summary,
        )
