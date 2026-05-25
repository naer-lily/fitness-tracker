#!/usr/bin/env python3
"""Check review status, deviation level, and milestone progress.

Outputs a JSON object to stdout for the AI to consume.
Does NOT modify tracker.json (AI decides when to update last_review).

Usage:
    python3 review.py              # Report status only
    python3 review.py --mark-done  # Report + update last_review in tracker.json
"""

import os
import sys
import json
import csv
from datetime import date, timedelta

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')
TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')


def load_records(limit=None):
    if not os.path.exists(RECORDS_PATH):
        return []
    records = []
    with open(RECORDS_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            d = date.fromisoformat(row[0].strip())
            w = float(row[1])
            bf = float(row[2])
            m = float(row[3]) if len(row) > 3 and row[3].strip() else None
            lbm_raw = row[4].strip() if len(row) > 4 else ''
            lbm = float(lbm_raw) if lbm_raw else w * (1 - bf / 100)
            records.append({'date': d, 'weight': w, 'bodyfat': bf, 'muscle': m, 'lbm': lbm})
    records.sort(key=lambda r: r['date'])
    if limit:
        records = records[-limit:]
    return records


def load_tracker():
    if not os.path.exists(TRACKER_PATH):
        return None
    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tracker(tracker):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKER_PATH, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def compute_7day_avg(records):
    if not records:
        return None
    window = min(7, len(records))
    recent = records[-window:]
    return sum(r['weight'] for r in recent) / len(recent)


def get_current_phase(tracker, today):
    if not tracker or not tracker.get('phases'):
        return None
    for ph in tracker['phases']:
        try:
            ps = date.fromisoformat(ph['start'])
            pe = date.fromisoformat(ph['end'])
        except (KeyError, ValueError):
            continue
        if ps <= today <= pe:
            return ph
    return None


def compute_expected_weight(phase, tracker, today):
    if not phase or phase.get('target_weight') is None:
        return None
    try:
        ps = date.fromisoformat(phase['start'])
        pe = date.fromisoformat(phase['end'])
        target = phase['target_weight']
    except (KeyError, ValueError):
        return None

    if today < ps:
        return None
    if today >= pe:
        return target

    start_w = phase.get('start_weight')
    if start_w is None:
        return target

    total_days = (pe - ps).days
    elapsed = (today - ps).days
    if total_days <= 0:
        return target

    progress = max(0.0, min(1.0, elapsed / total_days))
    return start_w + (target - start_w) * progress


def compute_deviation(current_weight, expected_weight, tracker):
    if current_weight is None or expected_weight is None:
        return {'level': 'unknown', 'diff_kg': None, 'message': '数据不足，无法评估'}

    diff = round(current_weight - expected_weight, 2)
    warning = tracker.get('warning_kg', 1.0) if tracker else 1.0
    critical = tracker.get('critical_kg', 2.0) if tracker else 2.0

    if diff <= 0.3:
        return {'level': 'green', 'diff_kg': diff,
                'message': '进度正常或超前。'}
    elif diff <= warning:
        return {'level': 'yellow', 'diff_kg': diff,
                'message': f'轻微偏离目标 {diff}kg，需关注。'}
    else:
        return {'level': 'red', 'diff_kg': diff,
                'message': f'显著偏离目标 {diff}kg，建议深入回顾并考虑调整。'}


def check_milestone(current_weight, tracker):
    if not tracker or current_weight is None:
        return None
    interval = tracker.get('milestone_interval_kg', 2.0)
    last = tracker.get('last_milestone_weight')

    if last is None:
        return None

    next_target = last - interval
    if current_weight <= next_target:
        milestone = {
            'weight': round(current_weight, 1),
            'from': round(last, 1),
            'interval_kg': interval,
            'date': date.today().isoformat()
        }
        tracker['last_milestone_weight'] = current_weight
        if 'milestones_hit' not in tracker:
            tracker['milestones_hit'] = []
        tracker['milestones_hit'].append(milestone)
        save_tracker(tracker)
        return milestone
    return None


def main():
    today = date.today()
    mark_done = '--mark-done' in sys.argv

    tracker = load_tracker()
    records = load_records(limit=21)
    current_weight = compute_7day_avg(records)

    # 1. Review due?
    review_due = False
    days_since_review = None
    if tracker:
        lr_str = tracker.get('last_review')
        if lr_str:
            try:
                last_review = date.fromisoformat(lr_str[:10])
                cadence = tracker.get('review_cadence_days', 7)
                days_since_review = (today - last_review).days
                review_due = days_since_review >= cadence
            except (ValueError, TypeError):
                pass
        else:
            # No review ever done, but data exists
            if records:
                review_due = True

    # 2. Phase & expected weight
    phase = get_current_phase(tracker, today)
    expected_weight = compute_expected_weight(phase, tracker, today)

    # 3. Deviation
    deviation = compute_deviation(current_weight, expected_weight, tracker)

    # 4. Milestone
    milestone = check_milestone(current_weight, tracker)

    # 5. Days since last record
    days_since_record = None
    if tracker and tracker.get('last_record'):
        try:
            lr = date.fromisoformat(tracker['last_record'][:10])
            days_since_record = (today - lr).days
        except (ValueError, TypeError):
            pass

    # 6. Trend direction (short-term)
    trend = None
    if len(records) >= 14:
        first_half = [r['weight'] for r in records[-14:-7]]
        second_half = [r['weight'] for r in records[-7:]]
        if first_half and second_half:
            avg1 = sum(first_half) / len(first_half)
            avg2 = sum(second_half) / len(second_half)
            trend = round(avg2 - avg1, 2)

    # 7. Phase progress
    phase_progress = None
    if phase and phase.get('start_weight') and phase.get('target_weight') is not None:
        total_change = phase['target_weight'] - phase['start_weight']
        if total_change != 0 and current_weight is not None:
            current_change = current_weight - phase['start_weight']
            phase_progress = round(min(100, max(0, abs(current_change / total_change) * 100)), 1)
            if total_change < 0:
                phase_progress = -phase_progress  # negative means weight loss

    result = {
        'date': today.isoformat(),
        'review_due': review_due,
        'days_since_review': days_since_review,
        'days_since_record': days_since_record,
        'current_weight_7day_avg': round(current_weight, 2) if current_weight else None,
        'current_phase': phase['name'] if phase else None,
        'expected_weight': round(expected_weight, 2) if expected_weight else None,
        'deviation': deviation,
        'trend_14day': trend,
        'phase_progress_pct': phase_progress,
        'milestone': milestone,
        'records_count': len(records),
        'records_total': len(load_records())
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if mark_done and tracker and review_due:
        tracker['last_review'] = today.isoformat() + 'T00:00:00'
        save_tracker(tracker)


if __name__ == '__main__':
    main()
