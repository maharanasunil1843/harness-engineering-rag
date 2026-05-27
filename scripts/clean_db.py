#!/usr/bin/env python3
"""Truncate all ingestion tables. Usage: uv run python scripts/clean_db.py --yes"""
import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()

_TABLES = [
    "component_addresses_failure",
    "chunks",
    "benchmark_results",
    "harness_components",
    "failure_modes",
    "harnesses",
    "practitioners",
    "documents",
]

_TRUNCATE_SQL = [
    "TRUNCATE TABLE component_addresses_failure CASCADE",
    "TRUNCATE TABLE chunks CASCADE",
    "TRUNCATE TABLE benchmark_results CASCADE",
    "TRUNCATE TABLE harness_components RESTART IDENTITY CASCADE",
    "TRUNCATE TABLE failure_modes RESTART IDENTITY CASCADE",
    "TRUNCATE TABLE harnesses RESTART IDENTITY CASCADE",
    "TRUNCATE TABLE practitioners RESTART IDENTITY CASCADE",
    "TRUNCATE TABLE documents CASCADE",
]


def row_counts(conn) -> dict[str, int]:
    counts = {}
    for t in _TABLES:
        row = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()  # noqa: S608
        counts[t] = row[0]
    return counts


def main() -> None:
    import psycopg

    ap = argparse.ArgumentParser()
    ap.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    args = ap.parse_args()

    if not args.yes:
        print("This will DELETE all ingestion data. Pass --yes to confirm.")
        sys.exit(1)

    with psycopg.connect(os.environ["DATABASE_URL"]) as conn:
        print("Row counts BEFORE truncation:")
        for t, n in row_counts(conn).items():
            print(f"  {t}: {n}")

        for sql in _TRUNCATE_SQL:
            conn.execute(sql)
        conn.commit()

        print("\nRow counts AFTER truncation:")
        for t, n in row_counts(conn).items():
            print(f"  {t}: {n}")

    print("\nDone.")


if __name__ == "__main__":
    main()
