DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = frozenset({DEFAULT_LANGUAGE})


MESSAGES: dict[str, dict[str, str]] = {
    "en": {
        "start": (
            "Hi! I can help you build a simple weekly menu and shopping list.\n\n"
            "Start with /plan. If you want to account for food you already have, write:\n"
            "/plan rice, eggs, cucumber"
        ),
        "plan": "Draft menu #{planning_cycle_id}:\n\n{menu}\n\nShopping list:\n{shopping}",
        "schedule_current": (
            "Current schedule: {weekday_name}, {at_time} ({timezone}).\n\n"
            "To change it, send:\n/schedule <weekday> <HH:MM> [timezone]\n"
            "Example: /schedule saturday 09:00 Europe/Berlin"
        ),
        "schedule_usage": (
            "To change your schedule, send:\n/schedule <weekday> <HH:MM> [timezone]\n"
            "Example: /schedule saturday 09:00 Europe/Berlin"
        ),
        "schedule_invalid": (
            "I could not understand that schedule. Use a weekday name, 24-hour time, and an "
            "optional timezone, for example:\n/schedule saturday 09:00 Europe/Berlin"
        ),
        "schedule_updated": "Schedule updated: {weekday_name}, {at_time} ({timezone}).",
        "profile": (
            "Current profile:\n\n"
            "People: {household_size}\n"
            "Cooking: up to {cooking_effort_minutes} minutes\n"
            "Planning: weekday {planning_weekday}, {planning_time}, {timezone}"
        ),
        "fridge": (
            "For now, list food as text in /plan, for example:\n"
            "/plan rice, eggs, cucumber\n\n"
            "Fridge photos will be connected through the local Ollama adapter."
        ),
        "delete_my_data_confirm": (
            "This will permanently delete your profile, schedule, planning history, and shopping "
            "lists.\n\nAre you sure?"
        ),
        "delete_my_data_confirm_button": "Yes, delete everything",
        "delete_my_data_cancel_button": "Cancel",
        "delete_my_data_done": "Your data has been deleted. Send /start any time to begin again.",
        "delete_my_data_cancelled": "Cancelled. Your data was not deleted.",
        "consent_prompt": (
            "Before we start: I store your profile, schedule, and planning history so I can build "
            "weekly menus and shopping lists for you. You can delete this data any time with "
            "/delete_my_data.\n\nDo you agree to this?"
        ),
        "consent_agree_button": "I agree",
        "consent_decline_button": "Not now",
        "consent_declined": (
            "No problem. Nothing was stored. Send /start whenever you would like to begin."
        ),
        "consent_required": "Please send /start and agree to continue before using this command.",
        "onboarding_household_size_prompt": (
            "How many people are you usually cooking for? Reply with a number from 1 to 12."
        ),
        "onboarding_household_size_invalid": "Please reply with a whole number from 1 to 12.",
        "onboarding_cooking_effort_prompt": (
            "How much active cooking time do you want on a typical day?"
        ),
        "onboarding_effort_minimal": "Almost no cooking",
        "onboarding_effort_15": "15 minutes",
        "onboarding_effort_30": "30 minutes",
        "onboarding_effort_batch": "Batch cooking is okay",
        "onboarding_allergies_prompt": (
            "Any allergies I should avoid? List them separated by commas, or reply 'none'."
        ),
        "onboarding_hard_restrictions_prompt": (
            "Any hard dietary restrictions, such as vegetarian, halal, or kosher? List them "
            "separated by commas, or reply 'none'."
        ),
        "onboarding_disliked_ingredients_prompt": (
            "Any ingredients you dislike? List them separated by commas, or reply 'none'."
        ),
        "onboarding_favorite_tags_prompt": (
            "Any favorite cuisines or dishes you always enjoy? List them separated by commas, "
            "or reply 'skip'."
        ),
        "onboarding_budget_level_prompt": "How budget-sensitive should meal choices be?",
        "onboarding_budget_low": "Keep costs low",
        "onboarding_budget_moderate": "Moderate",
        "onboarding_budget_flexible": "Budget is flexible",
        "onboarding_activity_level_prompt": "What is your typical activity level?",
        "onboarding_activity_sedentary": "Sedentary",
        "onboarding_activity_light": "Light",
        "onboarding_activity_moderate": "Moderate",
        "onboarding_activity_active": "Active",
        "onboarding_nutrition_goal_prompt": "What is your main goal?",
        "onboarding_goal_maintain": "Maintain weight",
        "onboarding_goal_lose": "Lose weight",
        "onboarding_goal_gain": "Gain weight",
        "onboarding_goal_eat_regularly": "Eat more regularly",
        "onboarding_goal_reduce_waste": "Reduce food waste",
        "onboarding_body_metrics_choice_prompt": (
            "Want approximate calorie targets? I can estimate them from your height, weight, "
            "age, and sex. This is optional and only used for the estimate."
        ),
        "onboarding_body_metrics_yes": "Add body metrics",
        "onboarding_body_metrics_no": "Skip",
        "onboarding_body_metrics_height_prompt": "Height in centimeters?",
        "onboarding_body_metrics_weight_prompt": "Weight in kilograms?",
        "onboarding_body_metrics_age_prompt": "Age in years?",
        "onboarding_body_metrics_sex_prompt": (
            "Sex, used only for the calorie formula?"
        ),
        "onboarding_sex_male": "Male",
        "onboarding_sex_female": "Female",
        "onboarding_number_invalid": "Please reply with a valid positive number.",
        "onboarding_complete": (
            "Thanks! Your profile is saved.\n\n"
            "Start with /plan to get your first weekly menu and shopping list. If you want to "
            "account for food you already have, write:\n/plan rice, eggs, cucumber"
        ),
    }
}


def resolve_language(language_code: str | None) -> str:
    if not language_code:
        return DEFAULT_LANGUAGE
    normalized = language_code.lower().split("-", maxsplit=1)[0]
    return normalized if normalized in SUPPORTED_LANGUAGES else DEFAULT_LANGUAGE


def t(language: str, key: str, **kwargs: object) -> str:
    template = MESSAGES.get(language, MESSAGES[DEFAULT_LANGUAGE])[key]
    return template.format(**kwargs)
