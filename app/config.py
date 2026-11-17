"""Load bot configuration from environment variables (.env)."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


def _split_csv(value: str | None) -> tuple[str, ...]:
    """Split a comma-separated string into a tuple of trimmed, non-empty items."""
    if not value:
        return ()
    return tuple(item.strip() for item in value.split(",") if item.strip())


@dataclass(frozen=True)
class Config:
    """Runtime settings for the bot."""

    telegram_bot_token: str
    llm_provider: str
    anthropic_api_key: str
    openai_api_key: str
    admin_usernames: tuple[str, ...]
    allowed_domains: tuple[str, ...]


def load_config(env: dict[str, str] | None = None) -> Config:
    """Build a Config from `env` (defaults to os.environ after loading .env).

    Raises:
        ValueError: if TELEGRAM_BOT_TOKEN is missing.
    """
    if env is None:
        load_dotenv()
        env = dict(os.environ)

    token = env.get("TELEGRAM_BOT_TOKEN", "").strip()
    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and fill it in.")

    return Config(
        telegram_bot_token=token,
        llm_provider=env.get("LLM_PROVIDER", "anthropic").strip().lower(),
        anthropic_api_key=env.get("ANTHROPIC_API_KEY", "").strip(),
        openai_api_key=env.get("OPENAI_API_KEY", "").strip(),
        admin_usernames=tuple(u.lstrip("@").lower() for u in _split_csv(env.get("ADMIN_USERNAMES"))),
        allowed_domains=tuple(d.lower() for d in _split_csv(env.get("ALLOWED_DOMAINS"))),
    )
