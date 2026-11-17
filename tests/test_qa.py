"""Tests for app.qa using the real knowledge/project.md."""

import pytest

from app import qa

KB = qa.KnowledgeBase.load()


def test_knowledge_file_loads() -> None:
    assert len(KB.entries) >= 10
    assert all(e.answer and "Keywords" not in e.answer for e in KB.entries)


@pytest.mark.parametrize(
    ("question", "expected"),
    [
        ("What is the total supply?", "1,000,000,000"),
        ("how many tokens are there?", "1,000,000,000"),
        ("Where can I buy GUARD?", "Jupiter"),
        ("is the LP locked or can they rug?", "burned"),
        ("when staking?", "Q2 2027"),
        ("who is the team behind this?", "Solana developers"),
        ("whats the roadmap for 2027?", "Q4 2027"),
        ("any airdrop coming?", "no airdrop"),
        ("what's the tax?", "0%"),
    ],
)
def test_answers_known_questions(question: str, expected: str) -> None:
    answer = KB.answer(question)
    assert answer is not None, question
    assert expected in answer


@pytest.mark.parametrize("question", ["What is your favorite pizza?", "Who won the football match yesterday?", "?"])
def test_refuses_unknown_questions(question: str) -> None:
    assert KB.answer(question) is None


def test_triggers() -> None:
    assert qa.is_question("what is the supply?", "GuardBot")
    assert qa.is_question("hey @guardbot supply", "GuardBot")
    assert not qa.is_question("gm everyone", "GuardBot")
    assert qa.strip_mention("@GuardBot what is the supply", "GuardBot") == "what is the supply"


def test_parse_knowledge_handles_keywords_and_empty_sections() -> None:
    entries = qa.parse_knowledge("# Title\nintro\n## Empty\n## Price\nKeywords: cost, value\nIt is cheap.\n")
    assert [e.title for e in entries] == ["Price"]
    assert "cost" in entries[0].strong
    assert entries[0].answer == "It is cheap."
