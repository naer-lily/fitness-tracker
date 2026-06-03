#!/usr/bin/env python3
"""Record daily exercise data and summarize activity.

Usage:
    exercise.py add <type> <calories> [--duration N] [--note "..."]
    exercise.py summary [--days N]
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


def load_exercise():
    if not os.path.exists(EXERCISE_PATH):
        return []
    records = []
    with open(EXERCISE_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            rec = {
                'date': row[0].strip(),
                'type': row[1].strip(),
                'duration': int(row[2]) if len(row) > 2 and row[2].strip() else 0,
                'calories': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
                'note': row[4].strip() if len(row) > 4 else '',
            }
            records.append(rec)
    return records


def cmd_add(args):
    """Append an exercise record to exercise_log.csv."""
    today = date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)
    write_header = not os.path.exists(EXERCISE_PATH)

    with open(EXERCISE_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['日期', '运动类型', '时长分钟', '消耗kcal', '备注'])
        writer.writerow([today, args.type, args.duration or '', args.calories, args.note or ''])

    dur_str = f' {args.duration}分钟' if args.duration else ''
    print(f'已记录 {today} {args.type}{dur_str}: {args.calories} kcal')
    if args.note:
        print(f'  备注: {args.note}')


def cmd_summary(args):
    """Output JSON summary of recent exercise activity."""
    days = args.days or 7
    today = date.today()
    start = today - timedelta(days=days - 1)

    records = load_exercise()

    by_date = defaultdict(list)
    for r in records:
        by_date[r['date']].append(r)

    daily = []
    total_cal = 0
    days_with_exercise = 0
    activity_types = defaultdict(lambda: {'count': 0, 'total_cal': 0, 'total_min': 0})

    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        entries = by_date.get(d, [])
        day_cal = sum(e['calories'] for e in entries)
        total_cal += day_cal

        if entries:
            days_with_exercise += 1

        for e in entries:
            at = activity_types[e['type']]
            at['count'] += 1
            at['total_cal'] += e['calories']
            at['total_min'] += e.get('duration', 0)

        daily.append({
            'date': d,
            'total_calories': round(day_cal),
            'activities': [
                {
                    'type': e['type'],
                    'duration': e.get('duration', 0),
                    'calories': e['calories'],
                    'note': e.get('note', ''),
                }
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
        'activity_breakdown': {
            k: {'count': v['count'], 'total_cal': round(v['total_cal']), 'total_min': v['total_min']}
            for k, v in sorted(activity_types.items())
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


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

    args = parser.parse_args()

    if args.cmd == 'add':
        cmd_add(args)
    elif args.cmd == 'summary':
        cmd_summary(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
