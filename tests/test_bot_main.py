import asyncio

from aiogram.types import MenuButtonCommands

from idlcooking.bot.main import configure_bot_commands


class _RecordingBot:
    def __init__(self) -> None:
        self.commands: list[object] | None = None
        self.menu_button: object | None = None

    async def set_my_commands(self, commands: list[object], **kwargs: object) -> None:
        self.commands = commands

    async def set_chat_menu_button(self, *, menu_button: object = None, **kwargs: object) -> None:
        self.menu_button = menu_button


def test_configure_bot_commands_pins_the_menu_button_to_the_command_list() -> None:
    # Issue #36: the chat "Menu" button must be set explicitly, not left to the client default.
    bot = _RecordingBot()

    asyncio.run(configure_bot_commands(bot))

    assert bot.commands  # a non-empty command list was registered
    assert isinstance(bot.menu_button, MenuButtonCommands)
