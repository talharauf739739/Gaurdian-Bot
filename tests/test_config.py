"""Tests for app.config."""

import pytest

from app.config import load_config


def test_load_config_parses_values() -> None:
    config = load_config(
        {
            "TELEGRAM_BOT_TOKEN": "123:abc",
            "LLM_PROVIDER": "OpenAI",
            "ADMIN_USERNAMES": "@Admin1, admin2 ,",
            "ALLOWED_DOMAINS": "DexScreener.com,x.com",
        }
    )
    assert config.telegram_bot_token == "123:abc"
    assert config.llm_provider == "openai"
    assert config.admin_usernames == ("admin1", "admin2")
    assert config.allowed_domains == ("dexscreener.com", "x.com")


def test_load_config_requires_token() -> None:
    with pytest.raises(ValueError):
        load_config({"TELEGRAM_BOT_TOKEN": "  "})
