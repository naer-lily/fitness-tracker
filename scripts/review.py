#!/usr/bin/env python3
"""Periodic review — multi-axis analysis for the AI to present to the user.

Outputs a comprehensive JSON object covering:
  - Review scheduling
  - Weight trend + phase deviation
  - Protein adequacy (crossed with LBM trend)
  - Metabolic adaptation risk
  - Diet break scheduling
  - Day-type compliance
  - Milestone detection

Usage:
    python3 review.py              # Report status only
    python3 review.py --mark-done  # Report + update last_review_date
"""

import os
import sys
import json
from datetime import date, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, SCRIPT_DIR)
import common


def compute_protein_adequacy(tracker, days=14):
    """Analyze protein intake vs targets, crossed with LBM trend."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    records = common.load_nutrition()
    weight_records = common.load_records()
    weight = common.get_current_weight(tracker) or 70

    target_g_per_kg = tracker['protein']['target_g_per_kg']
    min_g_per_kg = tracker['protein']['min_g_per_kg']
    target_g = round(weight * target_g_per_kg)
    min_g = round(weight * min_g_per_kg)

    daily_pro = defaultdict(float)
    for r in records:
        d = r['date']
        if start.isoformat() <= d <= today.isoformat():
            daily_pro[d] += r['protein']

    pro_vals = []
    for i in range(days):
        d = (start + timedelta(days=i))
        ds = d.isoformat()
        pro_vals.append(daily_pro.get(ds, 0))

    n = max(1, days)
    avg_g = round(sum(pro_vals) / n, 1)
    avg_g_per_kg = round(avg_g / weight, 2)

    met_days = sum(1 for p in pro_vals if p >= target_g * 0.85)
    below_days = sum(1 for p in pro_vals if p < min_g)

    # Consecutive below
    consecutive_below = 0
    for i in range(days - 1, -1, -1):
        d = (today - timedelta(days=i)).isoformat()
        if daily_pro.get(d, 0) < min_g:
            consecutive_below += 1
        else:
            break

    # LBM trend
    lbm_trend = _compute_lbm_trend(weight_records, days=14)
    lbm_protein_risk = False
    if lbm_trend and lbm_trend < -0.3 and avg_g_per_kg < min_g_per_kg:
        lbm_protein_risk = True

    return {
        'days': days,
        'avg_daily_g': avg_g,
        'avg_g_per_kg': avg_g_per_kg,
        'target_g_per_kg': target_g_per_kg,
        'target_daily_g': target_g,
        'min_daily_g': min_g,
        'met_target_days': met_days,
        'total_days_with_data': days,
        'consecutive_below_min': consecutive_below,
        'lbm_trend_kg': lbm_trend,
        'lbm_protein_risk': lbm_protein_risk,
        'warning': consecutive_below >= tracker['protein']['warning_consecutive_days'] or lbm_protein_risk,
    }


def compute_metabolic_risk(tracker, days=14):
    """Detect patterns that risk metabolic adaptation."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    nutrition = common.load_nutrition()
    exercise = common.load_exercise()
    ree = tracker['energy']['ree']
    defaults_meals = tracker['defaults']['meals']
    aggressive = tracker['deficit']['aggressive']
    max_consecutive = tracker['deficit']['max_consecutive_aggressive_days']
    max_sustained = tracker['deficit']['moderate']

    nut_by_date = defaultdict(lambda: defaultdict(float))
    nut_dates = set()
    for r in nutrition:
        nut_by_date[r['date']][r['meal']] += r['calories']
        nut_dates.add(r['date'])

    ex_by_date = defaultdict(float)
    for r in exercise:
        ex_by_date[r['date']] += r['calories']

    consecutive_aggressive = 0
    consecutive_large_deficit = 0
    max_consecutive_aggressive_seen = 0
    max_consecutive_large_seen = 0
    training_deficit_overlap = 0

    for i in range(days):
        d = (start + timedelta(days=i))
        ds = d.isoformat()

        day_nut = nut_by_date.get(ds, {})
        day_logged = set()
        intake = 0
        for r in nutrition:
            if r['date'] == ds:
                day_logged.add(r['meal'])
                intake += r['calories']

        for meal in ['breakfast', 'lunch', 'dinner']:
            if meal not in day_logged:
                intake += defaults_meals.get(meal, 0)

        burn = ex_by_date.get(ds, 0)
        deficit = ree + burn - intake

        if deficit > aggressive:
            consecutive_aggressive += 1
            max_consecutive_aggressive_seen = max(max_consecutive_aggressive_seen, consecutive_aggressive)
        else:
            consecutive_aggressive = 0

        if deficit > max_sustained:
            consecutive_large_deficit += 1
            max_consecutive_large_seen = max(max_consecutive_large_seen, consecutive_large_deficit)
        else:
            consecutive_large_deficit = 0

        # Heavy training + large deficit overlap
        dt, _ = common.resolve_day_type(tracker, d)
        if dt == 'training' and deficit > tracker['deficit']['mild'] + 200:
            training_deficit_overlap += 1

    risk_level = 'low'
    if max_consecutive_aggressive_seen >= max_consecutive:
        risk_level = 'high'
    elif max_consecutive_large_seen >= max_consecutive + 2:
        risk_level = 'moderate'

    return {
        'days': days,
        'max_consecutive_aggressive_days': max_consecutive_aggressive_seen,
        'max_consecutive_large_deficit_days': max_consecutive_large_seen,
        'aggressive_threshold_kcal': aggressive,
        'large_deficit_threshold_kcal': max_sustained,
        'training_deficit_overlap_days': training_deficit_overlap,
        'risk_level': risk_level,
    }


def compute_day_type_compliance(tracker, days=14):
    """Check whether nutrition matched day-type expectations."""
    today = date.today()
    start = today - timedelta(days=days - 1)
    nutrition = common.load_nutrition()
    exercise = common.load_exercise()
    ree = tracker['energy']['ree']
    defaults_meals = tracker['defaults']['meals']
    weight = common.get_current_weight(tracker) or 70

    nut_by_date = defaultdict(lambda: {'intake': 0, 'protein': 0, 'logged': set()})
    for r in nutrition:
        if start.isoformat() <= r['date'] <= today.isoformat():
            nut_by_date[r['date']]['intake'] += r['calories']
            nut_by_date[r['date']]['protein'] += r['protein']
            nut_by_date[r['date']]['logged'].add(r['meal'])

    ex_by_date = defaultdict(float)
    for r in exercise:
        if start.isoformat() <= r['date'] <= today.isoformat():
            ex_by_date[r['date']] += r['calories']

    training_days_pro = []
    training_days_def = []
    rest_days_cal = []

    for i in range(days):
        d = (start + timedelta(days=i))
        ds = d.isoformat()
        dt, _ = common.resolve_day_type(tracker, d)
        dt_config = common.get_day_type_config(tracker, dt)

        nd = nut_by_date.get(ds, {'intake': 0, 'protein': 0, 'logged': set()})
        intake = nd['intake']
        for meal in ['breakfast', 'lunch', 'dinner']:
            if meal not in nd['logged']:
                intake += defaults_meals.get(meal, 0)

        burn = ex_by_date.get(ds, 0)
        deficit = ree + burn - intake

        if dt == 'training':
            training_days_pro.append(nd['protein'])
            training_days_def.append(deficit)
        elif dt == 'rest':
            rest_days_cal.append(intake)

    return {
        'days': days,
        'training_days_avg_protein_g': round(sum(training_days_pro) / max(1, len(training_days_pro)), 1) if training_days_pro else 0,
        'training_days_avg_deficit_kcal': round(sum(training_days_def) / max(1, len(training_days_def))) if training_days_def else 0,
        'rest_days_avg_intake_kcal': round(sum(rest_days_cal) / max(1, len(rest_days_cal))) if rest_days_cal else 0,
        'training_days_count': len(training_days_pro),
        'rest_days_count': len(rest_days_cal),
    }


def _compute_lbm_trend(weight_records, days=14):
    """Compute LBM trend over recent days."""
    if len(weight_records) < 7:
        return None
    recent = weight_records[-days:]
    lbm_vals = [r['lbm'] for r in recent if r['lbm'] is not None]
    if len(lbm_vals) < 7:
        return None
    first = lbm_vals[:len(lbm_vals) // 2]
    second = lbm_vals[len(lbm_vals) // 2:]
    return round(sum(second) / len(second) - sum(first) / len(first), 2)


def main():
    today = date.today()
    mark_done = '--mark-done' in sys.argv

    tracker = common.load_tracker()
    records = common.load_records(limit=28)
    current_weight = common.compute_7day_avg(records)

    # 1. Review due?
    review_due = False
    days_since_review = None
    lr_str = tracker['review'].get('last_review_date') or tracker.get('last_review')
    if lr_str:
        try:
            last_review = date.fromisoformat(lr_str[:10])
            cadence = tracker['review']['cadence_days']
            days_since_review = (today - last_review).days
            review_due = days_since_review >= cadence
        except (ValueError, TypeError):
            pass
    else:
        if records:
            review_due = True

    # 2. Phase + deviation
    phase = common.get_phase_info(tracker, today)
    deviation = None
    if phase and phase.get('expected_weight_kg') and current_weight:
        diff = round(current_weight - phase['expected_weight_kg'], 2)
        warning = tracker['review']['warning_kg']
        critical = tracker['review']['critical_kg']
        if diff <= warning:
            level = 'green'
        elif diff <= critical:
            level = 'yellow'
        else:
            level = 'red'
        deviation = {
            'level': level,
            'diff_kg': diff,
            'current_7day_avg_kg': current_weight,
            'expected_kg': phase['expected_weight_kg'],
            'warning_kg': warning,
            'critical_kg': critical,
        }

    # 3. Trend
    trend = common.compute_trend(records)

    # 4. Milestone
    milestone = None
    interval = tracker['milestones']['interval_kg']
    last_ms = tracker['milestones']['last_weight_kg']
    if last_ms is not None and current_weight is not None and current_weight <= last_ms - interval:
        milestone = {
            'weight': round(current_weight, 1),
            'from': round(last_ms, 1),
            'interval_kg': interval,
            'date': today.isoformat(),
        }
        tracker['milestones']['last_weight_kg'] = current_weight
        tracker['milestones']['hit'].append(milestone)
        common.save_tracker(tracker)

    # 5. Days since last record
    days_since_record = None
    lrd = tracker['review'].get('last_record_date') or tracker.get('last_record')
    if lrd:
        try:
            days_since_record = (today - date.fromisoformat(lrd[:10])).days
        except (ValueError, TypeError):
            pass

    # 6. New dimensions
    protein_adequacy = compute_protein_adequacy(tracker)
    metabolic_risk = compute_metabolic_risk(tracker)
    day_type_compliance = compute_day_type_compliance(tracker)
    diet_break = common.get_diet_break_status(tracker)

    result = {
        'date': today.isoformat(),
        'review_due': review_due,
        'days_since_review': days_since_review,
        'days_since_record': days_since_record,

        'current_weight_7day_avg': round(current_weight, 2) if current_weight else None,
        'current_phase': phase['name'] if phase else None,
        'deviation': deviation,
        'trend_14day_kg': trend,

        'protein_adequacy': protein_adequacy,
        'metabolic_risk': metabolic_risk,
        'diet_break': diet_break,
        'day_type_compliance': day_type_compliance,

        'phase_progress': phase,
        'milestone': milestone,
        'records_count': len(records),
        'records_total': len(common.load_records()),
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))

    if mark_done and review_due:
        tracker['review']['last_review_date'] = today.isoformat() + 'T00:00:00'
        common.save_tracker(tracker)


if __name__ == '__main__':
    main()
