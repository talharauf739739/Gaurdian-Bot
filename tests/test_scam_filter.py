"""Tests for app.scam_filter."""

import pytest

from app import scam_filter as sf

ALLOWED = ("dexscreener.com", "solscan.io", "x.com")


@pytest.mark.parametrize(
    ("url", "domain"),
    [
        ("https://www.DexScreener.com/solana/abc", "dexscreener.com"),
        ("solscan.io/token/xyz", "solscan.io"),
        ("http://evil-airdrop.xyz/claim?x=1", "evil-airdrop.xyz"),
    ],
)
def test_domain_of(url: str, domain: str) -> None:
    assert sf.domain_of(url) == domain


def test_disallowed_links() -> None:
    urls = ["https://dexscreener.com/solana/x", "https://pro.solscan.io/t", "https://x.com.evil.io/a", "claim-sol.app"]
    assert sf.find_disallowed_links(urls, ALLOWED) == ["https://x.com.evil.io/a", "claim-sol.app"]


@pytest.mark.parametrize(
    "text",
    [
        "Having issues? DM me for support",
        "Please verify your wallet here to receive tokens",
        "send your seed phrase to restore access",
        "Claim your free airdrop now!!",
        "connect wallet to fix the sync error",
    ],
)
def test_scam_phrases_detected(text: str) -> None:
    assert sf.find_scam_phrases(text)


@pytest.mark.parametrize(
    "text",
    ["gm everyone", "Never share your seed phrase with anyone", "don't connect wallet to random sites", ""],
)
def test_safe_text_not_flagged(text: str) -> None:
    assert sf.find_scam_phrases(text) == []


ADMINS = ["talha_rauf", "Talha Rauf", "admin1"]


@pytest.mark.parametrize(
    "names",
    [
        ["talha_rauf_", None],  # extra underscore
        ["ta1ha_rauf", None],  # l vs 1
        [None, "Talha Rauf"],  # same display name
        ["talharauf_support", None],  # decoy word
        ["talha_raff", None],  # one-letter typo
        [None, "Тalha Rauf"],  # Cyrillic T
        ["admin_1", None],
    ],
)
def test_impersonation_detected(names: list) -> None:
    assert sf.find_impersonation(names, ADMINS) is not None


@pytest.mark.parametrize("names", [["crypto_mike", "Mike"], [None, "Sarah K"], ["talha", "Talha"], [None, None]])
def test_regular_users_not_flagged(names: list) -> None:
    assert sf.find_impersonation(names, ADMINS) is None


def test_levenshtein() -> None:
    assert sf.levenshtein("kitten", "sitting") == 3
    assert sf.levenshtein("", "abc") == 3
