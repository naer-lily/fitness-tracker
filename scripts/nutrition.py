#!/usr/bin/env python3
"""Record daily meal intake — with embedded status feedback.

Usage:
    nutrition.py add <meal_type> <calories> [--protein N] [--carbs N] [--fat N] [--note "..."]
    nutrition.py summary [--days N]
    nutrition.py protein-check [--days N]
    nutrition.py defaults [--set key=value ...]

After `add`, stdout includes today_summary + alerts so the AI has everything
it needs without calling another script.
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

sys.path.insert(0, SCRIPT_DIR)
import common


def cmd_add(args):
    """Append a meal and output today's full state."""
    meal = args.meal
    if meal not in common.MEAL_TYPES:
        print(json.dumps({'error': f'无效餐次: {meal}，可选: {", ".join(common.MEAL_TYPES)}'}))
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

    # Build response with today_summary
    tracker = common.load_tracker()
    targets, actual, gaps, dt, src = common.get_today_state(tracker)
    alerts = common.generate_today_alerts(tracker, targets, actual, gaps, dt)

    result = {
        'ok': True,
        'meal': {
            'date': today,
            'meal': meal,
            'meal_cn': common.MEAL_TYPES_CN[meal],
            'kcal': calories,
            'protein_g': protein,
            'carbs_g': carbs,
            'fat_g': fat,
            'note': note,
        },
        'today_summary': {
            'day_type': dt,
            'meals_so_far': actual['meals_logged'],
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
    """Output N-day nutrition summary with protein analysis."""
    days = args.days or 7
    today = date.today()
    start = today - timedelta(days=days - 1)

    tracker = common.load_tracker()
    defaults = tracker['defaults']['meals']
    records = common.load_nutrition()

    by_date = defaultdict(lambda: defaultdict(list))
    for r in records:
        by_date[r['date']][r['meal']].append(r)

    daily = []
    for i in range(days):
        d = (start + timedelta(days=i)).isoformat()
        meals_data = {}
        total_cal = total_pro = total_carb = total_fat = 0
        any_actual = False

        for meal_type in common.MEAL_TYPES:
            entries = by_date.get(d, {}).get(meal_type, [])

            if entries:
                any_actual = True
                cal = sum(e['calories'] for e in entries)
                pro = sum(e['protein'] for e in entries)
                carb = sum(e['carbs'] for e in entries)
                f = sum(e['fat'] for e in entries)
                filled = False
                count = len(entries)
            elif meal_type == 'snack':
                cal = pro = carb = f = 0
                filled = False
                count = 0
            else:
                cal = defaults.get(meal_type, 0)
                pro = carb = f = 0
                filled = True
                count = 0

            meals_data[meal_type] = {
                'calories': cal, 'protein': pro, 'carbs': carb, 'fat': f,
                'auto_filled': filled, 'count': count,
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
    avg_pro = round(sum(d['total_protein'] for d in daily) / days, 1) if days > 0 else 0

    weight = common.get_current_weight(tracker) or 70
    avg_pro_g_per_kg = round(avg_pro / weight, 2) if weight else None

    result = {
        'days': days,
        'start_date': start.isoformat(),
        'end_date': today.isoformat(),
        'daily': daily,
        'avg_daily_calories': avg_cal,
        'days_with_actual_records': actual_days,
        'defaults_used': defaults,
        'protein_summary': {
            'avg_daily_g': avg_pro,
            'avg_g_per_kg': avg_pro_g_per_kg,
            'target_g_per_kg': tracker['protein']['target_g_per_kg'],
            'min_g_per_kg': tracker['protein']['min_g_per_kg'],
            'met_target': avg_pro_g_per_kg is not None and avg_pro_g_per_kg >= tracker['protein']['target_g_per_kg'],
        },
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_protein_check(args):
    """Quick protein adequacy check."""
    days = args.days or 7
    tracker = common.load_tracker()
    records = common.load_nutrition()
    weight = common.get_current_weight(tracker) or 70

    today = date.today()
    start = today - timedelta(days=days - 1)

    daily_pro = defaultdict(float)
    for r in records:
        d = r['date']
        if start.isoformat() <= d <= today.isoformat():
            daily_pro[d] += r['protein']

    pro_vals = [daily_pro[(start + timedelta(days=i)).isoformat()] for i in range(days)]
    avg_g = round(sum(pro_vals) / days, 1) if days > 0 else 0
    avg_g_per_kg = round(avg_g / weight, 2) if weight else None

    # Count consecutive days below min
    min_g_per_kg = tracker['protein']['min_g_per_kg']
    min_g = round(weight * min_g_per_kg)
    consecutive_below = 0
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        if daily_pro.get(d, 0) < min_g * 0.85:
            consecutive_below += 1
        else:
            break

    result = {
        'days': days,
        'avg_g_per_kg': avg_g_per_kg,
        'avg_daily_g': avg_g,
        'target_g_per_kg': tracker['protein']['target_g_per_kg'],
        'min_g_per_kg': min_g_per_kg,
        'target_daily_g': round(weight * tracker['protein']['target_g_per_kg']),
        'min_daily_g': min_g,
        'met_target': avg_g_per_kg is not None and avg_g_per_kg >= tracker['protein']['target_g_per_kg'],
        'below_min': avg_g_per_kg is not None and avg_g_per_kg < min_g_per_kg,
        'consecutive_below': consecutive_below,
        'warning': consecutive_below >= tracker['protein']['warning_consecutive_days'],
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))


def cmd_defaults(args):
    """View or set default meal calories."""
    tracker = common.load_tracker()

    if args.set:
        defaults = dict(tracker['defaults']['meals'])
        for pair in args.set:
            if '=' not in pair:
                print(json.dumps({'error': f'格式错误: {pair}，应为 key=value 如 breakfast=500'}))
                sys.exit(1)
            key, val = pair.split('=', 1)
            if key not in common.MEAL_TYPES:
                print(json.dumps({'error': f'无效餐次: {key}，可选: {", ".join(common.MEAL_TYPES)}'}))
                sys.exit(1)
            defaults[key] = float(val)
        tracker['defaults']['meals'] = defaults
        common.save_tracker(tracker)
        print(json.dumps({'status': 'updated', 'default_meals': defaults}, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({'default_meals': tracker['defaults']['meals']}, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='记录和管理每日饮食摄入')
    sub = parser.add_subparsers(dest='cmd')

    p_add = sub.add_parser('add', help='记录一餐')
    p_add.add_argument('meal', choices=list(common.MEAL_TYPES), help='餐次')
    p_add.add_argument('calories', type=float, help='热量 (kcal)')
    p_add.add_argument('--protein', type=float, help='蛋白质 (g) — 强烈推荐填写')
    p_add.add_argument('--carbs', type=float, help='碳水 (g)')
    p_add.add_argument('--fat', type=float, help='脂肪 (g)')
    p_add.add_argument('--note', help='备注')

    p_sum = sub.add_parser('summary', help='查看饮食摘要')
    p_sum.add_argument('--days', type=int, default=7, help='统计天数 (默认7)')

    p_pc = sub.add_parser('protein-check', help='快速检查蛋白质摄入趋势')
    p_pc.add_argument('--days', type=int, default=7, help='检查天数 (默认7)')

    p_def = sub.add_parser('defaults', help='查看/设置缺省值')
    p_def.add_argument('--set', nargs='*', metavar='KEY=VAL', help='设置缺省值')

    args = parser.parse_args()

    if args.cmd == 'add':
        cmd_add(args)
    elif args.cmd == 'summary':
        cmd_summary(args)
    elif args.cmd == 'protein-check':
        cmd_protein_check(args)
    elif args.cmd == 'defaults':
        cmd_defaults(args)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
