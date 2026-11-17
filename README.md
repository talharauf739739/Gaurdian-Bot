# 🛡 Guardian Bot

**A free AI-style community guardian for crypto Telegram groups.**
It checks Solana tokens for rug-pull risk, answers questions about your project, and removes scams before your members fall for them.

> Built with Python and python-telegram-bot. No paid APIs: runs entirely on free data sources.

---

## ✨ Features

| | Feature | What it does |
|---|---|---|
| 🔍 | **Token risk check** | Paste any Solana token address (or `/check <address>`). The bot pulls live data from DexScreener and RugCheck and replies in about 2 seconds with a 🟢 Low / 🟡 Medium / 🔴 High risk rating and the top 3 reasons. |
| 💡 | **Project Q&A** | Members ask questions ending in `?` (or mention the bot). It answers only from your project's knowledge file, so it never invents facts. If it doesn't know, it tags an admin. |
| 🚫 | **Link filter** | Deletes links to any site not on your allow-list and warns the sender. Catches hidden links behind text too. |
| 🎣 | **Scam phrase filter** | Removes "DM me for support", "verify your wallet", "seed phrase", "claim your airdrop" and similar. Ignores safety advice like "never share your seed phrase". |
| 🎭 | **Fake admin detection** | Flags members whose name imitates an admin: `ta1ha_rauf`, `talha_rauf_`, `TalhaRauf_support`, Cyrillic look-alike letters, one-letter typos. |
| 👋 | **Safety welcome** | Greets new members with "Admins never DM first." |
| 📊 | **Moderation log** | Every action is saved to SQLite. Admins can run `/stats`. |

### Example risk check

```
🛡 Bonk ($Bonk): 🟢 Low risk
💲 $0.000002327 · MC $204.78M · Liq $229.72K · Vol 24h $156.98K · Age 3y 10mo
1. Mint authority revoked
2. Freeze authority revoked
3. Trading for 3y 10mo

Not financial advice. DYOR.
```

<!-- Add screenshots to docs/screenshots/ and link them here, e.g.:
![Risk check](docs/screenshots/risk-check.png)
![Scam link removed](docs/screenshots/scam-link.png)
![Fake admin flagged](docs/screenshots/fake-admin.png)
-->

---

## 🚀 Setup (about 10 minutes)

### 1. Create your bot
1. In Telegram, open **@BotFather** and send `/newbot`. Pick a name and a username ending in `bot`.
2. Copy the **token** BotFather gives you.
3. Send `/setprivacy` to BotFather, choose your bot, then **Disable** (so it can read group messages).

### 2. Run it

**Option A: GitHub Codespaces (no install, works on any network)**
1. Fork this repo, then go to **Settings → Secrets and variables → Codespaces** and add a secret named `TELEGRAM_BOT_TOKEN` with your token.
2. Click **Code → Codespaces → Create codespace on main** and wait for it to build.
3. In the terminal run:
   ```bash
   python -m app.main
   ```

**Option B: Your own computer (Python 3.11+)**
```bash
git clone https://github.com/<you>/Gaurdian-Bot.git
cd Gaurdian-Bot
python -m venv .venv
# Windows: .venv\Scripts\activate    macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env        # then paste your token into .env
python -m app.main
```

You should see: `Guardian Bot is running as @YourBot`.

### 3. Add it to your group
1. Add the bot to your group.
2. Make it an **admin** with the **Delete messages** permission (needed to remove scams).
3. Send `/help` to check it's alive.

---

## ⚙️ Configuration

All settings live in `.env` (see `.env.example`). Only the token is required.

| Variable | Default | Purpose |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | (required) | Token from @BotFather |
| `ALLOWED_DOMAINS` | `dexscreener.com,solscan.io,x.com,twitter.com,rugcheck.xyz` | Links to these sites (and their subdomains) are allowed |
| `ADMIN_USERNAMES` | (empty) | Extra admin usernames, without @. Group admins are detected automatically. |
| `TELEGRAM_PROXY_URL` | (empty) | `socks5://host:port` or `http://host:port` if your network blocks Telegram |
| `DB_PATH` | `guardian.db` | Where the moderation log is stored |

### Teach it about your project
Edit [`knowledge/project.md`](knowledge/project.md). Each `## Question` heading is one answer. Add a `Keywords:` line to help it match differently worded questions:

```markdown
## When is the launch?
Keywords: launch, date, release, live, start
We launch on Raydium on March 1st at 18:00 UTC.
```

Restart the bot after editing.

---

## 🧠 How the risk rating works

The rating uses transparent rules, not a black box. Each concern adds points:

| Signal | Points |
|---|---|
| Marked as rugged by RugCheck | +10 |
| Mint authority still active (more tokens can be created) | +3 |
| Freeze authority still active (wallets can be frozen) | +3 |
| Top holder owns over 30% (over 15%: +1) | +3 |
| Pair younger than 1 hour (under 24h: +2, under 7 days: +1) | +3 |
| Top 10 holders own over 60% | +2 |
| RugCheck "danger" flags (up to 2) | +2 each |
| Liquidity under $10K (under $50K: +1), or no DEX liquidity yet | +2 |
| Under 50% of liquidity locked on a pool under $100K | +2 |
| Market cap under $100K | +1 |

**0-2 = 🟢 Low · 3-5 = 🟡 Medium · 6+ = 🔴 High**

Data sources: [DexScreener API](https://docs.dexscreener.com/api/reference) and [RugCheck API](https://api.rugcheck.xyz/swagger/index.html). Both are free and need no key.

---

## 🗂 Project structure

```
app/
  main.py            # Telegram handlers and message routing
  config.py          # Settings from .env
  contract_check.py  # DexScreener + RugCheck + risk rules
  qa.py              # Answers from knowledge/project.md
  scam_filter.py     # Link, phrase and fake-admin detection
  storage.py         # SQLite moderation log
knowledge/project.md # Your project's FAQ
tests/               # 75 offline tests (pytest)
```

Run the tests with `pytest`.

---

## 🔒 Safety

- The bot is **read-only on-chain**. It never sends transactions and never asks for keys or seed phrases.
- Risk ratings are informational. **Not financial advice. DYOR.**
- Keep your bot token secret. If it leaks, send `/revoke` to @BotFather.

---

## 📬 Want this for your community?

Guardian Bot can be customized for your project: your FAQ, your rules, other chains (Base, BNB, Ethereum), and 24/7 hosting.
Get in touch via the contact links on my GitHub profile.
