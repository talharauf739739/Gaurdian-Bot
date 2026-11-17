"""Tests for app.contract_check (offline: HTTP is mocked)."""

import json
import time

import httpx
import pytest

from app import contract_check as cc

BONK = "DezXAZ8z7PnrnRJjz3wXBoRgixCa6xjnB7YaB1pPB263"
NOW = time.time()
DAY_MS = 86_400_000


def dex_payload(liquidity: float = 1_300_000, age_days: float = 900) -> list[dict]:
    return [
        {
            "baseToken": {"address": BONK, "name": "Bonk", "symbol": "Bonk"},
            "priceUsd": "0.000002329",
            "liquidity": {"usd": 1000},
            "volume": {"h24": 10},
            "marketCap": 1,
            "pairCreatedAt": int(NOW * 1000 - age_days * DAY_MS),
        },
        {
            "baseToken": {"address": BONK, "name": "Bonk", "symbol": "Bonk"},
            "priceUsd": "0.000002329",
            "liquidity": {"usd": liquidity},
            "volume": {"h24": 157975.9},
            "marketCap": 204963478,
            "pairCreatedAt": int(NOW * 1000 - age_days * DAY_MS),
            "url": "https://dexscreener.com/solana/x",
        },
    ]


def rug_payload(mint=None, freeze=None, top=(10.4, 9.5, 5.0), lp_locked=0, risks=()) -> dict:
    return {
        "token": {"mintAuthority": mint, "freezeAuthority": freeze},
        "topHolders": [{"pct": p} for p in top],
        "markets": [{"lp": {"baseUSD": 500, "quoteUSD": 500, "lpLockedPct": lp_locked}}],
        "risks": list(risks),
        "rugged": False,
    }


# --- address detection -----------------------------------------------------

def test_find_solana_address_in_text() -> None:
    assert cc.find_solana_address(f"is this safe? {BONK} thanks") == BONK


@pytest.mark.parametrize(
    "text",
    ["hello world", "0x6982508145454Ce325dDbE47a25d4ec3d2311933", "I" * 40, BONK[:-6]],
)
def test_find_solana_address_rejects_non_addresses(text: str) -> None:
    assert cc.find_solana_address(text) is None


# --- parsing ---------------------------------------------------------------

def test_parse_dexscreener_picks_most_liquid_pair() -> None:
    market = cc.parse_dexscreener(dex_payload())
    assert market is not None
    assert market.liquidity_usd == 1_300_000
    assert market.symbol == "Bonk"


def test_parse_dexscreener_empty() -> None:
    assert cc.parse_dexscreener([]) is None
    assert cc.parse_dexscreener(None) is None


def test_parse_rugcheck_extracts_fields() -> None:
    sec = cc.parse_rugcheck(
        rug_payload(mint="abc", risks=[{"name": "Single holder ownership", "level": "danger"}])
    )
    assert sec is not None
    assert sec.mint_authority == "abc"
    assert sec.top_holder_pct == pytest.approx(10.4)
    assert sec.top10_holders_pct == pytest.approx(24.9)
    assert sec.lp_locked_pct == 0
    assert sec.danger_flags == ("Single holder ownership",)


# --- scoring ---------------------------------------------------------------

def test_established_token_is_low_risk() -> None:
    risk = cc.assess_risk(cc.parse_dexscreener(dex_payload()), cc.parse_rugcheck(rug_payload()), now=NOW)
    assert risk.level == "Low"
    assert len(risk.reasons) == 3


def test_new_token_with_authorities_is_high_risk() -> None:
    market = cc.parse_dexscreener(dex_payload(liquidity=8_000, age_days=0.2))
    sec = cc.parse_rugcheck(rug_payload(mint="m", freeze="f", top=(45, 20, 10)))
    risk = cc.assess_risk(market, sec, now=NOW)
    assert risk.level == "High"
    assert any("Mint authority" in r or "Freeze authority" in r for r in risk.reasons)
    assert len(risk.reasons) == 3


def test_fresh_launchpad_token_without_liquidity_is_high_risk() -> None:
    payload = dex_payload(age_days=0.005)
    for pair in payload:
        pair.pop("liquidity")
        pair["marketCap"] = 10_480
    risk = cc.assess_risk(cc.parse_dexscreener(payload), cc.parse_rugcheck(rug_payload()), now=NOW)
    assert risk.level == "High"
    assert risk.reasons[0].startswith("Brand-new pair")


def test_missing_security_report_is_not_low() -> None:
    risk = cc.assess_risk(cc.parse_dexscreener(dex_payload(age_days=3)), None, now=NOW)
    assert risk.level == "Medium"


# --- formatting ------------------------------------------------------------

def test_format_summary_shape() -> None:
    market = cc.parse_dexscreener(dex_payload())
    risk = cc.assess_risk(market, cc.parse_rugcheck(rug_payload()), now=NOW)
    text = cc.format_summary(BONK, market, risk, now=NOW)
    body, disclaimer = text.rsplit("\n\n", 1)
    assert disclaimer == "Not financial advice. DYOR."
    assert len(body.splitlines()) <= 5
    assert "🟢 Low risk" in body
    assert "$1.30M" in body


@pytest.mark.parametrize(
    ("value", "expected"),
    [(None, "n/a"), (2_500_000_000, "$2.50B"), (1_329_894, "$1.33M"), (56_000, "$56.00K"), (0.000002329, "$0.000002329"), (0.5, "$0.5")],
)
def test_format_usd(value, expected) -> None:
    assert cc.format_usd(value) == expected


# --- end to end with mocked HTTP --------------------------------------------

def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_check_contract_success() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "dexscreener" in request.url.host:
            return httpx.Response(200, text=json.dumps(dex_payload()))
        return httpx.Response(200, json=rug_payload())

    async with _client(handler) as client:
        text = await cc.check_contract(BONK, client)
    assert text.startswith("🛡 Bonk ($Bonk)")
    assert text.endswith("Not financial advice. DYOR.")


@pytest.mark.asyncio
async def test_check_contract_both_apis_down() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectTimeout("timeout", request=request)

    async with _client(handler) as client:
        text = await cc.check_contract(BONK, client)
    assert "couldn't reach" in text


@pytest.mark.asyncio
async def test_check_contract_one_api_down_still_answers() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if "dexscreener" in request.url.host:
            return httpx.Response(200, json=dex_payload())
        return httpx.Response(503)

    async with _client(handler) as client:
        text = await cc.check_contract(BONK, client)
    assert "Security report unavailable" in text
