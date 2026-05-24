"""
Import Master DB CSV into Supabase.

Usage:
    python import_db.py --csv Master_Hashtag_DB.csv

Requires SUPABASE_URL and SUPABASE_KEY environment variables or .env file.
"""

import argparse
import os
import sys
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db import DatabaseManager


def main():
    parser = argparse.ArgumentParser(description="Import Master DB CSV to Supabase")
    parser.add_argument("--csv", default="Master_Hashtag_DB.csv",
                        help="Path to Master DB CSV file")
    parser.add_argument("--dry-run", action="store_true",
                        help="Validate without inserting")
    args = parser.parse_args()

    csv_path = os.path.join(os.path.dirname(__file__), args.csv)

    if not os.path.exists(csv_path):
        print(f"ERROR: File not found: {csv_path}")
        sys.exit(1)

    print(f"Connecting to Supabase...")
    print(f"  URL: {os.environ.get('SUPABASE_URL', 'NOT SET')}")

    db = DatabaseManager()
    if not db.connect():
        print("ERROR: Cannot connect to Supabase.")
        print("Set SUPABASE_URL and SUPABASE_KEY environment variables.")
        sys.exit(1)

    print(f"Connected. Importing from: {csv_path}")

    if args.dry_run:
        import csv
        with open(csv_path, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
        print(f"Dry run: {len(rows)} rows would be imported.")
        return

    success, fail = db.import_csv(csv_path)
    print(f"\nDone! Imported: {success} success, {fail} failed.")


if __name__ == "__main__":
    main()
