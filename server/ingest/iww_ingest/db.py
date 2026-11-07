"""Database access: one connection per job and an idempotent upsert helper."""
from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

import psycopg
from psycopg import sql
from psycopg.types.json import Jsonb

CHUNK_ROWS = 500          # 500 rows × ≤ 25 columns stays far below Postgres's 65,535-parameter limit


def connect(url: str, job: str) -> psycopg.Connection:
    # prepare_threshold=None keeps this working even on Supabase's transaction pooler.
    return psycopg.connect(
        url,
        autocommit=True,
        application_name=f"iww-{job}",
        prepare_threshold=None,
        options="-c statement_timeout=60000",
        connect_timeout=15,
    )


def _adapt(value: Any) -> Any:
    return Jsonb(value) if isinstance(value, (dict, list)) else value


def upsert(
    conn: psycopg.Connection,
    table: str,
    rows: Sequence[Mapping[str, Any]],
    key: Sequence[str],
    on_conflict: Literal["nothing", "update"] = "nothing",
    update_cols: Iterable[str] | None = None,
) -> int:
    """Insert rows, resolving conflicts on `key`. Returns the number of rows inserted or updated.

    Rows go out in multi-row chunks (the pooler is ~200 ms away from GitHub's runners), and
    RETURNING counts exactly the rows that were written: inserted ones, plus updated ones on "update".
    """
    if not rows:
        return 0
    cols = list(rows[0].keys())
    # A key repeated within one statement makes "do update" fail, so the last occurrence wins.
    unique = list({tuple(r[k] for k in key): r for r in rows}.values())
    if on_conflict == "update":
        targets = [c for c in (update_cols or cols) if c not in key]
        action = sql.SQL("do update set {}").format(
            sql.SQL(", ").join(sql.SQL("{0} = excluded.{0}").format(sql.Identifier(c)) for c in targets)
        )
    else:
        action = sql.SQL("do nothing")
    row_tpl = sql.SQL("({})").format(sql.SQL(", ").join(sql.Placeholder() * len(cols)))
    written = 0
    with conn.cursor() as cur:
        for start in range(0, len(unique), CHUNK_ROWS):
            chunk = unique[start:start + CHUNK_ROWS]
            stmt = sql.SQL("insert into {table} ({cols}) values {vals} on conflict ({key}) {action} returning 1").format(
                table=sql.Identifier(table),
                cols=sql.SQL(", ").join(map(sql.Identifier, cols)),
                vals=sql.SQL(", ").join([row_tpl] * len(chunk)),
                key=sql.SQL(", ").join(map(sql.Identifier, key)),
                action=action,
            )
            cur.execute(stmt, [_adapt(r[c]) for r in chunk for c in cols])
            written += len(cur.fetchall())
    return written


def scalar(conn: psycopg.Connection, query: str, params: Sequence[Any] = ()) -> Any:
    with conn.cursor() as cur:
        cur.execute(query, params)
        row = cur.fetchone()
    return row[0] if row else None


def fetch_all(conn: psycopg.Connection, query: str, params: Sequence[Any] = ()) -> list[tuple]:
    with conn.cursor() as cur:
        cur.execute(query, params)
        return cur.fetchall()
