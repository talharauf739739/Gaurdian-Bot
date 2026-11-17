"""Tests for app.storage."""

from app.storage import ActionLog


def test_log_and_count(tmp_path) -> None:
    log = ActionLog(tmp_path / "test.db")
    log.log("link_deleted", chat_id=1, user_id=10, username="spammer", detail="evil.xyz")
    log.log("link_deleted", chat_id=1, user_id=11)
    log.log("impersonator_flagged", chat_id=2, user_id=12)
    assert log.counts() == {"link_deleted": 2, "impersonator_flagged": 1}
    assert log.counts(chat_id=1) == {"link_deleted": 2}
    assert log.recent(1)[0][3] == "impersonator_flagged"
    log.close()
