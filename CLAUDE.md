# Project: Guardian Bot (demo)

An AI community guardian for crypto Telegram groups. It checks token contracts for risk, answers questions about one project from a knowledge file, and blocks scam messages. This is a portfolio demo, so it must be clean, reliable and easy to show on video.

## Stack
- Python 3.11+
- python-telegram-bot (v21+, async)
- httpx for API calls
- Free by default: risk summaries use transparent rules, no paid API needed
- Q&A uses keyword matching against knowledge/project.md (free, no LLM)
- SQLite for logs
- python-dotenv for config

## Rules
- Never hardcode secrets. Read everything from .env.
- Never ask for, store or handle private keys or seed phrases.
- The bot is read-only on-chain. It never sends transactions.
- Every external API call has a timeout (10s) and a friendly fallback message.
- Keep functions small and typed. Add docstrings.
- Write a test for each module in tests/.
- Risk summaries are informational. Always end with: "Not financial advice. DYOR."
- Verify API endpoints against their current docs before coding them.

## Commands
- Install: pip install -r requirements.txt
- Run: python -m app.main
- Test: pytest

## Workflow
- Build one milestone from SPEC.md at a time.
- After each milestone: run the tests, show me what changed, wait for my OK.
