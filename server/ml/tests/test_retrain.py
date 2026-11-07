import os
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import retrain  # noqa: E402
from iww_ingest import db  # noqa: E402
from iww_ingest.ml.models import Spec  # noqa: E402
from iww_ingest.runlog import RunLog  # noqa: E402

URL = os.environ.get("IWW_TEST_DB_URL")
SPEC = Spec("test_retrain", "v1.0", "wind_speed_kmh", "wind_speed_10m", "residual")
RESULT = {"_rounds": 100, "_threshold": None, "champion": "v1.0", "champion_score": 2.0, "challenger_score": 1.5}


def test_a_month_runs_from_local_midnight_to_local_midnight():
    start, end = retrain.month_bounds("2026-11")
    assert start == pd.Timestamp("2026-10-31T16:00:00Z")
    assert end == pd.Timestamp("2026-11-30T16:00:00Z")


def test_december_rolls_into_the_next_year():
    assert retrain.month_bounds("2026-12")[1] == pd.Timestamp("2026-12-31T16:00:00Z")


def test_the_scheduled_run_judges_the_month_that_just_ended():
    assert retrain.last_month(date(2026, 12, 2)) == "2026-11"
    assert retrain.last_month(date(2027, 1, 2)) == "2026-12"


class FakeBooster:
    def model_to_string(self) -> str:
        return "fake model"

    def feature_importance(self, kind: str) -> np.ndarray:
        return np.ones(len(retrain.tm.bias.FEATURES))


@pytest.fixture
def conn(monkeypatch):
    if not URL:
        pytest.skip("IWW_TEST_DB_URL not set")
    monkeypatch.setattr(retrain.tm, "usable", lambda spec, df: df)
    monkeypatch.setattr(retrain.tm, "fit", lambda spec, df, rounds: FakeBooster())
    c = db.connect(URL, "test")
    clean = "delete from ml_models where name = %s"
    c.execute(clean, (SPEC.name,))
    c.execute("""insert into ml_models (name, version, algorithm, features, artifact, is_active)
                 values (%s, 'v1.0', 'lightgbm', '{}', 'champion', true)""", (SPEC.name,))
    yield c
    c.execute(clean, (SPEC.name,))
    c.close()


def versions(conn) -> dict[str, bool]:
    return dict(db.fetch_all(conn, "select version, is_active from ml_models where name = %s", (SPEC.name,)))


def replace(conn) -> dict:
    run = RunLog("retrain", "local", conn).start()
    df = pd.DataFrame({"target_time": pd.date_range("2026-10-01", periods=3, freq="h", tz="UTC")})
    with run.step(SPEC.name) as step:
        step["note"] = retrain.activate(conn, SPEC, df, RESULT, "2026-11")
    run.finish()
    return run.steps[-1]


def test_a_winning_challenger_becomes_the_only_active_version(conn):
    assert replace(conn)["note"] == "v1.1"
    assert versions(conn) == {"v1.0": False, "v1.1": True}


def test_a_failed_replace_leaves_the_champion_active(conn, monkeypatch):
    monkeypatch.setattr(retrain, "next_version", lambda c, name: "v1.0")    # the insert hits unique (name, version)
    assert replace(conn)["ok"] is False
    assert versions(conn) == {"v1.0": True}
