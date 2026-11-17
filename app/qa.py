"""Answer community questions from knowledge/project.md with keyword matching (free, no LLM).

The bot only answers with text written in the knowledge file, so it never invents facts.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

DEFAULT_KNOWLEDGE_PATH = Path(__file__).resolve().parent.parent / "knowledge" / "project.md"
MIN_SCORE = 0.4  # share of the question's words that must match an entry

STOPWORDS = frozenset(
    """a an the is are was were be been being am do does did have has had i you he she it we they
    me my your our their this that these those what which whom whose when where why how can could
    should would will shall may might must of in on at to for from by with about as into over under
    and or but if then so not no yes there here any some all please tell know want need anyone guys
    bro hey hi hello its im just also more most much very ok okay sir coming come soon now whats""".split()
)
_TOKEN = re.compile(r"[a-z0-9]+")
_KEYWORDS_LINE = re.compile(r"^\s*keywords\s*:\s*(.*)$", re.IGNORECASE)


def _stem(word: str) -> str:
    """Very small stemmer: 'tokens' -> 'token', but keeps 'class' and short words."""
    if len(word) > 3 and word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def tokenize(text: str) -> frozenset[str]:
    """Lowercase content words of `text` without stopwords."""
    return frozenset(
        _stem(t) for t in _TOKEN.findall(text.lower()) if t not in STOPWORDS and (len(t) > 1 or t.isdigit())
    )


@dataclass(frozen=True)
class Entry:
    """One answer from the knowledge file."""

    title: str
    answer: str
    strong: frozenset[str]  # words from the heading and Keywords line
    weak: frozenset[str]  # words from the answer text


def parse_knowledge(markdown: str) -> list[Entry]:
    """Split the knowledge markdown into entries, one per '## ' heading."""
    entries: list[Entry] = []
    title: str | None = None
    body: list[str] = []

    def flush() -> None:
        if title is None:
            return
        keywords = ""
        lines = []
        for line in body:
            match = _KEYWORDS_LINE.match(line)
            if match:
                keywords += " " + match.group(1).replace(",", " ")
            else:
                lines.append(line)
        answer = "\n".join(lines).strip()
        if answer:
            entries.append(Entry(title, answer, tokenize(f"{title} {keywords}"), tokenize(answer)))

    for line in markdown.splitlines():
        if line.startswith("## "):
            flush()
            title, body = line[3:].strip(), []
        elif title is not None:
            body.append(line)
    flush()
    return entries


def score(query: frozenset[str], entry: Entry) -> float:
    """0..1: how well the question's words are covered by the entry."""
    if not query:
        return 0.0
    total = sum(1.0 if t in entry.strong else 0.5 if t in entry.weak else 0.0 for t in query)
    return total / len(query)


class KnowledgeBase:
    """Holds the parsed knowledge file and finds the best answer for a question."""

    def __init__(self, entries: list[Entry]) -> None:
        self.entries = entries

    @classmethod
    def load(cls, path: Path = DEFAULT_KNOWLEDGE_PATH) -> "KnowledgeBase":
        """Read and parse the knowledge file (an empty base if the file is missing)."""
        try:
            return cls(parse_knowledge(Path(path).read_text(encoding="utf-8")))
        except FileNotFoundError:
            return cls([])

    def best_match(self, question: str) -> tuple[Entry | None, float]:
        """Return the highest scoring entry and its score."""
        query = tokenize(question)
        best: tuple[Entry | None, float] = (None, 0.0)
        for entry in self.entries:
            s = score(query, entry)
            if s > best[1]:
                best = (entry, s)
        return best

    def answer(self, question: str) -> str | None:
        """The answer text if a confident match exists, else None."""
        entry, s = self.best_match(question)
        return entry.answer if entry and s >= MIN_SCORE else None


def strip_mention(text: str, bot_username: str | None) -> str:
    """Remove '@botname' from the text."""
    if not bot_username:
        return text
    return re.sub(rf"@{re.escape(bot_username)}\b", " ", text, flags=re.IGNORECASE).strip()


def is_mentioned(text: str, bot_username: str | None) -> bool:
    """True if the message mentions the bot by @username."""
    return bool(bot_username) and f"@{bot_username}".lower() in text.lower()


def is_question(text: str, bot_username: str | None) -> bool:
    """Spec trigger: the bot is mentioned, or the message ends with '?'."""
    return is_mentioned(text, bot_username) or text.strip().endswith("?")
