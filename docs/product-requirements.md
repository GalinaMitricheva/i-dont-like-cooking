# I don't like cooking: Product Requirements and Technical Architecture

## 1. Product Summary

`I don't like cooking` helps people who dislike cooking but still need to cook regularly because delivery, restaurants, or ready meals are too expensive, inconvenient, unhealthy, or undesirable.

The product is best shaped as a Telegram-first meal planning service rather than a classical app. The user interacts with a Telegram bot for onboarding, fridge photo uploads, schedule settings, weekly menu approval, shopping lists, cooking reminders, and end-of-cycle feedback. A lightweight backend agent generates the plan, stores preferences, and coordinates recipe search. A local Ollama model on the user's machine recognizes refrigerator photos when the user chooses privacy-preserving local analysis.

Primary promise:

> Every planning cycle, the user receives a low-effort, affordable, reasonably healthy menu and a shopping list that uses what they already have.

## 2. Target Users

### Primary User

An adult who:

- Does not enjoy cooking.
- Needs to cook several times per week.
- Wants meals that are easy, reliable, and not too expensive.
- Wants less food waste.
- Is willing to answer short Telegram questionnaires.
- Can send photos of refrigerator contents.

### Secondary Users

- People with basic fitness or nutrition goals who need approximate calorie and macro balance.
- People living alone or in pairs who often waste ingredients.
- Busy users who want "good enough" meal planning without becoming food enthusiasts.

## 3. Product Principles

1. Minimize effort.
   The service should ask short questions, offer defaults, and avoid making the user manage a complex recipe database.

2. Prefer good enough nutrition over precision.
   The goal is reasonable macro balance, not medical dietetics.

3. Reuse food before buying more.
   Existing prepared dishes and expiring ingredients should influence the next menu.

4. Learn quietly.
   Feedback should improve future menus without turning into a long review process.

5. Use Telegram as the main UI.
   No separate app is needed for the MVP.

6. Keep costs low.
   Use scheduled jobs, a small database, recipe metadata caching, and optional local Ollama for image recognition.

## 4. Scope

### MVP Scope

- Telegram bot onboarding.
- User profile questionnaire.
- Configurable weekly planning schedule, default Saturday morning.
- Fridge photo request before planning.
- Local Ollama image recognition integration through a local companion service or manual upload workflow.
- Weekly menu generation.
- Shopping list generation.
- Recipe search and recipe metadata extraction from public pages.
- Preference, allergy, and disliked ingredient constraints.
- Approximate calorie and macronutrient targeting.
- End-of-cycle feedback survey.
- Saving liked dishes and suppressing disliked dishes.
- Simple admin/developer logs.

### Explicitly Out of Scope for MVP

- Native iOS/Android app.
- Real-time grocery delivery integration.
- Exact medical nutrition plans.
- Paid recipe subscriptions.
- Complex pantry inventory with barcode scanning.
- Multi-user household roles.
- Automatic payment infrastructure.
- Fully autonomous browser scraping of every recipe site.

## 5. Key User Journeys

### Journey A: First-Time Onboarding

1. User opens Telegram bot.
2. Bot explains the service briefly and asks for consent to store profile and planning data.
3. Bot asks questionnaire:
   - Household size.
   - Meals to plan: breakfasts, lunches, dinners, snacks.
   - Cooking tolerance: "almost no cooking", "15 minutes", "30 minutes", "batch cooking is okay".
   - Allergies and hard restrictions.
   - Disliked ingredients.
   - Favorite cuisines or known safe dishes.
   - Budget sensitivity.
   - Physical activity level.
   - Goal: maintain, lose, gain, eat more regularly, reduce waste.
   - Height, weight, age, sex only if the user wants calorie estimates.
4. Bot proposes a default planning schedule: Saturday morning.
5. User confirms or changes schedule.
6. Bot asks for a first refrigerator photo or allows skipping.
7. Bot creates first menu and shopping list.

### Journey B: Weekly Planning Cycle

1. Before the scheduled planning time, bot asks the user to photograph the fridge, freezer, pantry, or leftovers.
2. User sends one or more photos.
3. The photo recognition adapter extracts likely items and confidence levels.
4. Bot asks the user to quickly confirm uncertain items.
5. Service checks expiring or already prepared food.
6. Service generates menu options for the next week.
7. Bot sends:
   - Weekly menu summary.
   - Shopping list grouped by store sections.
   - Short notes about what existing food is used.
8. User can accept, regenerate, remove a dish, or mark an item as already available.

### Journey C: Cooking Day

1. Bot sends a short reminder for a planned meal if reminders are enabled.
2. User opens recipe steps from Telegram.
3. Bot shows:
   - Ingredients.
   - Minimal steps.
   - Link to source recipe.
   - Prep time and cooking time.
   - Possible shortcuts.
4. User can mark meal as cooked, skipped, replaced, or too much effort.

### Journey D: End-of-Cycle Feedback

1. At the end of the cycle, bot asks for quick feedback:
   - Which meals were cooked?
   - Which were liked?
   - Which were too much effort?
   - Which ingredients were wasted?
   - Was the shopping list accurate?
2. Bot stores liked dishes for reuse.
3. Bot reduces future ranking of disliked or skipped dishes.
4. Bot adjusts planning assumptions.

### Journey E: Schedule Change

1. User sends "change schedule" or uses a Telegram button.
2. Bot shows current schedule.
3. User chooses weekday, time, and timezone.
4. Future planning jobs use the new schedule.

## 6. Functional Requirements

### 6.1 Telegram Interface

- The bot must start in English and keep message handling structured so more languages can be added later.
- The bot must provide button-based choices where possible.
- The bot must allow free text for allergies, dislikes, and corrections.
- The bot must send scheduled reminders.
- The bot must support multiple photos per planning cycle.
- The bot must keep messages concise and action-oriented.

### 6.2 User Profile

The system must store:

- Telegram user ID.
- Preferred language.
- Timezone.
- Planning schedule.
- Household size.
- Meal count preferences.
- Cooking effort tolerance.
- Allergies.
- Hard dietary restrictions.
- Disliked ingredients.
- Favorite ingredients, cuisines, and dishes.
- Budget sensitivity.
- Nutrition goal.
- Optional height, weight, age, sex, activity level.
- Liked and disliked recipe history.

### 6.3 Nutrition Estimation

The system should estimate daily calorie targets using a common formula such as Mifflin-St Jeor when sufficient user data exists.

The system should support approximate macro ranges:

- Protein: enough to make meals filling.
- Fat: moderate.
- Carbohydrates: flexible.
- Fiber and vegetables: encouraged.

The system must label nutrition as approximate and non-medical.

### 6.4 Refrigerator Recognition

The system must accept refrigerator, freezer, pantry, and leftovers photos.

The preferred privacy-preserving implementation:

- User runs a small local companion process.
- Telegram receives the photo.
- Backend sends the image to the user's local adapter only if connectivity is configured, or the user uploads the image directly to the local adapter.
- Local adapter calls Ollama vision model.
- Adapter returns structured JSON with likely items.

Recognized item fields:

- Item name.
- Category.
- Estimated quantity.
- State: raw, cooked, packaged, leftover, unknown.
- Confidence.
- Possible expiry urgency.

The bot must ask for confirmation when confidence is low.

### 6.5 Recipe Discovery

The system should find recipes online and prefer pages with:

- Clear ingredients.
- Step-by-step instructions.
- Photos for steps when available.
- Low active cooking time.
- Common ingredients.
- Good source reliability.
- Nutrition data when available.

The system must store only metadata and links unless source terms allow more.

The system should cache:

- Recipe title.
- Source URL.
- Ingredients.
- Parsed steps or summary.
- Estimated active time.
- Estimated total time.
- Difficulty score.
- Nutrition estimate.
- Tags.
- User feedback.

### 6.6 Menu Generation

Menu generation must consider:

- User profile.
- Schedule.
- Existing fridge items.
- Leftovers and expiring food.
- Allergies and hard exclusions.
- Disliked ingredients and disliked recipes.
- Liked recipes.
- Budget sensitivity.
- Cooking effort tolerance.
- Macro and calorie targets.
- Ingredient reuse across recipes.
- Meal variety.

The generated menu should include:

- Days and meals.
- Recipes or simple meal formulas.
- Ingredient quantities.
- Prep-ahead suggestions only when they reduce effort.
- Leftover usage notes.

### 6.7 Shopping List

The shopping list must:

- Exclude confirmed existing items.
- Include quantities where possible.
- Group items by category.
- Mark optional items.
- Mark items already likely available but needing confirmation.
- Be editable from Telegram.

Categories:

- Produce.
- Protein.
- Dairy and eggs.
- Grains and bakery.
- Pantry.
- Frozen.
- Spices and sauces.
- Other.

### 6.8 Feedback and Learning

The system must record:

- Cooked, skipped, replaced.
- Liked, neutral, disliked.
- Too much effort.
- Too expensive.
- Too much food.
- Too little food.
- Ingredient waste.
- Shopping list missing items.

The system should use feedback to:

- Increase rank of liked recipes.
- Decrease or exclude disliked recipes.
- Lower effort threshold if user frequently skips.
- Adjust portion assumptions.
- Avoid repeated problem ingredients.

## 7. Non-Functional Requirements

### Cost

The MVP should run on a low-cost server or free tier:

- Small backend process.
- PostgreSQL or SQLite for earliest prototype.
- Scheduled worker.
- Telegram Bot API.
- Optional local image processing.

### Privacy

- Store only data needed for planning.
- Treat health, allergies, and body metrics as sensitive.
- Keep photo processing local where possible.
- Allow user data deletion.
- Avoid storing raw fridge photos longer than necessary.

### Reliability

- Scheduled jobs must be idempotent.
- If recipe search fails, use cached recipes.
- If image recognition fails, ask user to manually list available food.
- If Telegram delivery fails, retry with backoff.

### Security

- Protect bot token and API keys.
- Use per-user authorization for local adapter pairing.
- Sanitize recipe page content.
- Do not execute scraped content.

### Maintainability

- Keep Telegram bot, planning engine, recipe search, nutrition, and local vision adapter as separate modules.
- Use structured JSON contracts between modules.
- Add tests around planning constraints and schedule behavior.

## 8. Recommended Technical Architecture

### Recommended Product Form

Build a Telegram-first service with an optional local companion.

This is better than a native app for the first version because:

- Telegram already handles notifications, photo upload, and simple forms.
- Users do not need to install another app.
- The backend can stay small.
- Local Ollama can be integrated only for users who want private photo recognition.
- Iteration is faster.

### High-Level Components

1. Telegram Bot
   - User conversations.
   - Questionnaires.
   - Photo intake.
   - Buttons and commands.
   - Reminders.

2. Backend API
   - User profile storage.
   - Planning cycle orchestration.
   - Menu and shopping list persistence.
   - Feedback storage.

3. Scheduler and Worker
   - Runs weekly planning jobs.
   - Sends reminders.
   - Retries failed jobs.

4. Planning Engine
   - Builds constraints.
   - Selects recipes.
   - Balances effort, nutrition, budget, and waste reduction.
   - Produces menu and shopping list.

5. Recipe Discovery Service
   - Searches web sources.
   - Parses recipe pages.
   - Extracts structured recipe metadata.
   - Caches recipe records.

6. Nutrition Service
   - Estimates calorie targets.
   - Estimates macros for recipes and menus.
   - Marks estimates as approximate.

7. Local Ollama Vision Adapter
   - Runs on user's machine.
   - Sends image prompts to Ollama.
   - Returns structured inventory guesses.

8. Database
   - Stores users, preferences, cycles, recipes, inventory items, menus, shopping lists, and feedback.

### Suggested Stack for MVP

- Language: Python.
- Telegram framework: aiogram.
- API: FastAPI.
- Scheduler: APScheduler for prototype, later Celery/RQ if needed.
- Database: PostgreSQL for hosted MVP, SQLite acceptable for local prototype.
- ORM: SQLAlchemy or SQLModel.
- Migrations: Alembic.
- Recipe parsing: recipe-scrapers library plus custom fallback parsers.
- Web search: pluggable provider, initially manual/cached or search API if available.
- Local vision: Ollama HTTP API with a vision-capable model.
- Deployment: one small VPS, Fly.io, Render, Railway, or similar low-cost host.
- Observability: structured logs plus basic error alerts.

### Data Flow: Weekly Planning

1. Scheduler finds users whose planning time has arrived.
2. Bot asks for fridge photos.
3. User sends photos or skips.
4. Vision adapter recognizes inventory.
5. Bot asks user to confirm uncertain inventory.
6. Planning engine builds constraints.
7. Recipe discovery returns candidate recipes.
8. Planning engine ranks and selects meals.
9. Shopping list service subtracts inventory.
10. Bot sends menu and shopping list.
11. User accepts or asks for changes.
12. End-of-cycle feedback updates preferences.

## 9. Core Data Model

### User

- id
- telegram_user_id
- language
- timezone
- created_at
- consent_version

### UserProfile

- user_id
- household_size
- meal_preferences
- cooking_effort_level
- budget_level
- nutrition_goal
- activity_level
- optional_body_metrics

### Preference

- user_id
- type: allergy, hard_restriction, dislike, favorite, cuisine
- value
- strength

### PlanningSchedule

- user_id
- weekday
- time
- timezone
- enabled

### InventoryItem

- user_id
- planning_cycle_id
- name
- category
- quantity
- state
- confidence
- source: photo, manual, previous_cycle
- urgency

### Recipe

- id
- title
- source_url
- ingredients
- steps_summary
- active_time_minutes
- total_time_minutes
- difficulty_score
- nutrition_estimate
- tags
- source_quality_score

### PlanningCycle

- id
- user_id
- start_date
- end_date
- status
- generated_at

### MenuItem

- planning_cycle_id
- date
- meal_type
- recipe_id
- servings
- reason

### ShoppingListItem

- planning_cycle_id
- name
- category
- quantity
- already_have
- optional
- checked

### Feedback

- user_id
- planning_cycle_id
- recipe_id
- cooked_status
- rating
- effort_feedback
- cost_feedback
- notes

## 10. Menu Ranking Logic

Each candidate recipe receives a weighted score:

- Safety score: excludes allergies and hard restrictions.
- Effort score: lower active time and fewer steps rank higher.
- Inventory score: uses current food and leftovers.
- Waste score: uses urgent ingredients.
- Nutrition score: improves weekly macro balance.
- Preference score: matches liked dishes and avoids disliked items.
- Budget score: favors cheaper ingredients and reuse.
- Variety score: avoids repeating the same cuisine or protein too often.
- Reliability score: favors recipes with structured ingredients and clear steps.

For MVP, this can be a deterministic weighted scoring system. Later, user feedback can tune weights per user.

## 11. Telegram Commands and Buttons

### Commands

- `/start` - onboarding or main menu.
- `/plan` - generate or view current plan.
- `/fridge` - upload fridge photos.
- `/schedule` - change planning schedule.
- `/profile` - edit preferences.
- `/feedback` - review last cycle.
- `/delete_my_data` - request data deletion.

### Main Buttons

- Send fridge photo.
- Skip photo.
- Confirm inventory.
- Generate menu.
- Regenerate one meal.
- Accept menu.
- Show shopping list.
- Mark item bought.
- Mark meal cooked.
- Too much effort.
- I liked this.
- Do not suggest again.

## 12. MVP Milestones

### Milestone 1: Product Skeleton

- Repository setup.
- Requirements and architecture docs.
- Basic Telegram bot scaffold.
- User profile questionnaire.
- Database schema.

### Milestone 2: Planning Prototype

- Manual inventory entry.
- Recipe cache seed data.
- Deterministic menu generation.
- Shopping list generation.
- Schedule configuration.

### Milestone 3: Local Vision Prototype

- Local Ollama adapter.
- Photo-to-inventory JSON.
- Telegram confirmation flow.

### Milestone 4: Recipe Discovery

- Recipe URL ingestion.
- Recipe metadata parsing.
- Candidate ranking.
- Source links in menu.

### Milestone 5: Feedback Loop

- End-of-cycle survey.
- Liked and disliked recipe learning.
- Simple personalization.

## 13. Risks and Mitigations

### Recipe Copyright and Terms

Risk: Copying recipe text and photos can violate source terms.

Mitigation:

- Store metadata, short summaries, and links.
- Prefer sources with structured data and permissive terms.
- Avoid storing full copyrighted recipe pages unless allowed.

### Nutrition Accuracy

Risk: Generated nutrition may be inaccurate.

Mitigation:

- Present estimates as approximate.
- Avoid medical claims.
- Let users override portion sizes and goals.

### Fridge Photo Ambiguity

Risk: Photos are incomplete or unclear.

Mitigation:

- Ask for confirmation.
- Support manual corrections.
- Treat low-confidence items as suggestions.

### User Effort Creep

Risk: The product becomes too demanding for people who already dislike cooking.

Mitigation:

- Keep questionnaires short.
- Use defaults.
- Avoid requiring detailed inventory management.
- Make feedback one-tap where possible.

### Web Recipe Quality

Risk: Online recipes vary in complexity and reliability.

Mitigation:

- Score sources.
- Cache successful recipes.
- Let users blacklist recipes.
- Prefer simple, structured recipes.

## 14. Open Product Questions

1. Which additional languages should be added after the English MVP?
2. Should calorie estimation be optional by default to avoid sensitive onboarding?
3. Should the local Ollama adapter be required, or should manual inventory be the default fallback?
4. Should planning cover all meals or start with dinners only?
5. Should the service support strict budgets, for example "up to X per week"?
6. Which recipe sources are acceptable for initial discovery?
7. How much recipe content should be shown directly in Telegram versus linked out?

## 15. Proposed MVP Decision Defaults

- Interface: Telegram bot.
- Language: English first, localization-ready architecture.
- Planning cadence: Saturday morning by default, user-configurable.
- First planning scope: dinners plus optional leftovers for lunches.
- Inventory: fridge photo plus quick confirmation, manual fallback.
- Photo recognition: optional local Ollama adapter.
- Nutrition: approximate, optional body metrics.
- Recipe source handling: metadata and links, with concise instructions generated from structured data.
- Hosting: low-cost single backend service.
- Database: PostgreSQL for deployed MVP, SQLite for local development.
