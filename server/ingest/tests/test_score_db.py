"""`score` against a real Postgres (see test_db.py for how to start one)."""
import os
from datetime import datetime, timedelta, timezone

import pytest

from iww_ingest import config, db
from iww_ingest.jobs import score

URL = os.environ.get("IWW_TEST_DB_URL")
pytestmark = [pytest.mark.db, pytest.mark.skipif(not URL, reason="IWW_TEST_DB_URL not set")]
MODEL_ID = 987654                       # no predictions exist for it, so every issue starts pending


def hour_ago(h: int) -> datetime:
    return datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0) - timedelta(hours=h)


@pytest.fixture
def conn():
    c = db.connect(URL, "test")
    issues = [hour_ago(h) for h in range(1, 6)]
    clean = "delete from forecasts where model = 'best_match' and origin = 'snapshot' and issued_at = any(%s)"
    c.execute(clean, (issues,))
    db.upsert(c, "forecasts", [{"location_id": config.LOCATION_ID, "model": "best_match", "origin": "snapshot",
                                "issued_at": t, "target_time": t + timedelta(hours=1), "temperature_c": 27.0}
                               for t in issues], ("location_id", "model", "origin", "issued_at", "target_time"))
    yield c, issues
    c.execute(clean, (issues,))
    c.close()


def test_issues_that_thin_would_delete_are_not_scored_again(conn):
    c, issues = conn
    pending = set(score.pending_issues(c, MODEL_ID)) & set(issues)
    thin_from = datetime.now(timezone.utc) - timedelta(hours=score.THIN_AFTER_HOURS)
    assert pending == {t for t in issues if t >= thin_from or t.hour in score.KEEP_UTC_HOURS}
    assert {hour_ago(1), hour_ago(2)} <= pending                     # recent issues are always scored
    assert any(t not in pending for t in issues)                     # 4 h and 5 h ago can't both be kept hours
