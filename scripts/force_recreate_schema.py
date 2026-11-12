#!/usr/bin/env python3
"""
Force SQLAlchemy to recreate the database schema.

This script backs up existing data and recreates the tables with the current schema.
"""

import sys
import argparse
from pathlib import Path
import shutil
from datetime import datetime

def recreate_database(db_path: str, backup: bool = True) -> bool:
    """
    Recreate database with current schema.

    Args:
        db_path: Path to the database file
        backup: Whether to create a backup first

    Returns:
        True if successful
    """
    db_file = Path(db_path)

    if not db_file.exists():
        print(f"❌ Database not found: {db_path}")
        return False

    # Backup if requested
    if backup:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = db_file.parent / f"{db_file.stem}_backup_{timestamp}{db_file.suffix}"
        print(f"📦 Creating backup: {backup_path}")
        shutil.copy2(db_path, backup_path)
        print(f"✅ Backup created")

    # Import after backup is done
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

    from sqlalchemy import create_engine
    from pylantir.models import Base, WorklistItem

    # Create engine
    db_url = f"sqlite:///{db_path}"
    engine = create_engine(db_url)

    print(f"🔄 Recreating schema for: {db_path}")

    # Drop and recreate all tables
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)

    print(f"✅ Schema recreated successfully")
    print(f"⚠️  Note: Database is now empty. Restore from backup if needed.")

    return True


def main():
    parser = argparse.ArgumentParser(
        description="Recreate database schema (WARNING: deletes all data)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
WARNING: This will DELETE ALL DATA in the database!
The script creates a backup first, but use with caution.

Example:
  python scripts/force_recreate_schema.py --db-path /path/to/worklist.db
        """
    )

    parser.add_argument(
        "--db-path",
        required=True,
        help="Path to the worklist database file"
    )

    parser.add_argument(
        "--no-backup",
        action="store_true",
        help="Skip creating a backup (dangerous!)"
    )

    args = parser.parse_args()

    print("=" * 70)
    print("⚠️  WARNING: Database Schema Recreation")
    print("=" * 70)
    print()
    print("This will DELETE ALL DATA in the database!")

    if args.no_backup:
        print("⚠️  Backup is DISABLED - data will be lost!")
    else:
        print("✅ A backup will be created first")

    print()
    response = input("Type 'yes' to continue: ")

    if response.lower() != 'yes':
        print("❌ Aborted")
        return 1

    print()

    success = recreate_database(args.db_path, backup=not args.no_backup)

    print()
    print("=" * 70)

    if success:
        print("✅ Database schema recreated")
        print()
        print("Next steps:")
        print("  1. Restart your API server")
        print("  2. The database is now empty")
        print("  3. Run data sync to repopulate")
        return 0
    else:
        print("❌ Failed to recreate schema")
        return 1


if __name__ == "__main__":
    sys.exit(main())
