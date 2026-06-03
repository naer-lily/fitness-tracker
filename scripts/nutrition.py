#!/usr/bin/env python3
"""Record daily meal intake and summarize nutrition data.

Usage:
    nutrition.py add <meal_type> <calories> [--protein N] [--carbs N] [--fat N] [--note "..."]
    nutrition.py summary [--days N]
    nutrition.py defaults [--set key=value ...]
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
NUTRITION_PATH = os.path.join(DATA_DIR, 'nutrition_log.csv')
TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')

MEAL_TYPES = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '零食'}
MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']


def load_tracker():
    if not os.path.exists(TRACKER_PATH):
        return {}
    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def save_tracker(tracker):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKER_PATH, 'w', encoding='utf-8') as f:
        json.dump(tracker, f, ensure_ascii=False, indent=2)


def load_nutrition():
    if not os.path.exists(NUTRITION_PATH):
        return []
    records = []
    with open(NUTRITION_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        header = next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            rec = {
                'date': row[0].strip(),
                'meal': row[1].strip(),
                'calories': float(row[2]),
                'protein': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
                'carbs': float(row[4]) if len(row) > 4 and row[4].strip() else 0,
                'fat': float(row[5]) if len(row) > 5 and row[5].strip() else 0,
                'note': row[6].strip() if len(row) > 6 else '',
            }
            records.append(rec)
    return records


def get_default_meals(tracker):
    return tracker.get('default_meals', {
        'breakfast': 450,
        'lunch': 650,
        'dinner': 600,
        'snack': 200,
    })


def cmd_add(args):
    """Append a meal record to nutrition_log.csv."""
    meal = args.meal
    if meal not in MEAL_TYPES:
        print(json.dumps({'error': f'无效餐次: {meal}，可选: {", ".join(MEAL_TYPES)}'}))
        sys.exit(1)

    calories = args.calories
    protein = args.protein or 0
    carbs = args.carbs or 0
    fat = args.fat or 0
    note = args.note or ''
    today = date.today().isoformat()

    os.makedirs(DATA_DIR, exist_ok=True)
    write_header = not os.path.exists(NUTRITION_PATH)

    with open(NUTRITION_PATH, 'a', encoding='utf-8', newline='') as f:
        writer = csv.writer(f)
        if write_header:
            writer.writerow(['日期', '餐次', '热量kcal', '蛋白质g', '碳水g', '脂肪g', '备注'])
        writer.writerow([today, meal, calories, protein, carbs, fat, note])

    meal_cn = MEAL_TYPES[meal]
    macros = f' | 蛋白质{protein}g 碳水{carbs}g 脂肪{fat}g' if (protein or carbs or fat) else ''
    print(f'已记录 {today} {meal_cn}: {calories} kcal{macros}')
    if note:
        print(f'  备注: {note}')


def cmd_summary(args):
    """Output JSON summary of recent nutrition intake."""
    days = args.days or 7
    today = date.today()
    start = today - timedelta(days=days - 1)

    tracker = load_tracker()
    defaults = get_default_meals(tracker)
    records = load_nutrition()

    by_date = defaultdict(lambda: defaultdict(list))
    for r in records:
        d = r['date']
        by_date[d][r['meal']].append(r)

    daily = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        meals_data = {}
        total_cal = total_pro = total_carb = total_fat = 0
        any_actual = False

        for meal_type in MEAL_ORDER:
            entries = by_date.get(d, {}).get(meal_type, [])

            if entries:
                any_actual = True
                cal = sum(e['calories'] for e in entries)
                pro = sum(e['protein'] for e in entries)
                carb = sum(e['carbs'] for e in entries)
                f = sum(e['fat'] for e in entries)
                filled = False
                count = len(entries)
            else:
                default_cal = defaults.get(meal_type, 0)
                cal = default_cal
                pro = carb = f = 0  # defaults only have calories
                filled = True
                count = 0

            meals_data[meal_type] = {
                'calories': cal,
                'protein': pro,
                'carbs': carb,
                'fat': f,
                'auto_filled': filled,
                'count': count,
            }
            total_cal += cal
            total_pro += pro
            total_carb += carb
            total_fat += f

        daily.append({
            'date': d,
            'total_calories': round(total_cal),
            'total_protein': round(total_pro, 1),
            'total_carbs': round(total_carb, 1),
            'total_fat': round(total_fat, 1),
            'meals': meals_data,
            'has_actual_records': any_actual,
        })

    actual_days = sum(1 for d in daily if d['has_actual_records'])
    avg_cal = round(sum(d['total_calories'] for d in daily) / days) if days > 0 else 0

    result = {
        'days': days,
        'start_date': start.isoformat(),
        'end_date': today.isoformat(),
        'daily': daily,
        'avg_daily_calories': avg_cal,
        'days_with_actual_records': actual_days,
        'defaults_used': defaults,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_defaults(args):
    """View or set default meal calories."""
    tracker = load_tracker()

    if args.set:
        defaults = get_default_meals(tracker)
        for pair in args.set:
            if '=' not in pair:
                print(json.dumps({'error': f'格式错误: {pair}，应为 key=value 如 breakfast=500'}))
                sys.exit(1)
            key, val = pair.split('=', 1)
            if key not in MEAL_TYPES:
                print(json.dumps({'error': f'无效餐次: {key}，可选: {", ".join(MEAL_TYPES)}'}))
                sys.exit(1)
            defaults[key] = float(val)

        tracker['default_meals'] = defaults
        save_tracker(tracker)
        print(json.dumps({'status': 'updated', 'default_meals': defaults}, ensure_ascii=False, indent=2))
    else:
        defaults = get_default_meals(tracker)
        print(json.dumps({'default_meals': defaults}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='记录和管理每日饮食摄入')
    sub = parser.add_subparsers(dest='cmd')

    p_add = sub.add_parser('add', help='记录一餐')
    p_add.add_argument('meal', choices=list(MEAL_TYPES), help='餐次')
    p_add.add_argument('calories', type=float, help='热量 (kcal)')
    p_add.add_argument('--protein', type=float, help='蛋白质 (g)')
    p_add.add_argument('--carbs', type=float, help='碳水 (g)')
    p_add.add_argument('--fat', type=float, help='脂肪 (g)')
    p_add.add_argument('--note', help='备注')

    p_sum = sub.add_parser('summary', help='查看饮食摘要')
    p_sum.add_argument('--days', type=int, default=7, help='统计天数 (默认7)')

    p_def = sub.add_parser('defaults', help='查看/设置缺省值')
    p_def.add_argument('--set', nargs='*', metavar='KEY=VAL', help='设置缺省值，如 --set breakfast=500 lunch=700')

    args = parser.parse_args()

    if args.cmd == 'add':
        cmd_add(args)
    elif args.cmd == 'summary':
        cmd_summary(args)
    elif args.cmd == 'defaults':
        cmd_defaults(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
