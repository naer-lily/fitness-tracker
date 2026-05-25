#!/usr/bin/env python3
"""Record fitness data to CSV and update tracker metadata."""

import sys
import os
import json
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')
TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')


def main():
    if len(sys.argv) < 3:
        print("Usage: python3 record.py <weight_kg> <body_fat_pct> [muscle_kg]")
        print("  weight_kg    - 体重 (kg)，必填")
        print("  body_fat_pct - 体脂率 (%)，必填")
        print("  muscle_kg    - 肌肉量 (kg)，可选")
        sys.exit(1)

    weight = float(sys.argv[1])
    body_fat = float(sys.argv[2])
    muscle = sys.argv[3] if len(sys.argv) > 3 else ''

    lean_body_mass = weight * (1 - body_fat / 100)
    today = date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)

    write_header = not os.path.exists(RECORDS_PATH)

    with open(RECORDS_PATH, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("日期,体重kg,体脂率%,肌肉量kg,去脂体重kg\n")
        f.write(f"{today},{weight},{body_fat},{muscle},{lean_body_mass:.2f}\n")

    print(f"Recorded: {today} | {weight}kg | {body_fat}% | LBM: {lean_body_mass:.2f}kg")

    update_tracker(today)


def update_tracker(today_str):
    if not os.path.exists(TRACKER_PATH):
        return

    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        tracker = json.load(f)

    tracker['last_record'] = today_str

    with open(TRACKER_PATH, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


if __name__ == '__main__':
    main()
