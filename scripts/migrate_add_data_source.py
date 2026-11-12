#!/usr/bin/env python3
"""
Safely rebuild worklist_items to match worklist_new.db schema.

Target schema (match worklist_new.db):
- data_source VARCHAR(255) NULL (no default)

Business rule:
- Existing rows should have data_source='REDCap' (backfilled during copy)

This script is defensive:
- Optional timestamped backup (--backup)
- Creates worklist_items_new, copies rows, verifies counts match
- Only then swaps tables
- Rolls back on error and refuses to run if leftover *_new or *_old tables exist
"""

import argparse
import shutil
import sqlite3
import sys
from pathlib import Path
from datetime import datetime

TABLE = "worklist_items"
NEW_TABLE = f"{TABLE}_new"
OLD_TABLE = f"{TABLE}_old"


CREATE_NEW_TABLE_SQL = f"""
CREATE TABLE {NEW_TABLE} (
  id INTEGER NOT NULL PRIMARY KEY,
  study_instance_uid VARCHAR(100),
  patient_name VARCHAR(100),
  patient_id VARCHAR(50),
  patient_birth_date VARCHAR(8),
  patient_sex VARCHAR(1),
  patient_weight_lb VARCHAR(10),
  accession_number VARCHAR(50),
  referring_physician_name VARCHAR(100),
  modality VARCHAR(10),
  study_description VARCHAR(100),
  scheduled_station_aetitle VARCHAR(100),
  scheduled_start_date VARCHAR(8),
  scheduled_start_time VARCHAR(6),
  performing_physician VARCHAR(100),
  procedure_description VARCHAR(200),
  protocol_name VARCHAR(100),
  station_name VARCHAR(100),
  hisris_coding_designator VARCHAR(100),
  performed_procedure_step_status VARCHAR,
  data_source VARCHAR(255)
);
"""


def backup_db(db_path: Path) -> Path:
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = db_path.with_suffix(db_path.suffix + f".bak-{ts}")
    shutil.copy2(db_path, backup_path)
    return backup_path


def table_exists(cur: sqlite3.Cursor, name: str) -> bool:
    cur.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=? LIMIT 1", (name,))
    return cur.fetchone() is not None


def column_exists(cur: sqlite3.Cursor, table: str, column: str) -> bool:
    cur.execute(f"PRAGMA table_info({table});")
    return any(row[1] == column for row in cur.fetchall())


def count_rows(cur: sqlite3.Cursor, table: str) -> int:
    cur.execute(f"SELECT COUNT(*) FROM {table};")
    return int(cur.fetchone()[0])


def build_insert_sql(old_has_data_source: bool) -> str:
    # If old table has data_source, keep it but coalesce NULLs to REDCap.
    # If it doesn't exist, set REDCap for all copied rows.
    if old_has_data_source:
        data_source_expr = "COALESCE(data_source, 'REDCap') AS data_source"
    else:
        data_source_expr = "'REDCap' AS data_source"

    return f"""
    INSERT INTO {NEW_TABLE} (
      id, study_instance_uid, patient_name, patient_id, patient_birth_date, patient_sex,
      patient_weight_lb, accession_number, referring_physician_name, modality,
      study_description, scheduled_station_aetitle, scheduled_start_date, scheduled_start_time,
      performing_physician, procedure_description, protocol_name, station_name,
      hisris_coding_designator, performed_procedure_step_status, data_source
    )
    SELECT
      id, study_instance_uid, patient_name, patient_id, patient_birth_date, patient_sex,
      patient_weight_lb, accession_number, referring_physician_name, modality,
      study_description, scheduled_station_aetitle, scheduled_start_date, scheduled_start_time,
      performing_physician, procedure_description, protocol_name, station_name,
      hisris_coding_designator, performed_procedure_step_status,
      {data_source_expr}
    FROM {TABLE};
    """


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Safely rebuild worklist_items to match worklist_new.db schema (data_source VARCHAR(255) nullable)."
    )
    ap.add_argument("--db-path", required=True, help="Path to the SQLite DB (e.g., worklist-prod.db)")
    ap.add_argument("--backup", action="store_true", help="Create a timestamped backup before migrating")
    args = ap.parse_args()

    db_file = Path(args.db_path)
    if not db_file.exists():
        print(f"❌ Database not found: {db_file}")
        return 1

    if args.backup:
        b = backup_db(db_file)
        print(f"🗄️  Backup created: {b}")

    print("=" * 70)
    print("Pylantir DB Migration: Rebuild worklist_items to match worklist_new.db")
    print("=" * 70)

    conn = None
    try:
        conn = sqlite3.connect(str(db_file))
        cur = conn.cursor()

        if not table_exists(cur, TABLE):
            print(f"❌ Table not found: {TABLE}")
            return 1

        # Guardrails: refuse to run if leftover tables exist (avoid confusion/data loss)
        if table_exists(cur, NEW_TABLE) or table_exists(cur, OLD_TABLE):
            print(f"❌ Found leftover table(s) '{NEW_TABLE}' or '{OLD_TABLE}'.")
            print("   Please inspect/rename/drop them manually (or restore from backup) before rerunning.")
            return 1

        before = count_rows(cur, TABLE)
        print(f"ℹ️  Rows in {TABLE} before: {before}")

        old_has_data_source = column_exists(cur, TABLE, "data_source")

        # Use a write transaction; IMMEDIATE avoids mid-flight writers
        cur.execute("BEGIN IMMEDIATE;")

        # 1) Create new table
        cur.execute(CREATE_NEW_TABLE_SQL)

        # 2) Copy data
        insert_sql = build_insert_sql(old_has_data_source)
        cur.execute(insert_sql)

        after_new = count_rows(cur, NEW_TABLE)
        print(f"ℹ️  Rows copied into {NEW_TABLE}: {after_new}")

        # 3) Verify counts match BEFORE swapping
        if after_new != before:
            raise RuntimeError(f"Row count mismatch: before={before}, new={after_new}. Aborting.")

        # 4) Swap (rename original -> old, new -> original)
        cur.execute(f"ALTER TABLE {TABLE} RENAME TO {OLD_TABLE};")
        cur.execute(f"ALTER TABLE {NEW_TABLE} RENAME TO {TABLE};")

        # 5) Final verification that new main table has expected rows
        after = count_rows(cur, TABLE)
        if after != before:
            raise RuntimeError(f"Post-swap row count mismatch: expected={before}, got={after}. Aborting.")

        # 6) Drop old table only after everything checks out
        cur.execute(f"DROP TABLE {OLD_TABLE};")

        conn.commit()

        print("✅ Migration completed successfully")
        print(f"ℹ️  Rows in {TABLE} after: {after}")
        print("✅ data_source is now VARCHAR(255) nullable (no default), matching worklist_new.db")
        print("✅ Existing rows have been backfilled to data_source='REDCap'")
        return 0

    except Exception as e:
        if conn is not None:
            try:
                conn.rollback()
            except Exception:
                pass
        print(f"❌ Migration failed: {e}")
        print("Your database should be unchanged due to rollback.")
        return 1

    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    sys.exit(main())
