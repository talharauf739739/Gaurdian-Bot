"""Guardian Bot entry point: builds the Telegram application and registers handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.config import load_config

logging.basicConfig(format="%(asctime)s %(levelname)s %(name)s: %(message)s", level=logging.INFO)
logger = logging.getLogger("guardian_bot")

START_TEXT = (
    "Hi, I'm Guardian Bot. I keep this group safe.\n"
    "Send /help to see what I can do."
)

HELP_TEXT = (
    "Guardian Bot commands:\n"
    "/start - say hello\n"
    "/help - show this message\n\n"
    "Coming soon: contract risk checks, project Q&A and scam filtering.\n"
    "Admins never DM first."
)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to /start with a short greeting."""
    if update.effective_message:
        await update.effective_message.reply_text(START_TEXT)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply to /help with the command list."""
    if update.effective_message:
        await update.effective_message.reply_text(HELP_TEXT)


def build_application(token: str) -> Application:
    """Create the Telegram application with all handlers registered."""
    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    return application


def main() -> None:
    """Load config and start long polling."""
    config = load_config()
    application = build_application(config.telegram_bot_token)
    logger.info("Guardian Bot is running. Press Ctrl+C to stop.")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
