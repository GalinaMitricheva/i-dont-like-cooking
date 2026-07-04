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
        "schedule": (
            "Default schedule: Saturday, 09:00. Schedule editing will be added next."
        ),
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
