"""Shared HTTP client: 15 s timeout, retries with 1/3/9 s backoff on 5xx and network errors (architecture §6)."""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

from . import config

log = logging.getLogger(__name__)
_session: requests.Session | None = None


class HttpError(RuntimeError):
    def __init__(self, url: str, status: int | None, message: str):
        super().__init__(f"{message} ({status}) for {url}")
        self.url, self.status = url, status


def session() -> requests.Session:
    global _session
    if _session is None:
        email = config.settings().contact_email
        contact = f"; {email}" if email else ""
        _session = requests.Session()
        _session.headers["User-Agent"] = f"iww-ingest/1.0 (student project{contact})"
    return _session


def _request(url: str, params: dict[str, Any] | None, *, allow_404: bool = False) -> requests.Response:
    attempts = len(config.HTTP_BACKOFF_S) + 1
    for attempt in range(attempts):
        try:
            resp = session().get(url, params=params, timeout=config.HTTP_TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout) as exc:
            if attempt == attempts - 1:
                raise HttpError(url, None, f"network error: {exc}") from exc
        else:
            if resp.status_code < 400 or (allow_404 and resp.status_code == 404):
                return resp
            if resp.status_code < 500:                       # 4xx: retrying won't help
                raise HttpError(resp.url, resp.status_code, resp.text[:200])
            if attempt == attempts - 1:
                raise HttpError(resp.url, resp.status_code, "server error")
        delay = config.HTTP_BACKOFF_S[attempt]
        log.warning("retrying %s in %ss (attempt %d)", url, delay, attempt + 1)
        time.sleep(delay)
    raise AssertionError("unreachable")


def get_json(url: str, params: dict[str, Any] | None = None) -> tuple[Any, int, str]:
    """Returns (parsed JSON, HTTP status, final URL) so callers can log raw responses."""
    resp = _request(url, params)
    return resp.json(), resp.status_code, resp.url


def get_bytes(url: str) -> bytes | None:
    """Returns None on 404 (e.g. a satellite file that isn't published yet)."""
    resp = _request(url, None, allow_404=True)
    return None if resp.status_code == 404 else resp.content


def get_text(url: str, params: dict[str, Any] | None = None) -> str:
    return _request(url, params).text
