from datetime import datetime, timedelta, timezone

import numpy as np

from iww_ingest.features import bias
from iww_ingest.jobs import score
from iww_ingest.ml.models import SPECS

ISSUED = datetime(2026, 11, 8, 0, tzinfo=timezone.utc)


class Constant:
    """Stands in for a LightGBM booster: the same output for every row, and it checks the input shape."""

    def __init__(self, value: float):
        self.value = value

    def predict(self, x: np.ndarray) -> np.ndarray:
        assert x.shape[1] == len(bias.FEATURES)
        return np.full(len(x), self.value)


def rows(n: int, **override) -> list[dict]:
    base = {c: 10.0 for c in bias.FORECAST_COLUMNS} | {"humidity_pct": 97.0}
    return [{"target_time": ISSUED + timedelta(hours=h + 1), "lead_hours": h + 1, **base, **override}
            for h in range(n)]


def test_a_residual_model_writes_one_clipped_row_per_forecast_hour():
    out = score.score_rows(SPECS["bias_humidity"], Constant(5.0), None, 7, ISSUED, rows(3))
    assert len(out) == 3
    assert {r["variable"] for r in out} == {"humidity_pct"}
    assert all(r["value"] == 100.0 and r["base_value"] == 97.0 for r in out)
    assert [r["lead_hours"] for r in out] == [1, 2, 3]
    assert all(r["model_id"] == 7 and r["issued_at"] == ISSUED and r["base_model"] == "best_match" for r in out)


def test_a_missing_forecast_value_gets_no_prediction():
    out = score.score_rows(SPECS["bias_pressure"], Constant(0.5), None, 7, ISSUED, rows(2, pressure_hpa=None))
    assert out == []


def test_the_rain_model_writes_a_probability_and_a_yes_no():
    out = score.score_rows(SPECS["rain_occurrence"], Constant(0.42), 0.3, 9, ISSUED, rows(2))
    by_var = {}
    for r in out:
        by_var.setdefault(r["variable"], []).append(r["value"])
    assert by_var == {"rain_prob": [0.42, 0.42], "rain_yes": [1.0, 1.0]}


def test_no_forecast_rows_means_nothing_to_write():
    assert score.score_rows(SPECS["bias_wind"], Constant(1.0), None, 7, ISSUED, []) == []


def test_dry_run_without_a_database_logs_a_note_and_succeeds(monkeypatch):
    monkeypatch.setenv("SUPABASE_DB_URL", "")        # an empty value also stops .env from supplying one
    assert score.main(["--dry-run"]) == 0
