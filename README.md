# I don't like cooking

Telegram-first meal planning service for people who do not enjoy cooking but still need affordable, low-effort, reasonably healthy meals.

The service creates a weekly menu and shopping list on a configurable schedule, uses refrigerator photos to reduce food waste, learns user preferences from feedback, and prioritizes simple recipes with balanced macronutrients.

## Current Stage

Product discovery and technical requirements.

Start with:

- [Product requirements](docs/product-requirements.md)

## Proposed Form

The recommended first version is not a standalone mobile app. It is a lightweight Telegram bot plus a small backend service:

- Telegram is the user interface for onboarding, reminders, weekly plans, shopping lists, and feedback.
- The backend stores user profiles, schedules, menus, feedback, and recipe metadata.
- A local Ollama-based image recognition adapter can run on the user's machine for private refrigerator photo analysis.

This keeps user setup minimal, avoids mobile app maintenance, and allows the service to start cheaply.
