"""Tests for app.main command handlers."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.main import HELP_TEXT, START_TEXT, build_application, help_command, start


def _fake_update() -> MagicMock:
    update = MagicMock()
    update.effective_message.reply_text = AsyncMock()
    return update


@pytest.mark.asyncio
async def test_start_replies() -> None:
    update = _fake_update()
    await start(update, MagicMock())
    update.effective_message.reply_text.assert_awaited_once_with(START_TEXT)


@pytest.mark.asyncio
async def test_help_replies() -> None:
    update = _fake_update()
    await help_command(update, MagicMock())
    update.effective_message.reply_text.assert_awaited_once_with(HELP_TEXT)


def test_build_application_registers_commands() -> None:
    app = build_application("123456:TEST-token")
    commands = {c for h in app.handlers[0] for c in getattr(h, "commands", ())}
    assert {"start", "help"} <= commands


def test_build_application_with_proxy() -> None:
    app = build_application("123456:TEST-token", "socks5://127.0.0.1:1080")
    assert app.bot is not None
