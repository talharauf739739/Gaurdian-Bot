"""Scam detection: links outside the allow-list, scam phrases, and admin impersonation."""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from urllib.parse import urlparse

# --- links -------------------------------------------------------------------


def domain_of(url: str) -> str:
    """Hostname of a URL (with or without scheme), lowercase, without 'www.'."""
    candidate = url.strip()
    if "://" not in candidate:
        candidate = "http://" + candidate
    host = (urlparse(candidate).hostname or "").lower().rstrip(".")
    return host[4:] if host.startswith("www.") else host


def is_allowed_domain(host: str, allowed: Iterable[str]) -> bool:
    """True if `host` is an allowed domain or one of its subdomains."""
    return any(host == d or host.endswith("." + d) for d in allowed)


def find_disallowed_links(urls: Iterable[str], allowed: Iterable[str]) -> list[str]:
    """URLs whose domain is not on the allow-list."""
    allowed = tuple(allowed)
    return [u for u in urls if domain_of(u) and not is_allowed_domain(domain_of(u), allowed)]


# --- phrases -----------------------------------------------------------------

SCAM_PATTERNS = tuple(
    re.compile(p, re.IGNORECASE)
    for p in (
        r"\bdm (me|us|admin)\b",
        r"\b(dm|message|inbox) (me )?for (help|support|assistance)\b",
        r"\bverify (your )?wallet\b",
        r"\bseed ?phrase\b",
        r"\b(secret )?recovery phrase\b",
        r"\bprivate key\b",
        r"\bconnect (your )?wallet\b",
        r"\bwallet (validation|sync|rectification|recovery)\b",
        r"\bclaim (your )?(free )?(airdrop|reward|rewards|tokens)\b",
        r"\bdouble your (sol|crypto|money|tokens)\b",
        r"\bsupport (team|ticket)\b.*\b(dm|message)\b",
    )
)
_SAFETY_ADVICE = re.compile(r"\b(never|don'?t|do not|dont|beware|warning)\b", re.IGNORECASE)


def find_scam_phrases(text: str) -> list[str]:
    """Matched scam phrases. Safety advice like 'never share your seed phrase' is ignored."""
    if not text or _SAFETY_ADVICE.search(text):
        return []
    return [m.group(0) for p in SCAM_PATTERNS if (m := p.search(text))]


# --- impersonation -----------------------------------------------------------

_LOOKALIKES = str.maketrans(
    {
        "1": "l", "i": "l", "|": "l", "!": "l", "0": "o", "5": "s", "$": "s",
        "3": "e", "4": "a", "@": "a", "7": "t", "8": "b",
        # Cyrillic letters that look Latin
        "а": "a", "е": "e", "о": "o", "р": "p", "с": "c", "у": "y", "х": "x", "і": "l", "к": "k", "м": "m",
    }
)
_DECOY_WORDS = ("official", "support", "admin", "team", "real", "help", "mod")
MIN_NAME_LENGTH = 4


def normalize_name(name: str | None) -> str:
    """Collapse look-alike characters and drop separators: 'Ta1ha_Rauf' -> 'talharauf'."""
    if not name:
        return ""
    text = unicodedata.normalize("NFKC", name).lower().translate(_LOOKALIKES)
    return re.sub(r"[^a-z0-9]", "", text)


def _variants(name: str | None) -> set[str]:
    """The normalized name, plus a version without decoy words like 'support'."""
    base = normalize_name(name)
    variants = {base} if base else set()
    stripped = base
    for word in _DECOY_WORDS:
        stripped = stripped.replace(word, "")
    if len(stripped) >= MIN_NAME_LENGTH:
        variants.add(stripped)
    return variants


def levenshtein(a: str, b: str) -> int:
    """Edit distance between two strings."""
    if len(a) < len(b):
        a, b = b, a
    previous = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        current = [i]
        for j, cb in enumerate(b, 1):
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + (ca != cb)))
        previous = current
    return previous[-1]


def find_impersonation(candidate_names: Iterable[str | None], admin_names: Iterable[str | None]) -> str | None:
    """Return the admin name the candidate imitates, or None.

    Catches identical names, look-alike characters (l vs 1, Cyrillic), extra underscores
    or dots, decoy words ('_support', 'official'), and one-letter typos.
    """
    admins = [(name, normalize_name(name)) for name in admin_names if name]
    candidates = set().union(*(_variants(n) for n in candidate_names)) if candidate_names else set()
    for original, admin in admins:
        if len(admin) < MIN_NAME_LENGTH:
            continue
        for candidate in candidates:
            if candidate == admin or (len(admin) >= 5 and levenshtein(candidate, admin) <= 1):
                return original
    return None
