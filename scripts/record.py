#!/usr/bin/env python3
"""Record body measurements — with embedded trend feedback.

Usage:
    python3 record.py <weight_kg> <body_fat_pct> [muscle_kg]

stdout JSON includes trend + milestone detection so the AI has immediate context.
"""

import sys
import os
import json
from datetime import date

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')

sys.path.insert(0, SCRIPT_DIR)
import common


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

    lean_body_mass = round(weight * (1 - body_fat / 100), 2)
    today_str = date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)
    write_header = not os.path.exists(RECORDS_PATH)

    with open(RECORDS_PATH, 'a', encoding='utf-8') as f:
        if write_header:
            f.write("日期,体重kg,体脂率%,肌肉量kg,去脂体重kg\n")
        f.write(f"{today_str},{weight},{body_fat},{muscle},{lean_body_mass}\n")

    # Update tracker
    tracker = common.load_tracker()
    tracker['review']['last_record_date'] = today_str
    tracker['user']['current_weight_kg'] = weight
    tracker['user']['current_bodyfat_pct'] = body_fat
    tracker['user']['lean_body_mass_kg'] = lean_body_mass
    common.save_tracker(tracker)

    # Build trend feedback
    records = common.load_records()
    trend_7d = common.compute_7day_avg(records)
    trend_diff = common.compute_trend(records)
    trend_dir = 'stable'
    if trend_diff is not None:
        if trend_diff < -0.1:
            trend_dir = 'down'
        elif trend_diff > 0.1:
            trend_dir = 'up'

    # Milestone check
    milestone = None
    interval = tracker['milestones']['interval_kg']
    last_milestone = tracker['milestones']['last_weight_kg']
    if last_milestone is not None:
        next_target = last_milestone - interval
        if trend_7d is not None and trend_7d <= next_target:
            milestone = {
                'weight': round(trend_7d, 1),
                'from': round(last_milestone, 1),
                'interval_kg': interval,
                'date': today_str,
            }
            tracker['milestones']['last_weight_kg'] = trend_7d
            tracker['milestones']['hit'].append(milestone)
            common.save_tracker(tracker)

    # Alerts
    alerts = []
    if weight - (trend_7d or weight) > 1.0:
        alerts.append({
            'priority': 3, 'level': 'info', 'metric': 'weight_spike',
            'message': f'单日体重比 7 日均线高 {round(weight - trend_7d, 1)}kg，可能是水分/钠摄入/排泄节律',
        })

    result = {
        'ok': True,
        'record': {
            'date': today_str,
            'weight_kg': weight,
            'bodyfat_pct': body_fat,
            'muscle_kg': muscle if muscle else None,
            'lean_body_mass_kg': lean_body_mass,
            'fat_mass_kg': round(weight - lean_body_mass, 2),
        },
        'trend': {
            'trend_7d_weight_kg': trend_7d,
            'trend_direction': trend_dir,
            'trend_14day_diff_kg': trend_diff,
        },
        'milestone': milestone,
        'alerts': alerts,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
