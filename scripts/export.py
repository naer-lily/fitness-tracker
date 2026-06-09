#!/usr/bin/env python3
"""Export fitness data as structured CSV files — no plotting.

Output (stdout JSON):
  {
    "饮食明细_csv": "...",
    "运动明细_csv": "...",
    "每日汇总_csv": "...",
    "身体数据_csv": "...",
    "阶段信息_csv": "...",
    "参数": { "REE": 2000, "目标缺口": 600 }
  }
"""

import os, json, csv
from datetime import date, timedelta
from collections import defaultdict

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')

TEMP_DIR = os.path.join(
    os.environ.get('TEMP',
                   os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')),
    'opencode', 'fitness-tracker'
)

# ── Load ──────────────────────────────────────────────────────────────────────

def _load_csv(path):
    if not os.path.exists(path):
        return []
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            rows.append(r)
    return rows


def load_tracker():
    p = os.path.join(DATA_DIR, 'tracker.json')
    if not os.path.exists(p):
        return {}
    with open(p, 'r', encoding='utf-8') as f:
        return json.load(f)


def load_nutrition():
    rows = _load_csv(os.path.join(DATA_DIR, 'nutrition_log.csv'))
    # Normalise: original col names are Chinese
    for r in rows:
        r['热量kcal'] = float(r.get('热量kcal', 0) or 0)
        r['蛋白质g'] = float(r.get('蛋白质g', 0) or 0)
        r['碳水g'] = float(r.get('碳水g', 0) or 0)
        r['脂肪g'] = float(r.get('脂肪g', 0) or 0)
    return rows


def load_exercise():
    rows = _load_csv(os.path.join(DATA_DIR, 'exercise_log.csv'))
    for r in rows:
        r['消耗kcal'] = float(r.get('消耗kcal', 0) or 0)
    return rows


def load_weight():
    rows = _load_csv(os.path.join(DATA_DIR, 'records.csv'))
    records = []
    for r in rows:
        d = date.fromisoformat(r['日期'].strip())
        w = float(r['体重kg'])
        bf = float(r['体脂率%'])
        m = float(r['肌肉量kg']) if r.get('肌肉量kg', '').strip() else None
        lbm_raw = r.get('去脂体重kg', '').strip()
        lbm = float(lbm_raw) if lbm_raw else w * (1 - bf / 100)
        records.append({'日期': d, '体重kg': w, '体脂率%': bf, '肌肉量kg': m, '去脂体重kg': round(lbm, 2)})
    records.sort(key=lambda x: x['日期'])
    return records


# ── Helpers ───────────────────────────────────────────────────────────────────

def rolling_average(pairs, window=7):
    if not pairs:
        return []
    result = []
    for i in range(len(pairs)):
        start_i = max(0, i - window + 1)
        avg = sum(pairs[j][1] for j in range(start_i, i + 1)) / (i - start_i + 1)
        result.append((pairs[i][0], round(avg, 2)))
    return result


# ── CSV writers ───────────────────────────────────────────────────────────────

def write_nutrition_detail(nutrition_rows, out_dir):
    """Passthrough nutrition_log.csv with Chinese headers."""
    path = os.path.join(out_dir, '饮食明细.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['日期', '餐次', '热量(kcal)', '蛋白质(g)', '碳水(g)', '脂肪(g)', '备注'])
        for r in nutrition_rows:
            w.writerow([
                r['日期'], r['餐次'],
                r.get('热量kcal', ''), r.get('蛋白质g', ''), r.get('碳水g', ''), r.get('脂肪g', ''),
                r.get('备注', '')
            ])
    return path


def write_exercise_detail(exercise_rows, out_dir):
    """Passthrough exercise_log.csv with Chinese headers."""
    path = os.path.join(out_dir, '运动明细.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['日期', '运动类型', '时长(分钟)', '消耗(kcal)', '备注'])
        for r in exercise_rows:
            w.writerow([
                r['日期'], r['运动类型'], r.get('时长分钟', ''),
                r.get('消耗kcal', ''), r.get('备注', '')
            ])
    return path


def write_daily_summary(nutrition_rows, exercise_rows, tracker, today, out_dir):
    """14-day daily aggregation: intake, burn, deficit."""
    ree = tracker.get('ree', 2200)
    default_meals = tracker.get('default_meals', {
        'breakfast': 450, 'lunch': 650, 'dinner': 600, 'snack': 0,
    })

    # Aggregate nutrition by date+meal, and track which meals were explicitly recorded
    nut_by_date = defaultdict(lambda: defaultdict(float))
    recorded_meals = defaultdict(set)  # date -> set of meals that have at least one entry
    for r in nutrition_rows:
        nut_by_date[r['日期']][r['餐次']] += r.get('热量kcal', 0)
        recorded_meals[r['日期']].add(r['餐次'])

    # Aggregate exercise by date
    ex_by_date = defaultdict(float)
    for r in exercise_rows:
        ex_by_date[r['日期']] += r.get('消耗kcal', 0)

    start = today - timedelta(days=13)
    path = os.path.join(out_dir, '每日汇总.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['日期', '早餐(kcal)', '午餐(kcal)', '晚餐(kcal)', '零食(kcal)',
                     '总摄入(kcal)', '运动消耗(kcal)', 'REE(kcal)',
                     '纯缺口(kcal)', '脂肪校正缺口(kcal)', '有真实饮食数据'])

        d = start
        while d <= today:
            ds = d.isoformat()
            day_nut = nut_by_date.get(ds, {})
            day_recorded = recorded_meals.get(ds, set())

            # Use recorded value if meal was explicitly logged; otherwise fill default
            breakfast = day_nut.get('breakfast', 0) if 'breakfast' in day_recorded else default_meals.get('breakfast', 0)
            lunch     = day_nut.get('lunch', 0)     if 'lunch' in day_recorded     else default_meals.get('lunch', 0)
            dinner    = day_nut.get('dinner', 0)    if 'dinner' in day_recorded    else default_meals.get('dinner', 0)
            snack     = day_nut.get('snack', 0)     # snack has no default

            has_real = ds in recorded_meals
            total_intake = round(breakfast + lunch + dinner + snack)
            exercise_burn = round(ex_by_date.get(ds, 0))
            raw_deficit = round(ree + exercise_burn - total_intake)
            fat_deficit = round(raw_deficit * 0.7)

            w.writerow([ds, round(breakfast), round(lunch), round(dinner), round(snack),
                        total_intake, exercise_burn, ree,
                        raw_deficit, fat_deficit, '是' if has_real else '否'])
            d += timedelta(days=1)
    return path


def write_body_data(weight_records, out_dir):
    """Full timeline: weight, bodyfat, LBM, derived fat/lean mass, 7-day MA."""
    path = os.path.join(out_dir, '身体数据.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['日期', '体重(kg)', '体脂率(%)', '肌肉量(kg)', '去脂体重(kg)',
                     '脂肪量(kg)', '瘦体重(kg)', '7日均线体重(kg)'])

        w_pairs = [(r['日期'], r['体重kg']) for r in weight_records]
        win = min(7, max(2, len(weight_records)))
        ma = dict(rolling_average(w_pairs, win))

        for r in weight_records:
            fat_mass = round(r['体重kg'] * r['体脂率%'] / 100, 2)
            lean_mass = round(r['体重kg'] - fat_mass, 2)
            w.writerow([
                r['日期'].isoformat(), r['体重kg'], r['体脂率%'],
                r['肌肉量kg'] if r['肌肉量kg'] is not None else '',
                r['去脂体重kg'],
                fat_mass, lean_mass,
                ma.get(r['日期'], '')
            ])
    return path


def write_phase_info(tracker, today, out_dir):
    """Phase table: all phases, one row each, with computed daily deficit targets."""
    phases = tracker.get('phases', [])
    path = os.path.join(out_dir, '阶段信息.csv')
    with open(path, 'w', encoding='utf-8-sig', newline='') as f:
        w = csv.writer(f)
        w.writerow(['阶段名', '开始日期', '结束日期', '总天数', '已过天数', '剩余天数',
                     '起始体重(kg)', '目标体重(kg)', '需减体重(kg)',
                     '日均纯缺口(kcal)', '日均脂肪缺口(kcal)', '是否当前阶段'])

        for ph in phases:
            try:
                ps = date.fromisoformat(ph['start'])
                pe = date.fromisoformat(ph['end'])
            except (KeyError, ValueError):
                continue

            sw = ph.get('start_weight')
            tw = ph.get('target_weight')
            days_total = (pe - ps).days
            days_elapsed = (today - ps).days
            days_remaining = (pe - today).days
            is_current = ps <= today <= pe

            if sw is not None and tw is not None and days_total > 0:
                to_lose = round(sw - tw, 1)
                daily_deficit = round(to_lose * 7700 / days_total)
                daily_fat_deficit = round(daily_deficit / 0.7)
            else:
                to_lose = ''
                daily_deficit = ''
                daily_fat_deficit = ''

            w.writerow([
                ph.get('name', ''), ph.get('start', ''), ph.get('end', ''),
                days_total, max(0, days_elapsed), max(0, days_remaining),
                sw if sw is not None else '',
                tw if tw is not None else '',
                to_lose, daily_deficit, daily_fat_deficit,
                '是' if is_current else '否'
            ])
    return path


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    os.makedirs(TEMP_DIR, exist_ok=True)

    tracker = load_tracker()
    nutrition_rows = load_nutrition()
    exercise_rows = load_exercise()
    weight_records = load_weight()
    today = date.today()

    result = {
        '饮食明细_csv': write_nutrition_detail(nutrition_rows, TEMP_DIR),
        '运动明细_csv': write_exercise_detail(exercise_rows, TEMP_DIR),
        '每日汇总_csv': write_daily_summary(nutrition_rows, exercise_rows, tracker, today, TEMP_DIR),
        '身体数据_csv': write_body_data(weight_records, TEMP_DIR),
        '阶段信息_csv': write_phase_info(tracker, today, TEMP_DIR),
        '参数': {
            'REE': tracker.get('ree', 2200),
            '目标缺口': tracker.get('goal_deficit'),
            '默认餐次': tracker.get('default_meals', {}),
        },
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
