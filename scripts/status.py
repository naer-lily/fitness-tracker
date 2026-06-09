#!/usr/bin/env python3
"""Fitness status snapshot — pure read, no side effects.

Usage:
    status.py [--date YYYY-MM-DD] [--days N]

Output (stdout JSON):
  {
    "date": "...",
    "day_type": "training",
    "day_type_source": "weekly_schedule",
    "body": { ... },
    "today": { "targets": {...}, "actual": {...}, "gaps": {...}, "alerts": [...] },
    "week": { ... },
    "diet_break": { ... },
    "phase": { ... }
  }
"""

import os
import sys
import json
import argparse
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import common


def cmd_status(tracker, target_date=None, window_days=7):
    if target_date is None:
        target_date = date.today()
    ds = target_date.isoformat()

    records = common.load_records()
    day_type, source = common.resolve_day_type(tracker, target_date)

    # ── Body ──
    latest_w = None
    latest_bf = None
    latest_lbm = None
    if records:
        r = records[-1]
        if r['date'] <= target_date:
            latest_w = r['weight']
            latest_bf = r['bodyfat']
            latest_lbm = r['lbm']

    # Only use records up to target_date for trend
    filtered = [r for r in records if r['date'] <= target_date]
    trend_7d = common.compute_7day_avg(filtered)
    trend_diff = common.compute_trend(filtered)
    trend_dir = 'stable'
    if trend_diff is not None:
        if trend_diff < -0.1:
            trend_dir = 'down'
        elif trend_diff > 0.1:
            trend_dir = 'up'

    days_since_record = None
    lrd = tracker.get('review', {}).get('last_record_date')
    if lrd:
        try:
            days_since_record = (target_date - date.fromisoformat(lrd[:10])).days
        except (ValueError, TypeError):
            pass

    phase_info = common.get_phase_info(tracker, target_date)
    weight_vs_expected = None
    if phase_info and phase_info.get('expected_weight_kg') and trend_7d:
        weight_vs_expected = round(trend_7d - phase_info['expected_weight_kg'], 2)

    body = {
        'latest_weight_kg': latest_w,
        'latest_bodyfat_pct': latest_bf,
        'latest_lean_mass_kg': latest_lbm,
        'trend_7d_weight_kg': trend_7d,
        'trend_direction': trend_dir,
        'trend_14day_diff_kg': trend_diff,
        'days_since_last_record': days_since_record,
        'weight_vs_phase_expected_kg': weight_vs_expected,
    }

    # ── Today ──
    targets, actual, gaps, dt, src = common.get_today_state(tracker, target_date)
    today_alerts = common.generate_today_alerts(tracker, targets, actual, gaps, dt)

    # Days-since-record alert
    if days_since_record is not None and days_since_record > 3:
        today_alerts.append({
            'priority': 5, 'level': 'info', 'metric': 'stale_record',
            'message': f'已有 {days_since_record} 天未记录体重',
        })

    today = {
        'targets': targets,
        'actual': actual,
        'gaps': gaps,
        'alerts': today_alerts,
    }

    # ── Week ──
    week = common.compute_week_summary(tracker, target_date, window_days)

    # ── Diet break ──
    diet_break = common.get_diet_break_status(tracker, target_date)

    # ── Phase ──
    phase_out = phase_info

    result = {
        'date': ds,
        'day_type': dt,
        'day_type_source': src,
        'body': body,
        'today': today,
        'week': week,
        'diet_break': diet_break,
        'phase': phase_out,
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


def main():
    parser = argparse.ArgumentParser(description='查看当前健身状态快照')
    parser.add_argument('--date', help='指定日期 (YYYY-MM-DD)，默认今天')
    parser.add_argument('--days', type=int, default=7, help='周统计窗口天数 (默认7)')
    args = parser.parse_args()

    target_date = date.fromisoformat(args.date) if args.date else date.today()
    tracker = common.load_tracker()
    cmd_status(tracker, target_date, args.days)


if __name__ == '__main__':
    main()
