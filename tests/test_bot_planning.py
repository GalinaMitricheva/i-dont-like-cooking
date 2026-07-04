from idlcooking.bot.planning import TelegramPlanningFacade


def test_telegram_planning_facade_generates_and_persists_plan() -> None:
    facade = TelegramPlanningFacade("sqlite:///:memory:")

    summary = facade.generate_plan_from_text_inventory(telegram_user_id=12345, inventory_text="rice")

    assert summary.planning_cycle_id == 1
    assert len(summary.menu_lines) == 7
    assert any("already have" in line for line in summary.shopping_lines)
