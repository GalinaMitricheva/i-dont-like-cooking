from idlcooking.services.recipe_discovery import RecipeDiscoveryService, _parse_servings


class _FakeScraper:
    def __init__(
        self,
        title: str,
        ingredients: list[str],
        total_time: int | None,
        instructions: str = "",
        category: str | None = None,
        yields: str | None = None,
    ) -> None:
        self._title = title
        self._ingredients = ingredients
        self._total_time = total_time
        self._instructions = instructions
        self._category = category
        self._yields = yields

    def title(self) -> str:
        return self._title

    def ingredients(self) -> list[str]:
        return self._ingredients

    def total_time(self) -> int | None:
        if self._total_time is None:
            raise ValueError("total_time not available")
        return self._total_time

    def instructions(self) -> str:
        return self._instructions

    def category(self) -> str | None:
        return self._category

    def yields(self) -> str | None:
        if self._yields is None:
            raise ValueError("yields not available")
        return self._yields


def test_discover_parses_and_sanitizes_recipes() -> None:
    scrapers = {
        "https://example.com/rice": _FakeScraper(
            title="  <b>Fast Rice</b>  ",
            ingredients=["rice", "<i>eggs</i>"],
            total_time=12,
            instructions="Cook rice. Fry eggs. Combine.",
            category="Dinner, Simple",
        ),
    }
    service = RecipeDiscoveryService(
        source_urls=tuple(scrapers),
        scraper_factory=lambda url: scrapers[url],
    )

    discovered = service.discover()

    assert len(discovered) == 1
    recipe = discovered[0]
    assert recipe.title == "Fast Rice"
    assert recipe.ingredients == ("rice", "eggs")
    assert recipe.active_time_minutes == 12
    assert recipe.tags == ("Dinner", "Simple")
    assert recipe.steps_summary == "Cook rice. Fry eggs. Combine."
    assert recipe.source_url == "https://example.com/rice"


def test_discover_skips_urls_that_fail_to_scrape() -> None:
    def scraper_factory(url: str) -> _FakeScraper:
        if url == "https://example.com/broken":
            raise RuntimeError("404")
        return _FakeScraper(title="Soup", ingredients=["lentils"], total_time=15)

    service = RecipeDiscoveryService(
        source_urls=("https://example.com/broken", "https://example.com/soup"),
        scraper_factory=scraper_factory,
    )

    discovered = service.discover()

    assert [recipe.source_url for recipe in discovered] == ["https://example.com/soup"]


def test_parse_servings_reads_messy_yields() -> None:
    # Issue #39: yields arrive as free text; take the first integer (low end of a range).
    assert _parse_servings("4 servings") == 4
    assert _parse_servings("Serves 4-6") == 4
    assert _parse_servings("Makes 12") == 12
    assert _parse_servings("a few") is None
    assert _parse_servings(None) is None


def test_discover_captures_servings_from_yields() -> None:
    scrapers = {
        "https://example.com/tray": _FakeScraper(
            title="Chicken tray",
            ingredients=["chicken"],
            total_time=18,
            yields="4 servings",
        ),
        "https://example.com/solo": _FakeScraper(
            title="Single omelet", ingredients=["eggs"], total_time=8
        ),
    }
    service = RecipeDiscoveryService(
        source_urls=tuple(scrapers), scraper_factory=lambda url: scrapers[url]
    )

    discovered = {recipe.source_url: recipe for recipe in service.discover()}

    assert discovered["https://example.com/tray"].servings == 4
    # A missing yield degrades gracefully to unknown rather than aborting the scrape.
    assert discovered["https://example.com/solo"].servings is None


def test_discover_falls_back_to_default_active_time_when_missing() -> None:
    scrapers = {
        "https://example.com/mystery": _FakeScraper(
            title="Mystery Dish", ingredients=["mystery"], total_time=None
        ),
    }
    service = RecipeDiscoveryService(
        source_urls=tuple(scrapers),
        scraper_factory=lambda url: scrapers[url],
    )

    discovered = service.discover()

    assert discovered[0].active_time_minutes == 30
