"""observe: every 10 min. Open-Meteo current + METAR."""
from __future__ import annotations

import argparse
import sys

from ..runlog import RunLog
from ..sources import metar, openmeteo
from ._common import base_parser, run, write

OBS_KEY = ("location_id", "source", "observed_at")


def body(log: RunLog, args: argparse.Namespace) -> None:
    with log.step("om_current"):
        write(log, "observations", [openmeteo.parse_current(openmeteo.fetch_current())], OBS_KEY, "nothing")

    with log.step("metar"):
        # Corrected reports (COR) replace the original, so METAR updates on conflict.
        write(log, "observations", metar.parse(metar.fetch(hours=3)), OBS_KEY, "update")


def main(argv: list[str] | None = None) -> int:
    return run("observe", base_parser("observe"), body, argv)


if __name__ == "__main__":
    sys.exit(main())
