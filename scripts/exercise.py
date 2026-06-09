#!/usr/bin/env python3
"""Record daily exercise — with embedded status feedback and day-type management.

Usage:
    exercise.py add <type> <calories> [--duration N] [--note "..."]
    exercise.py summary [--days N]
    exercise.py set-day-type <type> [--date YYYY-MM-DD]

After `add`, stdout includes today_summary (merged nutrition+exercise state) + alerts.
"""

import os
import sys
import csv
import json
import argparse
from datetime import date, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
EXERCISE_PATH = os.path.join(DATA_DIR, 'exercise_log.csv')

sys.path.insert(0, SCRIPT_DIR)
import common

VALID_DAY_TYPES = ['training', 'light_active', 'rest']


def cmd_add(args):
    """Append an exercise record and output today's full state."""
    today = date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)
    write_header = not os.path.exists(EXERCISE_PATH)

    with open(EXERCISE_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['日期', '运动类型', '时长分钟', '消耗kcal', '备注'])
        writer.writerow([today, args.type, args.duration or '', args.calories, args.note or ''])

    # Build response with today_summary (nutrition + exercise merged)
    tracker = common.load_tracker()
    targets, actual, gaps, dt, src = common.get_today_state(tracker)
    alerts = common.generate_today_alerts(tracker, targets, actual, gaps, dt)

    result = {
        'ok': True,
        'exercise': {
            'date': today,
            'type': args.type,
            'kcal': args.calories,
            'duration_min': args.duration or 0,
            'note': args.note or '',
        },
        'today_summary': {
            'day_type': dt,
            'exercise_total_kcal': actual['exercise_kcal'],
            'protein_g': actual['protein_g'],
            'protein_target_g': targets['protein_g'],
            'protein_gap_g': gaps['protein_remaining_g'],
            'calories_in': actual['calories_in'],
            'calorie_target': targets['calories_in'],
            'calories_remaining': gaps['calories_remaining'],
            'deficit_now_kcal': gaps['deficit_now_kcal'],
            'deficit_target_kcal': targets['deficit_kcal'],
            'deficit_level': targets['deficit_level'],
            'alerts': alerts,
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_summary(args):
    """Output N-day exercise summary with day-type inference."""
    days = args.days or 7
    today = date.today()
    start = today - timedelta(days=days - 1)

    tracker = common.load_tracker()
    records = common.load_exercise()

    by_date = defaultdict(list)
    for r in records:
        by_date[r['date']].append(r)

    daily = []
    total_cal = 0
    days_with_exercise = 0
    activity_types = defaultdict(lambda: {'count': 0, 'total_cal': 0, 'total_min': 0})
    day_type_counts = defaultdict(int)

    for i in range(days):
        d = (start + timedelta(days=i))
        ds = d.isoformat()
        entries = by_date.get(ds, [])
        day_cal = sum(e['calories'] for e in entries)
        total_cal += day_cal

        if entries:
            days_with_exercise += 1

        for e in entries:
            at = activity_types[e['type']]
            at['count'] += 1
            at['total_cal'] += e['calories']
            at['total_min'] += e.get('duration', 0)

        dt, src = common.resolve_day_type(tracker, d)
        day_type_counts[dt] += 1

        daily.append({
            'date': ds,
            'total_calories': round(day_cal),
            'day_type': dt,
            'day_type_source': src,
            'activities': [
                {'type': e['type'], 'duration': e.get('duration', 0), 'calories': e['calories'], 'note': e.get('note', '')}
                for e in entries
            ],
        })

    result = {
        'days': days,
        'start_date': start.isoformat(),
        'end_date': today.isoformat(),
        'daily': daily,
        'total_calories': round(total_cal),
        'avg_per_day': round(total_cal / days) if days > 0 else 0,
        'days_with_exercise': days_with_exercise,
        'day_type_summary': {
            'breakdown': dict(day_type_counts),
            'weekday_heavy': sum(day_type_counts.get(dt, 0) for dt in ['training']),
            'weekday_light': sum(day_type_counts.get(dt, 0) for dt in ['light_active']),
            'weekday_rest': sum(day_type_counts.get(dt, 0) for dt in ['rest']),
        },
        'activity_breakdown': {
            k: {'count': v['count'], 'total_cal': round(v['total_cal']), 'total_min': v['total_min']}
            for k, v in sorted(activity_types.items())
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_set_day_type(args):
    """Manually override the day type for a given date."""
    target_date = date.fromisoformat(args.date) if args.date else date.today()
    ds = target_date.isoformat()
    dt = args.type

    if dt not in VALID_DAY_TYPES:
        print(json.dumps({'error': f'无效日类型: {dt}，可选: {", ".join(VALID_DAY_TYPES)}'}))
        sys.exit(1)

    tracker = common.load_tracker()
    if 'overrides' not in tracker:
        tracker['overrides'] = {}
    tracker['overrides'][ds] = dt
    common.save_tracker(tracker)

    dt_config = common.get_day_type_config(tracker, dt)
    print(json.dumps({
        'ok': True,
        'date': ds,
        'day_type': dt,
        'label': {'training': '训练日', 'light_active': '轻度活动日', 'rest': '休息日'}.get(dt, dt),
        'protein_g_per_kg': dt_config['protein_g_per_kg'],
        'deficit_target': dt_config['deficit_target'],
        'overridden': True,
    }, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='记录和管理每日运动')
    sub = parser.add_subparsers(dest='cmd')

    p_add = sub.add_parser('add', help='记录运动')
    p_add.add_argument('type', help='运动类型 (如 跑步/力量训练/游泳)')
    p_add.add_argument('calories', type=float, help='消耗热量 (kcal)')
    p_add.add_argument('--duration', type=int, help='时长 (分钟)')
    p_add.add_argument('--note', help='备注')

    p_sum = sub.add_parser('summary', help='查看运动摘要')
    p_sum.add_argument('--days', type=int, default=7, help='统计天数 (默认7)')

    p_sdt = sub.add_parser('set-day-type', help='手动设置某天的日类型')
    p_sdt.add_argument('type', choices=VALID_DAY_TYPES, help='日类型: training / light_active / rest')
    p_sdt.add_argument('--date', help='日期 (YYYY-MM-DD)，默认今天')

    args = parser.parse_args()

    if args.cmd == 'add':
        cmd_add(args)
    elif args.cmd == 'summary':
        cmd_summary(args)
    elif args.cmd == 'set-day-type':
        cmd_set_day_type(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
