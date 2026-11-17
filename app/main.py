"""Guardian Bot entry point: builds the Telegram application and registers handlers."""

from __future__ import annotations

import html
import logging
import time

from telegram import Message, MessageEntity, Update, User
from telegram.constants import ChatAction, ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app import qa, scam_filter
from app.config import Config, load_config
from app.contract_check import check_contract, find_solana_address
from app.storage import ActionLog

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("guardian_bot")
# httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)

ADMIN_CACHE_SECONDS = 600
SAFETY_LINE = "🛡 Admins never DM first."

START_TEXT = (
    "Hi, I'm Guardian Bot. I keep this group safe.\n"
    "Send /help to see what I can do."
)

HELP_TEXT = (
    "🛡 Guardian Bot\n\n"
    "🔍 /check <address> - risk check for a Solana token\n"
    "   (or just paste a token address)\n"
    "💡 Ask about the project: end your message with ? or mention me\n"
    "🚫 I remove unapproved links and scam messages, and flag fake admins\n"
    "📊 /stats - moderation stats (admins only)\n\n"
    f"{SAFETY_LINE}"
)

CHECK_USAGE = "Usage: /check <Solana token address>"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    return context.bot_data["config"]


def _log(context: ContextTypes.DEFAULT_TYPE) -> ActionLog:
    return context.bot_data["log"]


def _is_group(update: Update) -> bool:
    chat = update.effective_chat
    return bool(chat) and chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)


async def get_chat_admins(context: ContextTypes.DEFAULT_TYPE, chat_id: int) -> list[User]:
    """Human admins of a chat, cached for 10 minutes."""
    cache: dict[int, tuple[float, list[User]]] = context.bot_data.setdefault("admin_cache", {})
    cached = cache.get(chat_id)
    if cached and time.time() - cached[0] < ADMIN_CACHE_SECONDS:
        return cached[1]
    try:
        members = await context.bot.get_chat_administrators(chat_id)
        admins = [m.user for m in members if not m.user.is_bot]
    except TelegramError as exc:
        logger.warning("Could not load admins for chat %s: %s", chat_id, exc)
        admins = cached[1] if cached else []
    cache[chat_id] = (time.time(), admins)
    return admins


def is_admin(user: User, admins: list[User], config: Config) -> bool:
    """True if the user is a chat admin or listed in ADMIN_USERNAMES."""
    return user.id in {a.id for a in admins} or (user.username or "").lower() in config.admin_usernames


def _admin_names(admins: list[User], config: Config) -> list[str]:
    names: list[str] = list(config.admin_usernames)
    for admin in admins:
        names += [n for n in (admin.username, admin.full_name) if n]
    return names


def _admin_tags(admins: list[User], config: Config) -> str:
    usernames = list(config.admin_usernames) or [a.username for a in admins if a.username]
    return " ".join(f"@{u}" for u in usernames[:2])


def extract_urls(message: Message) -> list[str]:
    """All links in a message, including hidden links behind text."""
    kinds = [MessageEntity.URL, MessageEntity.TEXT_LINK]
    found = {**message.parse_entities(kinds), **message.parse_caption_entities(kinds)}
    return [entity.url if entity.type == MessageEntity.TEXT_LINK else text for entity, text in found.items()]


async def _send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    await context.bot.send_message(chat_id, text, parse_mode=ParseMode.HTML, disable_web_page_preview=True)


# ---------------------------------------------------------------------------
# Commands
# ---------------------------------------------------------------------------

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to /start with a short greeting."""
    if update.effective_message:
        await update.effective_message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to /help with the command list."""
    if update.effective_message:
        await update.effective_message.reply_text(HELP_TEXT)


async def _reply_with_check(update: Update, context: ContextTypes.DEFAULT_TYPE, address: str) -> None:
    """Show 'typing…', run the contract check and reply with the summary."""
    message = update.effective_message
    if not message:
        return
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.TYPING)
    summary = await check_contract(address)
    await message.reply_text(summary, disable_web_page_preview=True)


async def check_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /check <address>."""
    address = find_solana_address(" ".join(context.args or []))
    if not address:
        if update.effective_message:
            await update.effective_message.reply_text(CHECK_USAGE)
        return
    await _reply_with_check(update, context, address)


async def stats_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Admins only: show how many actions the bot has taken in this chat."""
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat or not _is_group(update):
        return
    if not is_admin(user, await get_chat_admins(context, chat.id), _config(context)):
        await message.reply_text("Only admins can use /stats.")
        return
    counts = _log(context).counts(chat.id)
    labels = {
        "link_deleted": "🔗 Links removed",
        "scam_phrase": "🎣 Scam messages removed",
        "impersonator_flagged": "🎭 Fake admins flagged",
        "question_answered": "💡 Questions answered",
        "question_unanswered": "🤔 Questions passed to admins",
    }
    lines = [f"{label}: {counts.get(key, 0)}" for key, label in labels.items()]
    await message.reply_text("📊 Guardian stats\n\n" + "\n".join(lines))


# ---------------------------------------------------------------------------
# Moderation
# ---------------------------------------------------------------------------

async def enforce_scam_rules(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str) -> bool:
    """Delete messages with unapproved links or scam phrases. Returns True if one was removed."""
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    config = _config(context)
    bad_links = scam_filter.find_disallowed_links(extract_urls(message), config.allowed_domains)
    phrases = [] if bad_links else scam_filter.find_scam_phrases(text)
    if not bad_links and not phrases:
        return False

    if bad_links:
        action, reason = "link_deleted", f"link to {scam_filter.domain_of(bad_links[0])}"
        rule = "Only links to " + ", ".join(config.allowed_domains) + " are allowed."
    else:
        action, reason = "scam_phrase", f'scam phrase "{phrases[0]}"'
        rule = "Never share your seed phrase or connect your wallet to unknown sites."

    try:
        await message.delete()
        removed = "🚨 Removed a message"
    except TelegramError:
        removed = "🚨 Suspicious message (make me an admin with 'Delete messages' so I can remove it)"

    await _send(
        context,
        chat.id,
        f"{removed} from {user.mention_html()}: {html.escape(reason)}.\n{html.escape(rule)}\n{SAFETY_LINE}",
    )
    _log(context).log(action, chat.id, user.id, user.username, detail=f"{reason} | {text[:200]}")
    return True


async def flag_impersonator(context: ContextTypes.DEFAULT_TYPE, chat_id: int, user: User, admins: list[User]) -> bool:
    """Warn the group if `user` looks like an admin. Each name is flagged once."""
    config = _config(context)
    if is_admin(user, admins, config):
        return False
    match = scam_filter.find_impersonation([user.username, user.full_name], _admin_names(admins, config))
    if not match:
        return False
    flagged: set = context.bot_data.setdefault("flagged", set())
    key = (chat_id, user.id, user.username, user.full_name)
    if key in flagged:
        return False
    flagged.add(key)
    await _send(
        context,
        chat_id,
        f"⚠️ Heads up: {user.mention_html()} looks like admin <b>{html.escape(match)}</b> "
        f"but is <b>NOT</b> an admin.\n{SAFETY_LINE} Never send funds or seed phrases to anyone.",
    )
    _log(context).log("impersonator_flagged", chat_id, user.id, user.username, detail=f"imitates {match}")
    return True


# ---------------------------------------------------------------------------
# Q&A
# ---------------------------------------------------------------------------

async def answer_question(update: Update, context: ContextTypes.DEFAULT_TYPE, text: str, admins: list[User]) -> None:
    """Answer from the knowledge file, or hand over to an admin."""
    message, chat, user = update.effective_message, update.effective_chat, update.effective_user
    kb: qa.KnowledgeBase = context.bot_data["kb"]
    bot_username = context.bot.username
    question = qa.strip_mention(text, bot_username)
    answer = kb.answer(question)
    if answer:
        await message.reply_text(f"💡 {answer}", disable_web_page_preview=True)
        _log(context).log("question_answered", chat.id, user.id, user.username, detail=question[:200])
        return

    # Plain "?" messages that have nothing to do with the project are ignored to keep the chat quiet.
    _, best_score = kb.best_match(question)
    if not qa.is_mentioned(text, bot_username) and best_score == 0:
        return
    tags = _admin_tags(admins, _config(context))
    handover = f"{html.escape(tags)} can you help?" if tags else "An admin will help soon."
    await message.reply_text(
        f"🤔 I don't have that in my project notes. {handover}", parse_mode=ParseMode.HTML
    )
    _log(context).log("question_unanswered", chat.id, user.id, user.username, detail=question[:200])


# ---------------------------------------------------------------------------
# Message router
# ---------------------------------------------------------------------------

async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Every non-command message: moderation first, then contract checks, then Q&A."""
    message, user, chat = update.effective_message, update.effective_user, update.effective_chat
    if not message or not user or not chat or user.is_bot:
        return
    text = message.text or message.caption or ""
    config = _config(context)

    admins: list[User] = []
    if _is_group(update):
        admins = await get_chat_admins(context, chat.id)
        if not is_admin(user, admins, config):
            if await enforce_scam_rules(update, context, text):
                return
            await flag_impersonator(context, chat.id, user, admins)

    address = find_solana_address(text)
    if address:
        await _reply_with_check(update, context, address)
        return
    if text and qa.is_question(text, context.bot.username):
        await answer_question(update, context, text, admins)


async def on_new_members(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Welcome new members with the safety reminder and check them for admin look-alikes."""
    message, chat = update.effective_message, update.effective_chat
    if not message or not chat:
        return
    members = [m for m in message.new_chat_members if not m.is_bot]
    if not members:
        return
    admins = await get_chat_admins(context, chat.id)
    names = ", ".join(m.mention_html() for m in members)
    await _send(
        context,
        chat.id,
        f"👋 Welcome {names}!\n{SAFETY_LINE} Anyone who DMs you offering support or airdrops is a scammer.",
    )
    for member in members:
        await flag_impersonator(context, chat.id, member, admins)


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

def build_application(
    token: str,
    proxy_url: str = "",
    config: Config | None = None,
    action_log: ActionLog | None = None,
    knowledge: qa.KnowledgeBase | None = None,
) -> Application:
    """Create the Telegram application with all handlers registered.

    `proxy_url` (e.g. socks5://127.0.0.1:1080 or http://host:port) routes Telegram
    traffic through a proxy for networks that block api.telegram.org.
    """
    builder = (
        Application.builder()
        .token(token)
        # Generous timeouts: some networks reach api.telegram.org slowly.
        .connect_timeout(30)
        .read_timeout(30)
        .write_timeout(30)
        .get_updates_connect_timeout(30)
        .get_updates_read_timeout(40)
    )
    if proxy_url:
        builder = builder.proxy(proxy_url).get_updates_proxy(proxy_url)
    application = builder.build()

    if config is not None:
        application.bot_data["config"] = config
    application.bot_data["log"] = action_log or ActionLog(":memory:")
    application.bot_data["kb"] = knowledge or qa.KnowledgeBase.load()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(CommandHandler("stats", stats_command))
    application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, on_new_members))
    application.add_handler(MessageHandler((filters.TEXT | filters.CAPTION) & ~filters.COMMAND, on_message))
    return application


async def _announce_ready(application: Application) -> None:
    """Log once the bot has actually connected to Telegram."""
    logger.info("Guardian Bot is running as @%s. Press Ctrl+C to stop.", application.bot.username)


def main() -> None:
    """Load config and start long polling."""
    config = load_config()
    knowledge = qa.KnowledgeBase.load()
    application = build_application(
        config.telegram_bot_token,
        config.telegram_proxy_url,
        config=config,
        action_log=ActionLog(config.db_path),
        knowledge=knowledge,
    )
    application.post_init = _announce_ready
    via = f" via proxy {config.telegram_proxy_url.split('@')[-1]}" if config.telegram_proxy_url else ""
    logger.info("Loaded %d knowledge entries. Connecting to Telegram%s...", len(knowledge.entries), via)
    # bootstrap_retries=-1: keep retrying the first connection instead of crashing.
    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


if __name__ == "__main__":
    main()
