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
