import pytest

from iww_ingest.sources import metar


@pytest.mark.parametrize("wx, raining, thunder", [
    (None, False, False),
    ("", False, False),
    ("-RA", True, False),
    ("+TSRA", True, True),
    ("TSRA", True, True),
    ("-SHRA", True, False),
    ("DZ BR", True, False),
    ("VCSH", False, False),      # showers in the vicinity, not at the station
    ("TS", False, True),         # thunder heard, no precipitation
    ("VCTS", False, True),
    ("BR", False, False),
])
def test_wx_flags(wx, raining, thunder):
    assert metar.wx_flags(wx) == (raining, thunder)


def test_magnus_rh():
    assert metar.magnus_rh(25, 25) == 100.0
    assert metar.magnus_rh(33, 25) == pytest.approx(62.9, abs=0.1)
    assert metar.magnus_rh(None, 25) is None


def test_report_conversion():
    row = metar.parse_report({"obsTime": 1793422800, "temp": 33, "dewp": 25, "wdir": "VRB", "wspd": 5,
                              "altim": 1012, "wxString": "-RA", "rawOb": "METAR WMKI ..."})
    assert row["observed_at"].isoformat() == "2026-10-31T05:00:00+00:00"
    assert row["wind_speed_kmh"] == 9.3          # 5 kt × 1.852
    assert row["wind_dir_deg"] is None
    assert row["pressure_hpa"] == 1012.0
    assert row["is_raining"] is True and row["is_thunder"] is False


def test_fixture_parses(fixture):
    rows = metar.parse(fixture("metar.json"))
    assert rows and all(r["source"] == "metar_wmki" and r["observed_at"].minute == 0 for r in rows)
