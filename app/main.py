"""Guardian Bot entry point: builds the Telegram application and registers handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

from app.config import load_config
from app.contract_check import check_contract, find_solana_address

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("guardian_bot")
# httpx logs every request URL at INFO, and Telegram URLs contain the bot token.
logging.getLogger("httpx").setLevel(logging.WARNING)

START_TEXT = (
    "Hi, I'm Guardian Bot. I keep this group safe.\n"
    "Send /help to see what I can do."
)

HELP_TEXT = (
    "Guardian Bot commands:\n"
    "/start - say hello\n"
    "/help - show this message\n"
    "/check <address> - risk check for a Solana token\n\n"
    "Tip: just paste a Solana token address and I'll check it.\n"
    "Admins never DM first."
)

CHECK_USAGE = "Usage: /check <Solana token address>"


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


async def address_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Auto-check any plain message that contains a Solana address."""
    message = update.effective_message
    address = find_solana_address(message.text if message else "")
    if address:
        await _reply_with_check(update, context, address)


def build_application(token: str, proxy_url: str = "") -> Application:
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
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("check", check_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, address_message))
    return application


def main() -> None:
    """Load config and start long polling."""
    config = load_config()
    application = build_application(config.telegram_bot_token, config.telegram_proxy_url)
    via = f" via proxy {config.telegram_proxy_url.split('@')[-1]}" if config.telegram_proxy_url else ""
    logger.info("Connecting to Telegram%s... (retries automatically if the network is slow)", via)
    application.post_init = _announce_ready
    # bootstrap_retries=-1: keep retrying the first connection instead of crashing.
    application.run_polling(allowed_updates=Update.ALL_TYPES, bootstrap_retries=-1)


async def _announce_ready(application: Application) -> None:
    """Log once the bot has actually connected to Telegram."""
    logger.info("Guardian Bot is running as @%s. Press Ctrl+C to stop.", application.bot.username)


if __name__ == "__main__":
    main()
