"""Solana token risk check: DexScreener market data + RugCheck security data + rule-based scoring.

The summary is produced by fixed, transparent rules (no LLM needed), so it is free,
fast and gives the same answer for the same data.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

logger = logging.getLogger(__name__)

DEXSCREENER_URL = "https://api.dexscreener.com/tokens/v1/solana/{address}"
RUGCHECK_URL = "https://api.rugcheck.xyz/v1/tokens/{address}/report"
REQUEST_TIMEOUT_SECONDS = 10.0
DISCLAIMER = "Not financial advice. DYOR."

_BASE58_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_ADDRESS_PATTERN = re.compile(r"(?<![1-9A-HJ-NP-Za-km-z])[1-9A-HJ-NP-Za-km-z]{32,44}(?![1-9A-HJ-NP-Za-km-z])")


# ---------------------------------------------------------------------------
# Address detection
# ---------------------------------------------------------------------------

def _base58_decoded_length(value: str) -> int:
    """Return the number of bytes `value` decodes to as base58."""
    number = 0
    for char in value:
        number = number * 58 + _BASE58_ALPHABET.index(char)
    leading_zeros = len(value) - len(value.lstrip("1"))
    return leading_zeros + (number.bit_length() + 7) // 8


def is_solana_address(value: str) -> bool:
    """True if `value` is base58 text that decodes to a 32-byte Solana public key."""
    if not 32 <= len(value) <= 44 or any(c not in _BASE58_ALPHABET for c in value):
        return False
    return _base58_decoded_length(value) == 32


def find_solana_address(text: str) -> str | None:
    """Return the first valid Solana address found in `text`, or None."""
    for match in _ADDRESS_PATTERN.finditer(text or ""):
        if is_solana_address(match.group()):
            return match.group()
    return None


# ---------------------------------------------------------------------------
# Data models
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MarketData:
    """Market facts from DexScreener (most liquid pair)."""

    name: str
    symbol: str
    price_usd: float | None
    liquidity_usd: float | None
    volume_24h_usd: float | None
    market_cap_usd: float | None
    pair_created_at_ms: int | None
    url: str | None


@dataclass(frozen=True)
class SecurityData:
    """Security facts from RugCheck."""

    mint_authority: str | None
    freeze_authority: str | None
    top_holder_pct: float | None
    top10_holders_pct: float | None
    lp_locked_pct: float | None
    rugged: bool
    danger_flags: tuple[str, ...] = ()
    warning_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class RiskAssessment:
    """Result of the rule-based scoring."""

    level: str  # "Low" | "Medium" | "High"
    score: int
    reasons: tuple[str, ...]


@dataclass
class _Findings:
    """Collects weighted concerns and positives while scoring."""

    concerns: list[tuple[int, str]] = field(default_factory=list)
    positives: list[str] = field(default_factory=list)

    def concern(self, weight: int, text: str) -> None:
        self.concerns.append((weight, text))


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _to_float(value: Any) -> float | None:
    """Convert API numbers/strings to float, returning None when missing or invalid."""
    try:
        return float(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def parse_dexscreener(payload: Any) -> MarketData | None:
    """Pick the most liquid pair from a DexScreener /tokens/v1 response."""
    pairs = payload if isinstance(payload, list) else (payload or {}).get("pairs") or []
    pairs = [p for p in pairs if isinstance(p, dict)]
    if not pairs:
        return None
    best = max(pairs, key=lambda p: _to_float((p.get("liquidity") or {}).get("usd")) or 0.0)
    base = best.get("baseToken") or {}
    return MarketData(
        name=str(base.get("name") or "Unknown"),
        symbol=str(base.get("symbol") or "?"),
        price_usd=_to_float(best.get("priceUsd")),
        liquidity_usd=_to_float((best.get("liquidity") or {}).get("usd")),
        volume_24h_usd=_to_float((best.get("volume") or {}).get("h24")),
        market_cap_usd=_to_float(best.get("marketCap") or best.get("fdv")),
        pair_created_at_ms=best.get("pairCreatedAt"),
        url=best.get("url"),
    )


def _weighted_lp_locked_pct(markets: list[dict[str, Any]]) -> float | None:
    """Liquidity-weighted LP locked percentage across all markets."""
    total = locked = 0.0
    for market in markets:
        lp = market.get("lp") or {}
        size = (_to_float(lp.get("baseUSD")) or 0.0) + (_to_float(lp.get("quoteUSD")) or 0.0)
        pct = _to_float(lp.get("lpLockedPct"))
        if size > 0 and pct is not None:
            total += size
            locked += size * pct
    return locked / total if total else None


def parse_rugcheck(payload: Any) -> SecurityData | None:
    """Extract the security facts we score from a RugCheck /report response."""
    if not isinstance(payload, dict) or not payload:
        return None
    token = payload.get("token") or {}
    holders = [h for h in payload.get("topHolders") or [] if isinstance(h, dict)]
    pcts = sorted((_to_float(h.get("pct")) or 0.0 for h in holders), reverse=True)
    risks = [r for r in payload.get("risks") or [] if isinstance(r, dict)]
    return SecurityData(
        mint_authority=token.get("mintAuthority", payload.get("mintAuthority")),
        freeze_authority=token.get("freezeAuthority", payload.get("freezeAuthority")),
        top_holder_pct=pcts[0] if pcts else None,
        top10_holders_pct=sum(pcts[:10]) if pcts else None,
        lp_locked_pct=_weighted_lp_locked_pct(payload.get("markets") or []),
        rugged=bool(payload.get("rugged")),
        danger_flags=tuple(str(r.get("name")) for r in risks if r.get("level") == "danger"),
        warning_flags=tuple(str(r.get("name")) for r in risks if r.get("level") == "warn"),
    )


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------

def _pair_age_hours(created_at_ms: int | None, now: float | None = None) -> float | None:
    """Hours since the pair was created."""
    if not created_at_ms:
        return None
    return max(0.0, ((now or time.time()) * 1000 - created_at_ms) / 3_600_000)


def _score_security(sec: SecurityData, f: _Findings) -> None:
    """Add concerns/positives from RugCheck data."""
    if sec.rugged:
        f.concern(10, "RugCheck marks this token as rugged")
    if sec.mint_authority:
        f.concern(3, "Mint authority is active: more tokens can be created")
    else:
        f.positives.append("Mint authority revoked")
    if sec.freeze_authority:
        f.concern(3, "Freeze authority is active: wallets can be frozen")
    else:
        f.positives.append("Freeze authority revoked")
    if sec.top_holder_pct is not None:
        if sec.top_holder_pct > 30:
            f.concern(3, f"Top holder owns {sec.top_holder_pct:.0f}% of supply")
        elif sec.top_holder_pct > 15:
            f.concern(1, f"Top holder owns {sec.top_holder_pct:.0f}% of supply")
    if sec.top10_holders_pct is not None and sec.top10_holders_pct > 60:
        f.concern(2, f"Top 10 holders own {sec.top10_holders_pct:.0f}% of supply")
    for name in sec.danger_flags[:2]:
        f.concern(2, f"RugCheck danger: {name}")


def _score_market(market: MarketData, sec: SecurityData | None, f: _Findings, now: float | None) -> None:
    """Add concerns/positives from DexScreener data."""
    liq = market.liquidity_usd
    if liq is None:
        f.concern(2, "No DEX liquidity yet (likely still on a launchpad curve)")
    if market.market_cap_usd is not None and market.market_cap_usd < 100_000:
        f.concern(1, f"Tiny market cap ({format_usd(market.market_cap_usd)})")
    if liq is not None:
        if liq < 10_000:
            f.concern(2, f"Very low liquidity ({format_usd(liq)})")
        elif liq < 50_000:
            f.concern(1, f"Low liquidity ({format_usd(liq)})")
        elif liq >= 250_000:
            f.positives.append(f"Deep liquidity ({format_usd(liq)})")
        if sec and sec.lp_locked_pct is not None and sec.lp_locked_pct < 50 and liq < 100_000:
            f.concern(2, f"Only {sec.lp_locked_pct:.0f}% of liquidity is locked")
    age = _pair_age_hours(market.pair_created_at_ms, now)
    if age is not None:
        if age < 1:
            f.concern(3, f"Brand-new pair ({format_age(age)} old)")
        elif age < 24:
            f.concern(2, f"New pair ({format_age(age)} old)")
        elif age < 24 * 7:
            f.concern(1, f"Young pair ({format_age(age)} old)")
        elif age > 24 * 90:
            f.positives.append(f"Trading for {format_age(age)}")


def assess_risk(market: MarketData | None, sec: SecurityData | None, now: float | None = None) -> RiskAssessment:
    """Score the token and return a Low/Medium/High level with its top 3 reasons."""
    f = _Findings()
    if sec:
        _score_security(sec, f)
    else:
        f.concern(2, "Security report unavailable: authorities and holders not checked")
    if market:
        _score_market(market, sec, f, now)
    else:
        f.concern(3, "No trading pairs found on DexScreener")

    score = sum(weight for weight, _ in f.concerns)
    level = "High" if score >= 6 else "Medium" if score >= 3 else "Low"
    concerns = [text for _, text in sorted(f.concerns, key=lambda c: -c[0])]
    reasons = (concerns + f.positives)[:3] if level != "Low" else (concerns[:1] + f.positives)[:3]
    return RiskAssessment(level=level, score=score, reasons=tuple(reasons))


# ---------------------------------------------------------------------------
# Formatting
# ---------------------------------------------------------------------------

LEVEL_EMOJI = {"Low": "🟢", "Medium": "🟡", "High": "🔴"}


def format_usd(value: float | None) -> str:
    """Compact dollar formatting: $1.2B, $3.4M, $56K, $0.000002329."""
    if value is None:
        return "n/a"
    for limit, suffix in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if abs(value) >= limit:
            return f"${value / limit:.2f}{suffix}"
    if abs(value) >= 1:
        return f"${value:,.2f}"
    if not value:
        return "$0"
    return "$" + f"{float(f'{value:.4g}'):.12f}".rstrip("0").rstrip(".")


def format_age(hours: float) -> str:
    """Human age: 45m, 5h, 3d, 2y 4mo."""
    if hours < 1:
        return f"{int(hours * 60)}m"
    if hours < 48:
        return f"{int(hours)}h"
    days = hours / 24
    if days < 60:
        return f"{int(days)}d"
    months = int(days / 30.44)
    years, months = divmod(months, 12)
    return f"{years}y {months}mo" if years else f"{months}mo"


def format_summary(address: str, market: MarketData | None, risk: RiskAssessment, now: float | None = None) -> str:
    """Build the Telegram reply: 5 lines max, then the disclaimer."""
    title = f"{market.name} (${market.symbol})" if market else f"{address[:4]}…{address[-4:]}"
    lines = [f"🛡 {title}: {LEVEL_EMOJI[risk.level]} {risk.level} risk"]
    if market:
        age = _pair_age_hours(market.pair_created_at_ms, now)
        lines.append(
            f"💲 {format_usd(market.price_usd)} · MC {format_usd(market.market_cap_usd)} · "
            f"Liq {format_usd(market.liquidity_usd)} · Vol 24h {format_usd(market.volume_24h_usd)}"
            + (f" · Age {format_age(age)}" if age is not None else "")
        )
    lines += [f"{i}. {reason}" for i, reason in enumerate(risk.reasons, start=1)]
    return "\n".join(lines[:5]) + f"\n\n{DISCLAIMER}"


# ---------------------------------------------------------------------------
# Fetching
# ---------------------------------------------------------------------------

async def _get_json(client: httpx.AsyncClient, url: str) -> Any | None:
    """GET a URL and return parsed JSON, or None on any error/timeout."""
    try:
        response = await client.get(url, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json()
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning("Request failed for %s: %s", url, exc)
        return None


async def check_contract(address: str, client: httpx.AsyncClient | None = None) -> str:
    """Fetch both sources in parallel and return the formatted risk summary."""
    own_client = client is None
    client = client or httpx.AsyncClient(headers={"Accept": "application/json"})
    try:
        dex_json, rug_json = await asyncio.gather(
            _get_json(client, DEXSCREENER_URL.format(address=address)),
            _get_json(client, RUGCHECK_URL.format(address=address)),
        )
    finally:
        if own_client:
            await client.aclose()

    if dex_json is None and rug_json is None:
        return "⚠️ I couldn't reach DexScreener or RugCheck right now. Please try again in a minute."

    market = parse_dexscreener(dex_json)
    security = parse_rugcheck(rug_json)
    if market is None and security is None:
        return f"🤷 I couldn't find any data for {address}. Is it a Solana token mint address?"
    return format_summary(address, market, assess_risk(market, security))
