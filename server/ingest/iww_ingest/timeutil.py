"""Time helpers. Storage is UTC everywhere; MYT is only for local days (architecture §5)."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo

UTC = timezone.utc
MYT = ZoneInfo("Asia/Kuala_Lumpur")


def utcnow() -> datetime:
    return datetime.now(UTC)


def om_local_to_utc(value: str, utc_offset_seconds: int) -> datetime:
    """Open-Meteo returns naive ISO times in the requested zone; shift them to UTC."""
    naive = datetime.fromisoformat(value)
    return (naive - timedelta(seconds=utc_offset_seconds)).replace(tzinfo=UTC)


def floor_to(ts: datetime, minutes: int) -> datetime:
    step = minutes * 60
    epoch = int(ts.timestamp())
    return datetime.fromtimestamp(epoch - epoch % step, UTC)


def myt_date(ts: datetime) -> date:
    return ts.astimezone(MYT).date()


def from_unix(seconds: int | float) -> datetime:
    return datetime.fromtimestamp(seconds, UTC)
