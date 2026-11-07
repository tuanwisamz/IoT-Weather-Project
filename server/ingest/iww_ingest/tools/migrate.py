"""Apply named migration files in order, each in one transaction (there's no psql on the dev machine).

    python -m iww_ingest.tools.migrate 0001_core 0004_rls 0005_seed
"""
from __future__ import annotations

import sys

from .. import config, db


def main(argv: list[str] | None = None) -> int:
    names = argv if argv is not None else sys.argv[1:]
    if not names:
        print(__doc__)
        return 1
    files = [config.MIGRATIONS_DIR / (n if n.endswith(".sql") else f"{n}.sql") for n in names]
    missing = [f.name for f in files if not f.exists()]
    if missing:
        print(f"not found: {missing}", file=sys.stderr)
        return 1
    cfg = config.settings()
    if not cfg.db_url:
        print("SUPABASE_DB_URL is not set", file=sys.stderr)
        return 1
    with db.connect(cfg.db_url, "migrate") as conn:
        for f in files:
            with conn.transaction(), conn.cursor() as cur:
                cur.execute(f.read_text(encoding="utf-8"))
            print(f"applied {f.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
