"""Integration tests against a real Postgres: `npm run serve` in database/test, then
IWW_TEST_DB_URL=postgresql://postgres@127.0.0.1:5544/postgres pytest -m db"""
import os
from datetime import datetime, timedelta, timezone

import pytest

from iww_ingest import db
from iww_ingest.runlog import RunLog

URL = os.environ.get("IWW_TEST_DB_URL")
pytestmark = [pytest.mark.db, pytest.mark.skipif(not URL, reason="IWW_TEST_DB_URL not set")]
T0 = datetime(2030, 1, 1, tzinfo=timezone.utc)          # far from any real data
KEY = ("location_id", "source", "observed_at")


@pytest.fixture
def conn():
    c = db.connect(URL, "test")
    c.execute("delete from observations where observed_at >= %s", (T0,))
    yield c
    c.execute("delete from observations where observed_at >= %s", (T0,))
    c.close()


def obs(i, temp=27.0):
    return {"location_id": 1, "source": "openmeteo_current", "observed_at": T0 + timedelta(minutes=15 * i),
            "temperature_c": temp, "raw": {"i": i}}


def count(conn):
    return db.scalar(conn, "select count(*) from observations where observed_at >= %s", (T0,))


def test_upsert_is_idempotent(conn):
    rows = [obs(i) for i in range(1200)]                  # spans several chunks
    assert db.upsert(conn, "observations", rows, KEY) == 1200
    assert db.upsert(conn, "observations", rows, KEY) == 0
    assert count(conn) == 1200


def test_do_nothing_keeps_the_first_value(conn):
    db.upsert(conn, "observations", [obs(0, 27.0)], KEY)
    db.upsert(conn, "observations", [obs(0, 30.0)], KEY, "nothing")
    assert db.scalar(conn, "select temperature_c from observations where observed_at = %s", (T0,)) == 27.0


def test_update_replaces_and_counts(conn):
    db.upsert(conn, "observations", [obs(0, 27.0)], KEY)
    assert db.upsert(conn, "observations", [obs(0, 30.0), obs(1, 31.0)], KEY, "update") == 2
    assert db.scalar(conn, "select temperature_c from observations where observed_at = %s", (T0,)) == 30.0


def test_duplicate_keys_in_one_batch_are_collapsed(conn):
    assert db.upsert(conn, "observations", [obs(0, 27.0), obs(0, 28.0)], KEY, "update") == 1
    assert db.scalar(conn, "select temperature_c from observations where observed_at = %s", (T0,)) == 28.0


def test_failed_step_rolls_back_and_run_is_logged(conn):
    log = RunLog("manual", "local", conn).start()
    with log.step("good"):
        log.rows("observations", db.upsert(conn, "observations", [obs(0)], KEY))
    with log.step("bad"):
        db.upsert(conn, "observations", [obs(1)], KEY)
        raise RuntimeError("source down")
    assert log.finish() == "partial"
    assert count(conn) == 1                                # the bad step's insert was rolled back
    status, steps, rows = db.fetch_all(conn, "select status, steps, rows_written from ingestion_runs where id = %s",
                                       (log.run_id,))[0]
    assert status == "partial" and [s["ok"] for s in steps] == [True, False] and rows == {"observations": 1}
