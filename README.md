# I don't like cooking

Telegram-first meal planning service for people who do not enjoy cooking but still need affordable, low-effort, reasonably healthy meals.

The service creates a weekly menu and shopping list on a configurable schedule, learns user preferences from feedback, and prioritizes simple recipes with balanced macronutrients. Refrigerator-photo recognition is part of the product vision but not implemented yet (see Known Gaps below).

## Current Stage

The MVP is implemented. The Telegram bot supports the full weekly planning loop end to end:

- Consent and a one-time onboarding questionnaire (household size, cooking effort, allergies/restrictions/dislikes, budget, activity level, nutrition goal, optional body metrics).
- A configurable weekly planning schedule, with a background scheduler that automatically triggers and sends a plan when a user's day/time arrives.
- Weekly plan generation anchored on lunch, with optional dinner leftovers (reusing the same day's lunch) and optional breakfast, drawn from a recipe pool that's scraped from a curated set of real recipe sites and cached in SQLite, falling back to a small bundled recipe set if scraping is unavailable.
- A categorized, quantity-aware shopping list (produce/protein/dairy and eggs/grains and bakery/frozen/spices and sauces/other), with quantities summed across recipes where units match.
- A day-by-day recipe viewer (ingredients, steps summary, source link) with Previous/Next navigation.
- An end-of-cycle feedback command that re-ranks future plans based on what you liked or disliked.
- Data deletion on request.

See [Product requirements](docs/product-requirements.md) for the full product vision, and the repository's GitHub issues for what's shipped vs. still planned. The "MVP v0.1" milestone is fully closed; everything tracked after it is a refinement or a deliberately deferred later-milestone feature (local fridge-photo vision, structured logging, schema migrations, and recipe pool growth).

## Bot Commands

- `/start` — consent, then (first time only) the onboarding questionnaire.
- `/plan [inventory]` — asks how many days to plan for and which meals to include (lunch only / + breakfast / + dinner leftovers / all three), then generates a draft plan. A draft offers Accept menu, Regenerate, Show shopping list, and View recipes; once accepted, Accept/Regenerate drop away and Rate your meals appears. Optionally list food you already have, e.g. `/plan rice, eggs, cucumber`.
- `/schedule` — show the current weekly planning schedule. `/schedule <weekday> <HH:MM> [timezone]` (e.g. `/schedule saturday 09:00 Europe/Berlin`) to change it.
- `/profile` — view the saved profile.
- `/feedback` — rate the latest plan's meals one at a time (liked / okay / too much effort / too expensive / didn't cook it); feeds into future recipe ranking.
- `/fridge` — currently a placeholder pointing at typing inventory into `/plan`; photo-based fridge recognition is not implemented (see Known Gaps).
- `/delete_my_data` — permanently delete profile, schedule, planning history, and feedback, with a confirmation step.

## Proposed Form

The recommended first version is not a standalone mobile app. It is a lightweight Telegram bot plus a small backend service:

- Telegram is the user interface for onboarding, reminders, weekly plans, shopping lists, and feedback.
- The backend stores user profiles, schedules, menus, feedback, and recipe metadata.
- A local Ollama-based image recognition adapter is planned to run on the user's machine for private refrigerator photo analysis (not implemented yet).

This keeps user setup minimal, avoids mobile app maintenance, and allows the service to start cheaply.

The MVP bot speaks English first. Bot messages go through a small localization layer so additional languages can be added later without rewriting conversation handlers.

## Repository Layout

```text
src/idlcooking/
  api/          FastAPI app entrypoint
  bot/          Telegram bot entrypoint, handlers, i18n, and the TelegramPlanningFacade
  domain/       Pure planning, profile, schedule, shopping, and feedback logic
  services/     External adapters: web recipe discovery (recipe-scrapers) and the future
                local Ollama vision contract
  storage/      SQLite schema and repositories
  scheduler.py  Scheduled job that triggers weekly planning cycles
tests/          Unit and integration-style tests (no live network calls)
```

## Local Development

Requirements:

- Python 3.11+
- A Telegram bot token for bot polling

Create a virtual environment and install dependencies:

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -e ".[dev]"
```

Copy `.env.example` to `.env` and fill `TELEGRAM_BOT_TOKEN` when you want to run the bot.

Run the backend API:

```bash
uvicorn idlcooking.api.main:app --reload
```

Health checks:

- `GET /health`
- `GET /ready`

Create or update a Telegram user's planning profile:

```bash
curl -X PUT http://127.0.0.1:8000/telegram-users/12345/profile ^
  -H "Content-Type: application/json" ^
  -d "{\"household_size\":1,\"cooking_effort_minutes\":20,\"allergies\":[],\"hard_restrictions\":[],\"disliked_ingredients\":[\"cilantro\"],\"favorite_tags\":[\"simple\"],\"budget_level\":\"moderate\",\"activity_level\":\"light\",\"nutrition_goal\":\"reduce_waste\"}"
```

Generate and persist a weekly plan:

```bash
curl -X POST http://127.0.0.1:8000/telegram-users/12345/plan ^
  -H "Content-Type: application/json" ^
  -d "{\"inventory\":[{\"name\":\"rice\",\"urgency\":2},{\"name\":\"eggs\"}],\"days\":7,\"include_dinner_leftovers\":true}"
```

Run the Telegram bot:

```bash
python -m idlcooking.bot.main
```

Run tests:

```bash
pytest
```

### A note on the local database

`storage/database.py` only ever runs `CREATE TABLE IF NOT EXISTS` — there is no migration system yet (tracked as a known gap). If you pull a change that adds or renames a column and your bot starts throwing `sqlite3.OperationalError: no such column: ...`, stop the bot, delete `data/idlcooking.sqlite3`, and restart it to regenerate the schema from scratch. This is local dev data only; there is no production deployment yet.

## Implemented Domain Rules

- Weekly schedule calculation (`next_run_after` / `latest_occurrence_before_or_at`), defaulting to Saturday 09:00 in the configured timezone, with idempotent scheduler triggering (a schedule only fires once per occurrence, tracked via `last_triggered_at`, and retries automatically if a send fails).
- Optional calorie estimation using Mifflin-St Jeor when the user provides body metrics.
- Weighted recipe scoring that excludes allergies/restrictions/dislikes and disliked-via-feedback recipes, rewards low effort and inventory matches, favors favorite tags and liked-via-feedback recipes, and boosts high-protein recipes.
- Multi-meal-type planning: lunch (always, the primary anchor meal), optional dinner as a same-day leftover of that day's lunch (no extra shopping), and optional breakfast. Meal selection cycles through the ranked candidate pool so every requested day is filled, with no adjacent-day repeats unless only a single recipe is available; breakfast prefers recipes tagged "breakfast" and falls back to the general pool if nothing is tagged.
- Shopping-list generation with best-effort quantity parsing from free-text ingredient lines, quantities summed across recipes when units match, category grouping (produce/protein/dairy and eggs/grains and bakery/pantry/frozen/spices and sauces/other), and spices/sauces marked optional.
- Web recipe discovery via `recipe-scrapers` against a curated allow-list of verified recipe URLs, cached in SQLite so repeat plans don't re-scrape, with a bundled seed-recipe fallback if discovery fails entirely.
- End-of-cycle feedback (liked/neutral/disliked/too much effort/too expensive/skipped) that adjusts future recipe ranking per user.
- SQLite persistence for Telegram users, profiles, schedules, generated planning cycles, menu items (including recipe steps summaries), shopping list items, cached discovered recipes, and feedback.

## Known Gaps

Tracked as GitHub issues rather than silently left undocumented:

- Local Ollama vision integration and fridge-photo intake are not implemented; inventory is entered as text via `/plan`.
- No schema migration system (see the note above).
- Ingredient-name matching for the shopping list is exact-after-quantity-stripping, so the same ingredient described differently across recipes (e.g. "garlic clove" vs. "garlic powder") doesn't always merge into one line.
- The curated recipe pool is still relatively small and unevenly distributed across meal types/categories.
- A few flows still lack a Back affordance to exit cleanly (e.g. the first "Rate your meals" prompt).
