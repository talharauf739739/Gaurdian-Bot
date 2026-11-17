"""Tests for app.main handlers (Telegram objects are mocked)."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from telegram import MessageEntity
from telegram.constants import ChatType

from app import main as bot
from app.config import load_config
from app.qa import KnowledgeBase
from app.storage import ActionLog

CONFIG = load_config({"TELEGRAM_BOT_TOKEN": "123:abc"})


def _user(uid: int, username: str | None, full_name: str) -> MagicMock:
    user = MagicMock()
    user.id, user.username, user.full_name, user.is_bot = uid, username, full_name, False
    user.mention_html.return_value = full_name
    return user


ADMIN = _user(1, "talha_rauf", "Talha Rauf")


def _context() -> MagicMock:
    context = MagicMock()
    context.bot.username = "GuardBot"
    context.bot.send_message = AsyncMock()
    context.bot.send_chat_action = AsyncMock()
    context.bot.get_chat_administrators = AsyncMock(return_value=[MagicMock(user=ADMIN)])
    context.bot_data = {"config": CONFIG, "log": ActionLog(":memory:"), "kb": KnowledgeBase.load()}
    context.args = []
    return context


def _update(text: str, user: MagicMock, urls: tuple[str, ...] = ()) -> MagicMock:
    update = MagicMock()
    update.effective_user = user
    update.effective_chat.id = -100
    update.effective_chat.type = ChatType.SUPERGROUP
    message = update.effective_message
    message.text, message.caption = text, None
    message.reply_text = AsyncMock()
    message.delete = AsyncMock()
    entities = {MagicMock(type=MessageEntity.URL): u for u in urls}
    message.parse_entities.return_value = entities
    message.parse_caption_entities.return_value = {}
    return update


@pytest.mark.asyncio
async def test_start_replies() -> None:
    update = _update("/start", ADMIN)
    await bot.start(update, MagicMock())
    update.effective_message.reply_text.assert_awaited_once_with(bot.START_TEXT)


@pytest.mark.asyncio
async def test_help_replies() -> None:
    update = _update("/help", ADMIN)
    await bot.help_command(update, MagicMock())
    update.effective_message.reply_text.assert_awaited_once_with(bot.HELP_TEXT)


def test_build_application_registers_commands() -> None:
    app = bot.build_application("123456:TEST-token")
    commands = {c for h in app.handlers[0] for c in getattr(h, "commands", ())}
    assert {"start", "help", "check", "stats"} <= commands


def test_build_application_with_proxy() -> None:
    app = bot.build_application("123456:TEST-token", "socks5://127.0.0.1:1080")
    assert app.bot is not None


@pytest.mark.asyncio
async def test_bad_link_from_member_is_deleted_and_logged() -> None:
    context = _context()
    update = _update("free sol here", _user(2, "member", "Member"), urls=("https://claim-sol.xyz",))
    await bot.on_message(update, context)
    update.effective_message.delete.assert_awaited_once()
    assert "claim-sol.xyz" in context.bot.send_message.await_args.args[1]
    assert context.bot_data["log"].counts() == {"link_deleted": 1}


@pytest.mark.asyncio
async def test_allowed_link_and_admin_links_are_kept() -> None:
    context = _context()
    member_update = _update("chart", _user(2, "member", "Member"), urls=("https://dexscreener.com/solana/x",))
    admin_update = _update("new site", ADMIN, urls=("https://anything.io",))
    await bot.on_message(member_update, context)
    await bot.on_message(admin_update, context)
    member_update.effective_message.delete.assert_not_awaited()
    admin_update.effective_message.delete.assert_not_awaited()


@pytest.mark.asyncio
async def test_impersonator_flagged_once() -> None:
    context = _context()
    fake = _user(3, "ta1ha_rauf", "Talha Rauf")
    await bot.on_message(_update("gm", fake), context)
    await bot.on_message(_update("gm again", fake), context)
    assert context.bot.send_message.await_count == 1
    assert "NOT" in context.bot.send_message.await_args.args[1]


@pytest.mark.asyncio
async def test_question_answered_from_knowledge() -> None:
    context = _context()
    update = _update("what is the total supply?", _user(2, "member", "Member"))
    await bot.on_message(update, context)
    assert "1,000,000,000" in update.effective_message.reply_text.await_args.args[0]


@pytest.mark.asyncio
async def test_unknown_question_with_mention_tags_admin() -> None:
    context = _context()
    update = _update("@GuardBot what is your favorite pizza?", _user(2, "member", "Member"))
    await bot.on_message(update, context)
    reply = update.effective_message.reply_text.await_args.args[0]
    assert "don't have that" in reply and "@talha_rauf" in reply


@pytest.mark.asyncio
async def test_unrelated_question_without_mention_is_ignored() -> None:
    context = _context()
    update = _update("anyone watching the match?", _user(2, "member", "Member"))
    await bot.on_message(update, context)
    update.effective_message.reply_text.assert_not_awaited()
