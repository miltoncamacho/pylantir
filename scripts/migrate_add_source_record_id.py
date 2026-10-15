#!/usr/bin/env python3
"""Add and optionally backfill stable source record IDs in a Pylantir SQLite DB."""

import argparse
import shutil
import sqlite3
import sys
from datetime import datetime
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db-path", required=True, help="Path to the SQLite worklist database")
    parser.add_argument("--backup", action="store_true", help="Create a timestamped backup first")
    parser.add_argument(
        "--backfill-source",
        action="append",
        default=[],
        metavar="OLD_NAME=CONFIG_NAME",
        help=(
            "For rows whose data_source matches OLD_NAME, copy accession_number to "
            "source_record_id and set data_source to CONFIG_NAME. A single NAME means "
            "both names are identical. Repeat for multiple configured sources. Only "
            "use this when accession_number was mapped from the upstream booking ID."
        ),
    )
    args = parser.parse_args()
    db_path = Path(args.db_path).expanduser().resolve()
    if not db_path.is_file():
        print(f"Database not found: {db_path}")
        return 1

    if args.backup:
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup = db_path.with_suffix(db_path.suffix + f".bak-{stamp}")
        shutil.copy2(db_path, backup)
        print(f"Backup created: {backup}")

    connection = sqlite3.connect(str(db_path))
    try:
        cursor = connection.cursor()
        columns = {row[1] for row in cursor.execute("PRAGMA table_info(worklist_items)")}
        if not columns:
            raise RuntimeError("worklist_items table does not exist")

        cursor.execute("BEGIN IMMEDIATE")
        if "source_record_id" not in columns:
            cursor.execute(
                "ALTER TABLE worklist_items "
                "ADD COLUMN source_record_id VARCHAR(255) DEFAULT NULL"
            )
            print("Added source_record_id column")
        else:
            print("source_record_id column already exists")

        for source_mapping in args.backfill_source:
            if "=" in source_mapping:
                old_name, configured_name = source_mapping.split("=", 1)
            else:
                old_name = configured_name = source_mapping
            if not old_name or not configured_name:
                raise RuntimeError(f"invalid source mapping: {source_mapping!r}")
            cursor.execute(
                "UPDATE worklist_items "
                "SET source_record_id = accession_number, data_source = ? "
                "WHERE data_source = ? AND source_record_id IS NULL "
                "AND accession_number IS NOT NULL AND TRIM(accession_number) != ''",
                (configured_name, old_name),
            )
            print(
                f"Backfilled {cursor.rowcount} row(s) for source "
                f"{old_name!r} as {configured_name!r}"
            )

        duplicates = cursor.execute(
            "SELECT data_source, source_record_id, COUNT(*) FROM worklist_items "
            "WHERE source_record_id IS NOT NULL "
            "GROUP BY data_source, source_record_id HAVING COUNT(*) > 1"
        ).fetchall()
        if duplicates:
            details = ", ".join(f"{source}/{record_id} ({count})" for source, record_id, count in duplicates)
            raise RuntimeError(f"duplicate source identities found: {details}")

        cursor.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS uq_worklist_source_record "
            "ON worklist_items(data_source, source_record_id) "
            "WHERE source_record_id IS NOT NULL"
        )
        connection.commit()
        print("Migration completed successfully")
        return 0
    except Exception as exc:
        connection.rollback()
        print(f"Migration failed; transaction rolled back: {exc}")
        return 1
    finally:
        connection.close()


if __name__ == "__main__":
    sys.exit(main())
