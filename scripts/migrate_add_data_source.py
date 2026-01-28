#!/usr/bin/env python3
"""
Database migration script to add data_source column to existing databases.

This migration adds the 'data_source' column to the worklist_items table
for installations upgrading from versions without multi-source support.

Usage:
    python scripts/migrate_add_data_source.py --db-path /path/to/worklist.db
"""

import sqlite3
import sys
import argparse
from pathlib import Path


def check_column_exists(cursor, table_name, column_name):
    """Check if a column exists in a table."""
    cursor.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cursor.fetchall()]
    return column_name in columns


def migrate_database(db_path: str) -> bool:
    """
    Add data_source column to worklist_items table if it doesn't exist.

    Args:
        db_path: Path to the SQLite database file

    Returns:
        True if migration was successful or not needed, False on error
    """
    db_file = Path(db_path)

    if not db_file.exists():
        print(f"❌ Database file not found: {db_path}")
        return False

    print(f"🔍 Checking database: {db_path}")

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if column already exists
        if check_column_exists(cursor, "worklist_items", "data_source"):
            print("✅ Column 'data_source' already exists - no migration needed")
            conn.close()
            return True

        print("📝 Adding 'data_source' column to worklist_items table...")

        # Add the column
        cursor.execute("""
            ALTER TABLE worklist_items
            ADD COLUMN data_source TEXT DEFAULT NULL
        """)

        conn.commit()

        # Verify the column was added
        if check_column_exists(cursor, "worklist_items", "data_source"):
            print("✅ Migration successful - 'data_source' column added")

            # Show current row count
            cursor.execute("SELECT COUNT(*) FROM worklist_items")
            count = cursor.fetchone()[0]
            print(f"ℹ️  Database contains {count} worklist items")
            print(f"ℹ️  Existing items will have data_source=NULL (legacy REDCap entries)")

            conn.close()
            return True
        else:
            print("❌ Migration verification failed")
            conn.close()
            return False

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description="Add data_source column to worklist database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Migrate default database
  python scripts/migrate_add_data_source.py --db-path /path/to/worklist.db

  # Migrate database from config
  python scripts/migrate_add_data_source.py --db-path ~/pylantir/worklist.db
        """
    )

    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the worklist database file"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("Pylantir Database Migration: Add data_source Column")
    print("=" * 70)
    print()

    success = migrate_database(args.db_path)

    print()
    print("=" * 70)

    if success:
        print("✅ Migration completed successfully")
        print()
        print("You can now:")
        print("  1. Restart your Pylantir API server")
        print("  2. Configure multiple data sources in your config.json")
        print("  3. Use the Calpendo plugin or other data sources")
        return 0
    else:
        print("❌ Migration failed")
        print()
        print("Please:")
        print("  1. Check the database path is correct")
        print("  2. Ensure you have write permissions")
        print("  3. Backup your database before retrying")
        return 1


if __name__ == "__main__":
    sys.exit(main())
