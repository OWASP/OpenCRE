#!/usr/bin/env python3
"""
Validate golden_dataset.json entries against the OpenCRE database.
Checks that all CRE IDs referenced in the dataset actually exist.
"""

import json
import sqlite3
import sys
from pathlib import Path


def validate_golden_dataset(golden_path: str, db_path: str) -> int:
    """Validate all CRE IDs in the golden dataset."""
    errors = 0

    # Load golden dataset
    with open(golden_path, "r") as f:
        entries = json.load(f)

    # Connect to database
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Get all existing CRE IDs
    cursor.execute("SELECT external_id FROM cre")
    existing_ids = {row[0] for row in cursor.fetchall()}

    print(f"📊 Found {len(existing_ids)} CREs in database")
    print(f"📊 Checking {len(entries)} golden entries...")
    print()

    for entry in entries:
        if entry["expected"]["decision"] != "linked":
            continue

        for cre_id in entry["expected"]["cre_ids"]:
            if cre_id not in existing_ids:
                print(f"❌ CRE ID not found: {cre_id} in {entry['id']}")
                errors += 1
            else:
                print(f"✅ {cre_id} OK in {entry['id']}")

    conn.close()

    if errors == 0:
        print(f"\n✅ All {len(entries)} entries validated successfully!")
    else:
        print(f"\n❌ {errors} errors found. Please fix the missing CRE IDs.")

    return errors


if __name__ == "__main__":
    if len(sys.argv) < 3:
        print(
            "Usage: python validate_golden_dataset.py <golden_dataset.json> <standards_cache.sqlite>"
        )
        sys.exit(1)

    golden_path = sys.argv[1]
    db_path = sys.argv[2]

    if not Path(golden_path).exists():
        print(f"❌ File not found: {golden_path}")
        sys.exit(1)

    if not Path(db_path).exists():
        print(f"❌ Database not found: {db_path}")
        sys.exit(1)

    sys.exit(validate_golden_dataset(golden_path, db_path))
