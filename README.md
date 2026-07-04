# I don't like cooking

Telegram-first meal planning service for people who do not enjoy cooking but still need affordable, low-effort, reasonably healthy meals.

The service creates a weekly menu and shopping list on a configurable schedule, uses refrigerator photos to reduce food waste, learns user preferences from feedback, and prioritizes simple recipes with balanced macronutrients.

## Current Stage

Initial engineering scaffold.

Start with:

- [Product requirements](docs/product-requirements.md)

## Proposed Form

The recommended first version is not a standalone mobile app. It is a lightweight Telegram bot plus a small backend service:

- Telegram is the user interface for onboarding, reminders, weekly plans, shopping lists, and feedback.
- The backend stores user profiles, schedules, menus, feedback, and recipe metadata.
- A local Ollama-based image recognition adapter can run on the user's machine for private refrigerator photo analysis.

This keeps user setup minimal, avoids mobile app maintenance, and allows the service to start cheaply.

The MVP bot speaks English first. Bot messages go through a small localization layer so additional languages can be added later without rewriting conversation handlers.

## Repository Layout

```text
src/idlcooking/
  api/          FastAPI app entrypoint
  bot/          Telegram bot entrypoint and handlers
  domain/       Pure scheduling, profile, planning, and shopping-list logic
  services/     External adapters, starting with the local Ollama vision contract
  scheduler.py  Scheduled job setup
tests/          Unit tests for domain behavior
```

## Local Development

Requirements:

- Python 3.11+
- A Telegram bot token for bot polling
- Optional: local Ollama with a vision-capable model for the future fridge-photo adapter

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
  -d "{\"household_size\":1,\"cooking_effort_minutes\":20,\"allergies\":[],\"hard_restrictions\":[],\"disliked_ingredients\":[\"cilantro\"],\"favorite_tags\":[\"simple\"],\"activity_level\":\"light\",\"nutrition_goal\":\"reduce_waste\"}"
```

Generate and persist a first deterministic weekly plan:

```bash
curl -X POST http://127.0.0.1:8000/telegram-users/12345/plan ^
  -H "Content-Type: application/json" ^
  -d "{\"inventory\":[{\"name\":\"rice\",\"urgency\":2},{\"name\":\"eggs\"}],\"days\":7}"
```

Run the Telegram bot:

```bash
python -m idlcooking.bot.main
```

Run tests:

```bash
pytest
```

## First Implemented Domain Rules

- Weekly schedule calculation, defaulting to Saturday 09:00 in the configured timezone.
- Optional calorie estimation using Mifflin-St Jeor when the user provides body metrics.
- Deterministic recipe scoring that excludes allergies/restrictions/dislikes, rewards low effort, and prefers recipes using current inventory.
- Shopping-list generation that marks already available ingredients.
- SQLite persistence for Telegram users, profiles, schedules, generated planning cycles, menu items, and shopping list items.
