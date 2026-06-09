#!/usr/bin/env python3
"""Shared utilities for the fitness-tracker 2.0 system.

All scripts import from here to avoid duplicating data-loading, day-type
resolution, deficit calculation, and alert-generation logic.
"""

import os
import json
import csv
from datetime import date, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')

TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')
NUTRITION_PATH = os.path.join(DATA_DIR, 'nutrition_log.csv')
EXERCISE_PATH = os.path.join(DATA_DIR, 'exercise_log.csv')

MEAL_TYPES = ['breakfast', 'lunch', 'dinner', 'snack']
MEAL_TYPES_CN = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '零食'}

# ── Tracker ───────────────────────────────────────────────────────────────────

_default_tracker = {
    "_version": 2,
    "user": {"name": "", "current_weight_kg": None, "current_bodyfat_pct": None, "lean_body_mass_kg": None},
    "energy": {"ree": 2000},
    "targets": {"goal_weight_kg": None, "weekly_loss_kg": 0.5, "phases": []},
    "protein": {"target_g_per_kg": 1.8, "min_g_per_kg": 1.4, "warning_consecutive_days": 3},
    "deficit": {"mild": 300, "moderate": 500, "aggressive": 700, "max_consecutive_aggressive_days": 3},
    "day_types": {
        "training":    {"deficit_target": "mild",     "protein_g_per_kg": 2.0, "calorie_modifier_kcal": 0},
        "light_active": {"deficit_target": "moderate", "protein_g_per_kg": 1.8, "calorie_modifier_kcal": -100},
        "rest":        {"deficit_target": "moderate",  "protein_g_per_kg": 1.6, "calorie_modifier_kcal": -200},
    },
    "weekly_schedule": {
        "enabled": True,
        "pattern": {"1": "training", "2": "training", "3": "light_active", "4": "training", "5": "training", "6": "light_active", "7": "rest"},
        "fri_sat_deficit_boost_kcal": 200,
    },
    "diet_breaks": {
        "enabled": True,
        "every_weeks": 4,
        "duration_days": 7,
        "last_break_start": None,
        "in_break": False,
    },
    "overrides": {},
    "milestones": {"interval_kg": 2.0, "last_weight_kg": None, "hit": []},
    "review": {"cadence_days": 7, "last_review_date": None, "last_record_date": None, "warning_kg": 1.0, "critical_kg": 2.0},
    "defaults": {"meals": {"breakfast": 450, "lunch": 650, "dinner": 600}, "snack_calories_if_unrecorded": 0},
}


def load_tracker():
    if not os.path.exists(TRACKER_PATH):
        return dict(_default_tracker)
    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        t = json.load(f)
    # Deep-merge defaults for any missing keys (v1→v2 migration)
    _deep_defaults(t, _default_tracker)
    return t


def save_tracker(t):
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(TRACKER_PATH, 'w', encoding='utf-8') as f:
        json.dump(t, f, ensure_ascii=False, indent=2)


def _deep_defaults(target, defaults):
    for k, v in defaults.items():
        if k not in target:
            target[k] = v
        elif isinstance(v, dict) and isinstance(target[k], dict):
            _deep_defaults(target[k], v)


# ── CSV loaders ──────────────────────────────────────────────────────────────

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
            records.append({'date': d, 'weight': w, 'bodyfat': bf, 'muscle': m, 'lbm': round(lbm, 2)})
    records.sort(key=lambda r: r['date'])
    if limit:
        records = records[-limit:]
    return records


def load_nutrition():
    if not os.path.exists(NUTRITION_PATH):
        return []
    records = []
    with open(NUTRITION_PATH, 'r', encoding='utf-8') as f:
        reader = csv.reader(f)
        next(reader, None)
        for row in reader:
            if len(row) < 3:
                continue
            records.append({
                'date': row[0].strip(),
                'meal': row[1].strip(),
                'calories': float(row[2]),
                'protein': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
                'carbs': float(row[4]) if len(row) > 4 and row[4].strip() else 0,
                'fat': float(row[5]) if len(row) > 5 and row[5].strip() else 0,
                'note': row[6].strip() if len(row) > 6 else '',
            })
    return records


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
            records.append({
                'date': row[0].strip(),
                'type': row[1].strip(),
                'duration': int(row[2]) if len(row) > 2 and row[2].strip() else 0,
                'calories': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
                'note': row[4].strip() if len(row) > 4 else '',
            })
    return records


# ── Body computation ─────────────────────────────────────────────────────────

def get_current_weight(tracker):
    """Return the most recent weight (kg) from records or tracker."""
    records = load_records()
    if records:
        return records[-1]['weight']
    return tracker.get('user', {}).get('current_weight_kg')


def compute_7day_avg(records):
    if not records:
        return None
    window = min(7, len(records))
    recent = records[-window:]
    return round(sum(r['weight'] for r in recent) / len(recent), 2)


def compute_trend(records):
    """Short-term weight trend comparing last 7 days to previous 7."""
    if len(records) < 14:
        return None
    first = [r['weight'] for r in records[-14:-7]]
    second = [r['weight'] for r in records[-7:]]
    if not first or not second:
        return None
    return round(sum(second) / len(second) - sum(first) / len(first), 2)


# ── Day-type resolution ──────────────────────────────────────────────────────

def resolve_day_type(tracker, target_date=None):
    """Determine the day type for a given date (default: today).

    Priority: manual override > weekly_schedule > default('rest')
    """
    if target_date is None:
        target_date = date.today()
    ds = target_date.isoformat()

    overrides = tracker.get('overrides', {})
    if ds in overrides:
        return overrides[ds], 'override'

    ws = tracker.get('weekly_schedule', {})
    if ws.get('enabled'):
        iso_weekday = str(target_date.isoweekday())
        pattern = ws.get('pattern', {})
        if iso_weekday in pattern:
            return pattern[iso_weekday], 'weekly_schedule'

    return 'rest', 'default'


def get_day_type_config(tracker, day_type):
    """Return the full config dict for a day type."""
    return tracker.get('day_types', _default_tracker['day_types']).get(day_type, _default_tracker['day_types']['rest'])


# ── Target computation ───────────────────────────────────────────────────────

def compute_today_targets(tracker, target_date=None):
    """Compute today's calorie and protein targets based on day type and user profile."""
    if target_date is None:
        target_date = date.today()

    day_type, source = resolve_day_type(tracker, target_date)
    dt_config = get_day_type_config(tracker, day_type)
    weight = get_current_weight(tracker) or 70

    # Protein target from day_type config
    protein_g_per_kg = dt_config.get('protein_g_per_kg', tracker['protein']['target_g_per_kg'])
    protein_g = round(weight * protein_g_per_kg)

    # Calorie target: REE - deficit + day_type modifier
    ree = tracker['energy']['ree']
    deficit_level = dt_config['deficit_target']
    deficit_kcal = tracker['deficit'][deficit_level]
    modifier = dt_config.get('calorie_modifier_kcal', 0)

    # Diet break: override deficit to 0
    if tracker['diet_breaks']['in_break']:
        deficit_kcal = 0
        deficit_level = 'maintenance'

    # Fri/Sat boost
    ws = tracker.get('weekly_schedule', {})
    if ws.get('enabled') and ws.get('fri_sat_deficit_boost_kcal'):
        iso_weekday = target_date.isoweekday()
        if iso_weekday in (5, 6):
            deficit_kcal += ws['fri_sat_deficit_boost_kcal']

    calorie_target = ree - deficit_kcal + modifier
    # If in diet break, target = REE (maintenance)
    if deficit_kcal == 0 and deficit_level == 'maintenance':
        calorie_target = ree + modifier

    return {
        'calories_in': round(calorie_target),
        'protein_g': protein_g,
        'protein_g_per_kg': protein_g_per_kg,
        'deficit_kcal': deficit_kcal,
        'deficit_level': deficit_level,
    }, day_type, source


# ── Today's actual state ─────────────────────────────────────────────────────

def get_today_state(tracker, target_date=None):
    """Aggregate today's actual nutrition and exercise data.

    Returns (targets_dict, actual_dict, gaps_dict, day_type, source).
    """
    if target_date is None:
        target_date = date.today()
    ds = target_date.isoformat()

    targets, day_type, source = compute_today_targets(tracker, target_date)
    nutrition = load_nutrition()
    exercise = load_exercise()
    defaults_meals = tracker['defaults']['meals']
    snack_default = tracker['defaults'].get('snack_calories_if_unrecorded', 0)

    # Aggregate today's nutrition
    today_meals = defaultdict(lambda: {'calories': 0, 'protein': 0, 'carbs': 0, 'fat': 0, 'count': 0, 'auto_filled': False})
    logged_meals = set()

    for r in nutrition:
        if r['date'] != ds:
            continue
        m = r['meal']
        logged_meals.add(m)
        today_meals[m]['calories'] += r['calories']
        today_meals[m]['protein'] += r['protein']
        today_meals[m]['carbs'] += r['carbs']
        today_meals[m]['fat'] += r['fat']
        today_meals[m]['count'] += 1

    # Auto-fill unlogged meals
    auto_filled = []
    for meal in ['breakfast', 'lunch', 'dinner']:
        if meal not in logged_meals:
            default_cal = defaults_meals.get(meal, 0)
            today_meals[meal] = {'calories': default_cal, 'protein': 0, 'carbs': 0, 'fat': 0, 'count': 0, 'auto_filled': True}
            auto_filled.append(meal)
    if 'snack' not in logged_meals:
        today_meals['snack'] = {'calories': snack_default, 'protein': 0, 'carbs': 0, 'fat': 0, 'count': 0, 'auto_filled': False}

    total_cal = sum(v['calories'] for v in today_meals.values())
    total_pro = sum(v['protein'] for v in today_meals.values())
    total_carbs = sum(v['carbs'] for v in today_meals.values())
    total_fat = sum(v['fat'] for v in today_meals.values())

    # Today's exercise
    today_ex = [r for r in exercise if r['date'] == ds]
    exercise_kcal = sum(r['calories'] for r in today_ex)

    actual = {
        'calories_in': round(total_cal),
        'protein_g': round(total_pro, 1),
        'carbs_g': round(total_carbs, 1),
        'fat_g': round(total_fat, 1),
        'exercise_kcal': round(exercise_kcal),
        'meals_logged': sorted(logged_meals),
        'meals_auto_filled': auto_filled,
        'exercise_sessions': [{'type': e['type'], 'kcal': e['calories'], 'duration_min': e['duration']} for e in today_ex],
    }

    # Gaps
    deficit_now = round(tracker['energy']['ree'] + exercise_kcal - total_cal)
    gaps = {
        'protein_remaining_g': max(0, round(targets['protein_g'] - total_pro)),
        'calories_remaining': max(0, round(targets['calories_in'] - total_cal)),
        'deficit_now_kcal': deficit_now,
        'deficit_target_kcal': targets['deficit_kcal'],
    }

    return targets, actual, gaps, day_type, source


# ── Alerts ───────────────────────────────────────────────────────────────────

def generate_today_alerts(tracker, targets, actual, gaps, day_type):
    """Generate priority-sorted alerts for today's state."""
    alerts = []
    tracker_protein = tracker['protein']
    tracker_deficit = tracker['deficit']
    min_protein_g = round(get_current_weight(tracker) * tracker_protein['min_g_per_kg'])

    # 1. Protein gap (highest priority)
    if gaps['protein_remaining_g'] > 30:
        remaining_meals = len([m for m in ['lunch', 'dinner', 'snack'] if m not in actual['meals_logged']])
        if remaining_meals <= 1 and gaps['protein_remaining_g'] > 20:
            alerts.append({
                'priority': 1, 'level': 'warning', 'metric': 'protein',
                'message': f"蛋白质还差 {gaps['protein_remaining_g']}g，剩余餐次需优先补蛋白质",
                'action': f"晚餐建议至少 {gaps['protein_remaining_g']}g 蛋白质（约 {_protein_food_hint(gaps['protein_remaining_g'])}）"
            })
        else:
            alerts.append({
                'priority': 1, 'level': 'info', 'metric': 'protein',
                'message': f"蛋白质还差 {gaps['protein_remaining_g']}g",
                'action': f"剩余餐次每餐至少需要 {gaps['protein_remaining_g'] // max(1, remaining_meals)}g 蛋白质"
            })
    elif actual['protein_g'] < min_protein_g:
        alerts.append({
            'priority': 2, 'level': 'info', 'metric': 'protein',
            'message': f"蛋白质 {actual['protein_g']}g，已低于日最低目标 {min_protein_g}g",
            'action': '即使今天已基本吃完，也可以补一杯蛋白粉（约 25g 蛋白质，100 kcal）'
        })

    # 2. Deficit too large (metabolic adaptation risk)
    deficit_now = gaps['deficit_now_kcal']
    deficit_target = targets['deficit_kcal']
    dt_config = get_day_type_config(tracker, day_type)
    deficit_level = dt_config['deficit_target']
    aggressive = tracker_deficit['aggressive']

    if deficit_now > aggressive:
        alerts.append({
            'priority': 3, 'level': 'warning', 'metric': 'deficit_large',
            'message': f"今日缺口 {deficit_now} kcal 已超过激进上限 {aggressive} kcal",
            'action': '过大的缺口会在数日后引发代谢适应和食欲反弹。如果感觉累或饿，补充 200-300 kcal 的高蛋白食物。'
        })
    elif deficit_now > deficit_target + 200 and deficit_level in ('mild', 'moderate'):
        alerts.append({
            'priority': 4, 'level': 'info', 'metric': 'deficit_above_target',
            'message': f"今日缺口 {deficit_now} kcal 已超过 {day_type} 日目标 {deficit_target} kcal",
            'action': '温和缺口是最优状态。如果感觉饿，可以补充蛋白质零食。不要追求大缺口。'
        })

    # 3. Check consecutive aggressive deficit days
    alerts += _check_consecutive_aggressive(tracker)

    return sorted(alerts, key=lambda a: a['priority'])


def _check_consecutive_aggressive(tracker):
    """Check if recent days have had consecutive aggressive deficits."""
    nutrition = load_nutrition()
    exercise = load_exercise()
    aggressive = tracker['deficit']['aggressive']
    max_days = tracker['deficit']['max_consecutive_aggressive_days']
    ree = tracker['energy']['ree']

    # Aggregate last N days
    by_date = defaultdict(lambda: {'intake': 0, 'burn': 0})
    for r in nutrition:
        by_date[r['date']]['intake'] += r['calories']
    for r in exercise:
        by_date[r['date']]['burn'] += r['calories']

    today = date.today()
    consecutive = 0
    for i in range(1, max_days + 2):
        d = (today - timedelta(days=i)).isoformat()
        state = by_date.get(d, {'intake': 0, 'burn': 0})
        # Fill defaults for meals not logged
        defaults_meals = tracker['defaults']['meals']
        day_nut = [r for r in nutrition if r['date'] == d]
        logged = {r['meal'] for r in day_nut}
        intake = state['intake']
        for meal in ['breakfast', 'lunch', 'dinner']:
            if meal not in logged:
                intake += defaults_meals.get(meal, 0)
        deficit = ree + state['burn'] - intake
        if deficit > aggressive:
            consecutive += 1
        else:
            break

    alerts = []
    if consecutive >= max_days:
        alerts.append({
            'priority': 2, 'level': 'warning', 'metric': 'metabolic_adaptation_risk',
            'message': f"已连续 {consecutive} 天大缺口（>{aggressive} kcal），存在代谢适应风险",
            'action': '建议明天将热量提升至维持水平（REE），让身体恢复代谢率。或者安排一天饮食休息。'
        })
    return alerts


def _protein_food_hint(grams):
    """Give a concrete food suggestion for a protein target."""
    if grams <= 30:
        return f"{grams}g = 1 勺蛋白粉 或 2 个鸡蛋"
    elif grams <= 50:
        return f"{grams}g = {grams // 25} 勺蛋白粉 或 {grams // 30 * 100}g 鸡胸肉"
    else:
        return f"{grams}g = 约 {grams // 25} 勺蛋白粉 或 {round(grams / 0.23)}g 鸡胸肉"


# ── Weekly summary ───────────────────────────────────────────────────────────

def compute_week_summary(tracker, target_date=None, window_days=7):
    """Compute weekly averages, compliance, and alerts."""
    if target_date is None:
        target_date = date.today()
    start = target_date - timedelta(days=window_days - 1)

    nutrition = load_nutrition()
    exercise = load_exercise()
    records = load_records()
    defaults_meals = tracker['defaults']['meals']
    ree = tracker['energy']['ree']

    nut_by_date = defaultdict(lambda: defaultdict(float))
    nut_dates = set()
    for r in nutrition:
        nut_by_date[r['date']][r['meal']] += r['calories']
        nut_dates.add(r['date'])

    ex_by_date = defaultdict(float)
    for r in exercise:
        ex_by_date[r['date']] += r['calories']

    daily_cals = []
    daily_pro = []
    daily_deficit = []
    days_with_data = 0
    days_with_exercise = 0
    day_type_counts = defaultdict(int)
    protein_days_met = 0
    deficit_days_in_range = 0
    weight = get_current_weight(tracker) or 70

    for i in range(window_days):
        d = (start + timedelta(days=i))
        ds = d.isoformat()

        if ds not in nut_dates and not any(r['date'] == ds for r in exercise):
            continue  # skip days with no data at all

        days_with_data += 1
        dt, _ = resolve_day_type(tracker, d)
        day_type_counts[dt] += 1
        dt_config = get_day_type_config(tracker, dt)

        # Nutrition
        day_nut = nut_by_date.get(ds, {})
        logged_meals = set()
        day_pro = 0
        intake = 0

        for r in nutrition:
            if r['date'] == ds:
                logged_meals.add(r['meal'])
                day_pro += r['protein']
                intake += r['calories']

        for meal in ['breakfast', 'lunch', 'dinner']:
            if meal not in logged_meals:
                intake += defaults_meals.get(meal, 0)

        burn = ex_by_date.get(ds, 0)
        if burn > 0:
            days_with_exercise += 1
        deficit = ree + burn - intake

        daily_cals.append(intake)
        daily_pro.append(day_pro)
        daily_deficit.append(deficit)

        # Compliance
        protein_target_g = round(weight * dt_config['protein_g_per_kg'])
        if day_pro >= protein_target_g * 0.85:
            protein_days_met += 1

        deficit_target = tracker['deficit'].get(dt_config['deficit_target'], 500)
        if abs(deficit - deficit_target) <= 250:
            deficit_days_in_range += 1

    n = max(1, days_with_data)
    avg_pro_g_per_kg = round((sum(daily_pro) / n) / weight, 2) if daily_pro and weight else None

    week_alerts = []
    if avg_pro_g_per_kg is not None and avg_pro_g_per_kg < tracker['protein']['min_g_per_kg']:
        week_alerts.append({
            'priority': 1, 'level': 'warning', 'metric': 'protein_weekly',
            'message': f"本周平均蛋白质 {avg_pro_g_per_kg} g/kg，低于最低目标 {tracker['protein']['min_g_per_kg']} g/kg",
        })

    return {
        'days_with_data': days_with_data,
        'days_with_exercise': days_with_exercise,
        'day_type_breakdown': dict(day_type_counts),
        'averages': {
            'calories_in': round(sum(daily_cals) / n) if daily_cals else 0,
            'protein_g': round(sum(daily_pro) / n, 1) if daily_pro else 0,
            'protein_g_per_kg': avg_pro_g_per_kg,
            'exercise_kcal': round(sum(burn for d, burn in [(None, ex_by_date.get((start + timedelta(days=i)).isoformat(), 0)) for i in range(window_days)]) / n) if days_with_data > 0 else 0,
            'deficit_kcal': round(sum(daily_deficit) / n) if daily_deficit else 0,
        },
        'compliance': {
            'protein_days_met': protein_days_met,
            'protein_days_total': days_with_data,
            'deficit_days_in_range': deficit_days_in_range,
            'deficit_days_total': days_with_data,
        },
        'alerts': week_alerts,
    }


# ── Diet break ───────────────────────────────────────────────────────────────

def get_diet_break_status(tracker, target_date=None):
    if target_date is None:
        target_date = date.today()
    db = tracker['diet_breaks']
    if not db.get('enabled'):
        return {'in_break': False, 'enabled': False}

    in_break = db.get('in_break', False)
    last_start = db.get('last_break_start')
    every_weeks = db.get('every_weeks', 4)

    if in_break:
        # Calculate days remaining
        try:
            started = date.fromisoformat(last_start)
            elapsed = (target_date - started).days
            remaining = max(0, db.get('duration_days', 7) - elapsed)
        except (ValueError, TypeError):
            remaining = 0
        return {
            'in_break': True,
            'enabled': True,
            'started': last_start,
            'days_elapsed': elapsed if last_start else None,
            'days_remaining': remaining,
        }

    # Not in break — when is the next one?
    weeks_until = every_weeks
    if last_start:
        try:
            last = date.fromisoformat(last_start)
            days_since = (target_date - last).days
            weeks_since = days_since / 7.0
            weeks_until = max(1, every_weeks - int(weeks_since))
        except (ValueError, TypeError):
            pass

    next_break = target_date + timedelta(weeks=weeks_until)
    return {
        'in_break': False,
        'enabled': True,
        'weeks_until_next': weeks_until,
        'next_break_date': next_break.isoformat(),
    }


# ── Phase ────────────────────────────────────────────────────────────────────

def get_phase_info(tracker, target_date=None):
    if target_date is None:
        target_date = date.today()
    phases = tracker.get('targets', {}).get('phases', []) or tracker.get('phases', [])
    records = load_records()
    weight_7d = compute_7day_avg(records)

    for ph in phases:
        try:
            ps = date.fromisoformat(ph['start'])
            pe = date.fromisoformat(ph['end'])
        except (KeyError, ValueError):
            continue
        if ps <= target_date <= pe:
            days_total = (pe - ps).days
            days_elapsed = (target_date - ps).days
            progress_pct = round(min(100, max(0, days_elapsed / days_total * 100)), 1) if days_total > 0 else 0

            # On track?
            on_track = None
            sw = ph.get('start_weight')
            tw = ph.get('target_weight')
            if sw is not None and tw is not None and weight_7d is not None:
                expected_now = sw + (tw - sw) * min(1, max(0, days_elapsed / days_total))
                on_track = weight_7d <= expected_now + 0.5

            return {
                'name': ph.get('name', ''),
                'days_elapsed': max(0, days_elapsed),
                'days_total': days_total,
                'progress_pct': progress_pct,
                'on_track': on_track,
                'start_weight_kg': sw,
                'target_weight_kg': tw,
                'expected_weight_kg': round(sw + (tw - sw) * min(1, max(0, days_elapsed / days_total)), 1) if sw and tw and days_total > 0 else None,
                'current_7day_weight_kg': weight_7d,
            }
    return None
