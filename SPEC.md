# Guardian Bot: Spec

## Folder structure
```
app/
  main.py          # bot startup, handler registration
  config.py        # loads .env
  contract_check.py  # DexScreener + RugCheck + LLM summary
  qa.py            # answers from knowledge/project.md
  scam_filter.py   # link and impersonation checks
  llm.py           # one wrapper for the LLM provider
  storage.py       # SQLite logging
knowledge/
  project.md       # FAQ for the demo token
tests/
.env.example
requirements.txt
README.md
```

## .env.example
```
TELEGRAM_BOT_TOKEN=
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=
OPENAI_API_KEY=
ADMIN_USERNAMES=admin1,admin2
ALLOWED_DOMAINS=dexscreener.com,solscan.io,x.com
```

## Milestone 1: bot skeleton
- /start and /help commands.
- Bot replies in a test group.
- Done when: the bot responds in the group.

## Milestone 2: contract check
- Detect a Solana address (base58, 32 to 44 chars) in any message, or /check <address>.
- Fetch DexScreener: price, liquidity, 24h volume, market cap, pair age.
- Fetch RugCheck report: mint authority, freeze authority, top holder share, LP lock, risk flags.
- Send both to the LLM to write a short summary: 5 lines max, a risk level (Low, Medium, High), and the top 3 reasons.
- Done when: posting a real contract returns a clean summary in under 10 seconds.

## Milestone 3: Q&A from a knowledge file
- Load knowledge/project.md (token name, supply, roadmap, links, team, FAQs).
- When the bot is mentioned or a message ends with "?", answer only from that file.
- If the answer is not in the file, say so and tag an admin.
- Done when: it answers 5 test questions correctly and refuses one it cannot answer.

## Milestone 4: scam filter
- Delete messages with links outside ALLOWED_DOMAINS and warn the sender.
- Flag users whose name looks like an admin's (similar spelling, l vs 1, extra underscore).
- Detect phrases like "DM me for support", "verify your wallet", "seed phrase".
- Post a pinned-style warning: "Admins never DM first."
- Log every action to SQLite.
- Done when: a fake link and a fake admin name are both caught in the demo.

## Milestone 5: demo polish
- Clean message formatting with emojis for risk level.
- README with setup steps, screenshots and a short feature list.
- Done when: a stranger can run it from the README in 10 minutes.

## Demo video script (1 minute)
1. Paste a contract address. Show the risk summary.
2. Ask two questions about the project. Show the answers.
3. Post a scam link. Show it deleted with a warning.
4. Change a display name to look like an admin. Show the flag.
5. End on the GitHub link and your X handle.
