#!/usr/bin/env python3
"""Generate fitness dashboard PNG with matplotlib.

Rows (4):
  1. Last 28-day weight trend (7-day MA)
  2. Last 14-day calorie intake + deficit (stacked bar / bar)
  3. Body fat trend (7-day MA) + weekly loss rate
  4. Full plan weight trend (raw daily points, no smoothing)

Output: dashboard.png
"""

import os
import os.path
import json
import csv
from datetime import date, datetime, timedelta
from collections import defaultdict

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import matplotlib.ticker as mticker
import numpy as np

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')
TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')
NUTRITION_PATH = os.path.join(DATA_DIR, 'nutrition_log.csv')
EXERCISE_PATH = os.path.join(DATA_DIR, 'exercise_log.csv')

TEMP_DIR = os.path.join(
    os.environ.get('TEMP',
                   os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')),
    'opencode', 'fitness-tracker'
)

MEAL_LABELS = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '零食'}
MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']
MEAL_COLORS = {'breakfast': '#FF9F43', 'lunch': '#EE5A24', 'dinner': '#0ABDE3', 'snack': '#10AC84'}

# ── Font ──────────────────────────────────────────────────────────────────

_FONT_DIR = os.path.join(SKILL_ROOT, 'fonts')

def _register_chinese_font():
    SYSTEM = [
        'Microsoft YaHei', 'SimHei',
        'PingFang SC', 'Heiti SC', 'STHeiti', 'Hiragino Sans GB',
        'Noto Sans CJK SC', 'Noto Sans SC', 'WenQuanYi Micro Hei',
        'WenQuanYi Zen Hei', 'Source Han Sans SC',
    ]
    for name in SYSTEM:
        try:
            from matplotlib.font_manager import fontManager
            if any(f.name == name for f in fontManager.ttflist):
                plt.rcParams['font.sans-serif'] = [name, 'DejaVu Sans']
                plt.rcParams['font.family'] = 'sans-serif'
                return
        except Exception:
            continue
    BUNDLED = ['NotoSansSC-Regular.ttf', 'NotoSansSC-Regular.otf', 'SourceHanSansSC-Regular.otf']
    for fn in BUNDLED:
        fp = os.path.join(_FONT_DIR, fn)
        if os.path.exists(fp):
            try:
                from matplotlib.font_manager import fontManager
                fontManager.addfont(fp)
                for f in fontManager.ttflist:
                    if hasattr(os, 'samefile') and os.path.samefile(f.fname, fp):
                        plt.rcParams['font.sans-serif'] = [f.name, 'DejaVu Sans']
                        plt.rcParams['font.family'] = 'sans-serif'
                        return
                plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
                plt.rcParams['font.family'] = 'sans-serif'
                return
            except Exception:
                continue
    import warnings
    warnings.warn('No Chinese font found.')

_register_chinese_font()
plt.rcParams['axes.unicode_minus'] = False

# ── Data ────────────────────────────────────────────────────────────────────

def load_weight_records():
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
    return records


def load_tracker():
    if not os.path.exists(TRACKER_PATH):
        return {}
    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


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
                'date': row[0].strip(), 'meal': row[1].strip(), 'calories': float(row[2]),
                'protein': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
                'carbs': float(row[4]) if len(row) > 4 and row[4].strip() else 0,
                'fat': float(row[5]) if len(row) > 5 and row[5].strip() else 0,
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
                'calories': float(row[3]) if len(row) > 3 and row[3].strip() else 0,
            })
    return records


# ── Helpers ─────────────────────────────────────────────────────────────────

def rolling_average(pairs, window=7):
    if not pairs:
        return [], []
    # For small datasets, just use a smaller window
    w = window
    # Always produce a point for each day, using all prior data up to w days
    dates, vals = [], []
    for i in range(len(pairs)):
        start_i = max(0, i - w + 1)
        avg = sum(pairs[j][1] for j in range(start_i, i + 1)) / (i - start_i + 1)
        dates.append(pairs[i][0])
        vals.append(round(avg, 2))
    return dates, vals


def _date_ticks(dates_list, max_n=8):
    """Given a sorted list of date objects, return up to max_n tick dates."""
    if not dates_list:
        return []
    n = len(dates_list)
    if n <= max_n:
        return dates_list
    step = max(1, n // max_n)
    ticks = dates_list[::step]
    if ticks[-1] != dates_list[-1]:
        ticks.append(dates_list[-1])
    return ticks


def _plan_x_range(tracker, today):
    phases = tracker.get('phases', [])
    starts, ends = [], []
    for ph in phases:
        try:
            starts.append(date.fromisoformat(ph['start']))
            ends.append(date.fromisoformat(ph['end']))
        except (KeyError, ValueError):
            pass
    if starts and ends:
        return min(starts), max(ends)
    return today - timedelta(days=7), today + timedelta(days=7)


def compute_daily_calories(min_date, max_date, default_meals, tdee):
    nutrition = load_nutrition()
    exercise = load_exercise()

    nut_by_date = defaultdict(lambda: defaultdict(float))
    for r in nutrition:
        nut_by_date[r['date']][r['meal']] += r['calories']

    ex_by_date = defaultdict(float)
    for r in exercise:
        ex_by_date[r['date']] += r['calories']

    daily = []
    d = min_date
    while d <= max_date:
        ds = d.isoformat()
        day_nut = nut_by_date.get(ds, {})
        breakfast = day_nut.get('breakfast', default_meals.get('breakfast', 0))
        lunch     = day_nut.get('lunch',     default_meals.get('lunch', 0))
        dinner    = day_nut.get('dinner',    default_meals.get('dinner', 0))
        snack     = day_nut.get('snack', 0)
        intake    = breakfast + lunch + dinner + snack
        burn      = ex_by_date.get(ds, 0)
        deficit   = float(tdee or 0) + float(burn or 0) - float(intake or 0)
        daily.append({
            'date': d,
            'breakfast': breakfast, 'lunch': lunch,
            'dinner': dinner, 'snack': snack,
            'total_intake': round(intake),
            'exercise_burn': round(burn),
            'tdee': tdee, 'deficit': round(deficit),
        })
        d += timedelta(days=1)
    return daily, len(nutrition) > 0, len(exercise) > 0


# ── Chart drawers ───────────────────────────────────────────────────────────

def draw_weight_recent_28d(ax, weight_records, tracker, today):
    """Row 1: Last 28d weight + bodyfat dual-axis, 7-day MA."""

    x_start = today - timedelta(days=27)
    x_end = today
    ax.set_xlim(x_start, x_end)
    ax.set_xlabel('')

    if not weight_records:
        ax.text(0.5, 0.5, '暂无体重数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('体重 & 体脂率趋势 — 近28天 (7日滑动平均)', fontsize=13, fontweight='bold', color='#2D3436')
        return

    cutoff = today - timedelta(days=27)
    recent = [r for r in weight_records if r['date'] >= cutoff]
    if len(recent) < 3:
        recent = weight_records[-min(7, len(weight_records)):]

    # ── Weight on left Y-axis ──
    w_pairs = [(r['date'], r['weight']) for r in recent]
    win = min(7, max(2, len(recent)))
    dates_ma, w_ma = rolling_average(w_pairs, win)

    dates_raw = [r['date'] for r in recent]
    w_raw = [r['weight'] for r in recent]

    # Build list of all weight-relevant values for Y-range
    all_w = list(w_raw)

    # ── Current phase target line ──
    current_phase = None
    if tracker and tracker.get('phases'):
        for ph in tracker['phases']:
            try:
                ps = date.fromisoformat(ph['start'])
                pe = date.fromisoformat(ph['end'])
            except (KeyError, ValueError):
                continue
            if ps <= today <= pe:
                current_phase = ph
                break

    if current_phase and current_phase.get('target_weight') is not None:
        tw = current_phase['target_weight']
        all_w.append(tw)
        ax.axhline(y=tw, color='#D63031', linewidth=1.5, linestyle='--', alpha=0.7,
                   label=f"当前阶段目标: {tw}kg")
        ax.annotate(f'目标 {tw}kg', xy=(x_start + timedelta(days=2), tw),
                    xytext=(0, 6), textcoords='offset points',
                    fontsize=9, color='#D63031', va='bottom')

    ax.scatter(dates_raw, w_raw, color='#74B9FF', s=12, alpha=0.5, zorder=2, label='体重日测值')

    if w_ma:
        ax.plot(dates_ma, w_ma, color='#0984E3', linewidth=2.5, marker='o', markersize=5,
                label=f'体重 ({win}日均线)', zorder=4)
        ax.fill_between(dates_ma, w_ma, alpha=0.08, color='#0984E3')
        ax.annotate(f'{w_ma[-1]:.1f} kg', xy=(dates_ma[-1], w_ma[-1]),
                    xytext=(-15, -15), textcoords='offset points',
                    fontsize=11, color='#0984E3', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#DDD', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', color='#0984E3', lw=1.2))

    if all_w:
        pad = max((max(all_w) - min(all_w)) * 0.15, 0.5)
        ax.set_ylim(min(all_w) - pad, max(all_w) + pad)

    # ── Body fat on right Y-axis ──
    ax2 = ax.twinx()
    bf_pairs = [(r['date'], r['bodyfat']) for r in recent]
    _, bf_ma = rolling_average(bf_pairs, win)
    bf_dates_raw = [r['date'] for r in recent]
    bf_raw = [r['bodyfat'] for r in recent]
    bf_win = min(7, max(2, len(recent)))

    ax2.scatter(bf_dates_raw, bf_raw, color='#55EFC4', s=12, alpha=0.5, zorder=1, label='体脂率日测值')
    if bf_ma:
        ax2.plot(bf_dates_raw, bf_ma, color='#00B894', linewidth=2.5, marker='s', markersize=5,
                 label=f'体脂率 ({bf_win}日均线)', zorder=3)
        ax2.fill_between(bf_dates_raw, bf_ma, alpha=0.06, color='#00B894')
        ax2.annotate(f'{bf_ma[-1]:.1f}%', xy=(bf_dates_raw[-1], bf_ma[-1]),
                     xytext=(-15, 15), textcoords='offset points',
                     fontsize=11, color='#00B894', fontweight='bold',
                     bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#DDD', alpha=0.9),
                     arrowprops=dict(arrowstyle='->', color='#00B894', lw=1.2))

    ax2.set_ylabel('体脂率 (%)', color='#00B894')
    ax2.tick_params(axis='y', colors='#00B894')
    ax2.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))

    if bf_raw:
        bf_pad = max((max(bf_raw) - min(bf_raw)) * 0.15, 1.0)
        ax2.set_ylim(min(bf_raw) - bf_pad, max(bf_raw) + bf_pad)

    # ── X ticks: fixed 28-day window ──
    tick_dates = _date_ticks([x_start + timedelta(days=i) for i in range(28)], max_n=10)
    ax.set_xticks(tick_dates)
    ax.set_xticklabels([d.strftime('%m-%d') for d in tick_dates], fontsize=8)

    # Today line
    ax.axvline(x=today, color='#B2BEC3', linewidth=1, linestyle=':', alpha=0.6)
    ax.annotate('今天', xy=(mdates.date2num(today), ax.get_ylim()[1]),
                xytext=(4, 4), textcoords='offset points', fontsize=9, color='#636E72', va='bottom')

    # ── Combined legend ──
    lines1, labels1 = ax.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax.legend(lines1 + lines2, labels1 + labels2, loc='upper right', framealpha=0.8, fontsize=9)

    ax.set_title('体重 & 体脂率趋势 — 近28天 (7日滑动平均)', fontsize=13, fontweight='bold', color='#2D3436')
    ax.set_ylabel('体重 (kg)')
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))


def draw_bodyfat_trend(ax, weight_records):
    """Row 3 col 1: Body fat 7-day MA."""
    if not weight_records:
        ax.text(0.5, 0.5, '暂无数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('体脂率趋势 (7日滑动平均)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    bf_pairs = [(r['date'], r['bodyfat']) for r in weight_records]
    win = min(7, max(2, len(weight_records)))
    dates_bf, bf_ma = rolling_average(bf_pairs, win)

    # Raw scatter behind
    dates_raw_bf = [r['date'] for r in weight_records]
    bf_raw = [r['bodyfat'] for r in weight_records]
    ax.scatter(dates_raw_bf, bf_raw, color='#55EFC4', s=12, alpha=0.5, zorder=1, label='日测值')

    if bf_ma:
        ax.plot(dates_bf, bf_ma, color='#00B894', linewidth=2.5, marker='s', markersize=5,
                label=f'体脂率 ({win}日均线)')
        ax.fill_between(dates_bf, bf_ma, alpha=0.08, color='#00B894')
        ax.annotate(f'{bf_ma[-1]:.1f}%', xy=(dates_bf[-1], bf_ma[-1]),
                    xytext=(15, -15), textcoords='offset points',
                    fontsize=11, color='#00B894', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#DDD', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', color='#00B894', lw=1.2))
    # Ticks
    tick_dates = _date_ticks(dates_raw_bf, max_n=8)
    for lbl in ax.get_xticklabels():
        lbl.set_visible(False)
    ax.set_xticks(tick_dates)
    ax.set_xticklabels([d.strftime('%m-%d') for d in tick_dates], fontsize=8)

    # X range
    if len(dates_raw_bf) > 1:
        ax.set_xlim(dates_raw_bf[0] - timedelta(hours=12), dates_raw_bf[-1] + timedelta(hours=12))

    ax.set_title('体脂率趋势 (7日滑动平均)', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('体脂率 (%)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))


def draw_weekly_rate(ax, weight_records):
    """Row 3 col 2: Weekly loss rate."""
    if not weight_records or len(weight_records) < 8:
        ax.text(0.5, 0.5, '数据不足 (需≥8天)', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每周减重速度 (负值=减重)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    w_pairs = [(r['date'], r['weight']) for r in weight_records]
    dates_ma, w_ma = rolling_average(w_pairs, min(7, len(w_pairs)))
    weekly_dates, weekly_vals = [], []
    for i in range(7, len(w_ma)):
        weekly_dates.append(dates_ma[i])
        weekly_vals.append(round(w_ma[i] - w_ma[i - 7], 2))

    if not weekly_dates:
        ax.text(0.5, 0.5, '数据不足 (需≥14天)', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每周减重速度 (负值=减重)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    ax.axhspan(-1.0, -0.5, alpha=0.12, color='#00B894',
               label='安全区间 (0.5-1.0 kg/周)')
    ax.plot(weekly_dates, weekly_vals, color='#6C5CE7', linewidth=2.5, marker='D', markersize=4,
            label='周减重 (kg/周)')
    ax.axhline(y=0, color='gray', linewidth=0.8, linestyle=':')

    ax.set_title('每周减重速度 (负值=减重)', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('速度 (kg/周)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)


def draw_weight_plan_overview(ax, weight_records, tracker, plan_x_range, today):
    """Row 4: Full plan weight raw daily points + phase targets."""
    if not weight_records:
        ax.text(0.5, 0.5, '暂无体重数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('全计划体重走势 (每日原始值)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    dates_raw = [r['date'] for r in weight_records]
    w_raw = [r['weight'] for r in weight_records]
    ax.scatter(dates_raw, w_raw, color='#0984E3', s=18, alpha=0.8,
               label='体重 (日测值)', zorder=3)

    if tracker.get('phases'):
        for ph in tracker['phases']:
            tw = ph.get('target_weight')
            if tw is None:
                continue
            try:
                ps = date.fromisoformat(ph['start'])
                pe = date.fromisoformat(ph['end'])
            except (KeyError, ValueError):
                continue
            ax.plot([ps, pe], [tw, tw], color='#D63031', linestyle='--', linewidth=1.8,
                    label=f"{ph.get('name', '阶段')} → {tw}kg", alpha=0.8)

    ax.axvline(x=today, color='#B2BEC3', linewidth=1, linestyle=':', alpha=0.6)
    ax.annotate('今天', xy=(mdates.date2num(today), ax.get_ylim()[1]),
                xytext=(4, 4), textcoords='offset points', fontsize=9, color='#636E72', va='bottom')

    # Y-range
    all_w = list(w_raw)
    for ph in tracker.get('phases', []):
        tw = ph.get('target_weight')
        if tw is not None:
            all_w.append(tw)
    y_min, y_max = min(all_w), max(all_w)
    pad = max((y_max - y_min) * 0.1, 1.5)
    ax.set_ylim(y_min - pad, y_max + pad)

    ax.set_xlim(plan_x_range)
    ax.set_title('全计划体重走势 (每日原始值)', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('体重 (kg)')
    ax.legend(loc='upper right', framealpha=0.8, fontsize=9, ncol=2)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))


def draw_calorie_intake(ax, calorie_daily, tdee, has_nutrition):
    """Row 2 col 1: Last 14 days stacked bar."""
    if not calorie_daily:
        ax.text(0.5, 0.5, '暂无热量数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每日热量摄入 — 近14天', fontsize=12, fontweight='bold', color='#2D3436')
        return

    dates_cal = [d['date'] for d in calorie_daily]
    idxs = range(len(dates_cal))
    bw = 0.75 if len(dates_cal) <= 14 else 0.85

    bottom = np.zeros(len(dates_cal))
    for meal in MEAL_ORDER:
        vals = [d[meal] for d in calorie_daily]
        ax.bar(idxs, vals, bw, bottom=bottom,
               color=MEAL_COLORS[meal], label=MEAL_LABELS[meal],
               edgecolor='white', linewidth=0.3)
        bottom += np.array(vals)

    # Ticks: every day if ≤14, else sub-sample
    tk_dates = _date_ticks(dates_cal)
    ax.set_xticks([dates_cal.index(d) for d in tk_dates])
    ax.set_xticklabels([d.strftime('%m-%d') for d in tk_dates], fontsize=8)
    ax.set_xlim(-0.5, len(dates_cal) - 0.5)

    ax.axhline(y=tdee, color='#D63031', linewidth=1.5, linestyle='--',
               label=f'TDEE ({tdee} kcal)')
    if not has_nutrition:
        ax.text(0.5, 0.98, '(使用缺省值填充)', transform=ax.transAxes, ha='center',
                fontsize=9, color='#999', va='top')

    ax.set_title('每日热量摄入 — 近14天', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('热量 (kcal)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9, ncol=2)


def draw_calorie_deficit(ax, calorie_daily, goal_deficit):
    """Row 2 col 2: Last 14 days deficit bar."""
    if not calorie_daily:
        ax.text(0.5, 0.5, '暂无热量数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每日热量缺口 — 近14天', fontsize=12, fontweight='bold', color='#2D3436')
        return

    dates_cal = [d['date'] for d in calorie_daily]
    idxs = range(len(dates_cal))
    bw = 0.75 if len(dates_cal) <= 14 else 0.85
    deficits = [d['deficit'] for d in calorie_daily]
    colors = ['#00B894' if v >= 0 else '#D63031' for v in deficits]

    ax.bar(idxs, deficits, bw, color=colors, edgecolor='white', linewidth=0.3)

    tk_dates = _date_ticks(dates_cal)
    ax.set_xticks([dates_cal.index(d) for d in tk_dates])
    ax.set_xticklabels([d.strftime('%m-%d') for d in tk_dates], fontsize=8)
    ax.set_xlim(-0.5, len(dates_cal) - 0.5)

    # Safe deficit range band (300–800 kcal)
    ax.axhspan(300, 800, alpha=0.10, color='#00B894',
               label='安全缺口范围 (300-800 kcal)')

    if goal_deficit:
        ax.axhline(y=goal_deficit, color='#0984E3', linewidth=1.5, linestyle='--',
                   label=f'目标缺口 ({goal_deficit} kcal)')
    ax.axhline(y=0, color='gray', linewidth=0.8)
    ax.set_title('每日热量缺口 — 近14天', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('缺口 (kcal)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)


# ── Figure assembly ─────────────────────────────────────────────────────────

def build_dashboard(weight_records, tracker, calorie_daily, has_nutrition, has_exercise,
                    goal_deficit, plan_x_range, today):
    tdee = tracker.get('tdee', 2200)

    fig = plt.figure(figsize=(16, 18), facecolor='white')
    gs = fig.add_gridspec(3, 2, height_ratios=[1.0, 0.85, 0.9],
                          hspace=0.35, wspace=0.25,
                          left=0.07, right=0.97, top=0.93, bottom=0.04)

    ax1 = fig.add_subplot(gs[0, :])
    draw_weight_recent_28d(ax1, weight_records, tracker, today)

    ax2 = fig.add_subplot(gs[1, 0])
    draw_calorie_intake(ax2, calorie_daily, tdee, has_nutrition)

    ax3 = fig.add_subplot(gs[1, 1])
    draw_calorie_deficit(ax3, calorie_daily, goal_deficit)

    ax6 = fig.add_subplot(gs[2, :])
    draw_weight_plan_overview(ax6, weight_records, tracker, plan_x_range, today)

    # Global styling
    for ax in [ax1, ax2, ax3, ax6]:
        ax.set_facecolor('#FAFAFA')
        ax.grid(True, color='#E0E0E0', linewidth=0.5, alpha=0.7)
        ax.tick_params(labelsize=9)
        for spine in ax.spines.values():
            spine.set_visible(False)

    title_text = f'健身周报 — {today.isoformat()}'
    if tracker.get('phases'):
        parts = [f"{ph.get('name', '')}: {ph['target_weight']}kg"
                 for ph in tracker['phases'] if ph.get('target_weight') is not None]
        if parts:
            title_text += '\n' + ' | '.join(parts)
    fig.suptitle(title_text, fontsize=16, fontweight='bold', color='#2D3436',
                 x=0.07, ha='left', y=0.99)
    return fig


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    weight_records = load_weight_records()
    tracker = load_tracker()
    default_meals = tracker.get('default_meals', {
        'breakfast': 450, 'lunch': 650, 'dinner': 600, 'snack': 200,
    })
    tdee = tracker.get('tdee', 2200)
    goal_deficit = tracker.get('goal_deficit', None)
    today = date.today()

    plan_x_start, plan_x_end = _plan_x_range(tracker, today)
    plan_x_range = (plan_x_start, plan_x_end)

    cal_min = today - timedelta(days=13)
    cal_max = today
    calorie_daily, has_nutrition, has_exercise = compute_daily_calories(
        cal_min, cal_max, default_meals, tdee
    )

    fig = build_dashboard(
        weight_records, tracker, calorie_daily,
        has_nutrition, has_exercise, goal_deficit,
        plan_x_range, today,
    )

    os.makedirs(TEMP_DIR, exist_ok=True)
    png_path = os.path.join(TEMP_DIR, 'dashboard.png')
    fig.savefig(png_path, dpi=150, facecolor='white', edgecolor='none')
    plt.close(fig)

    w_pairs = [(r['date'], r['weight']) for r in weight_records] if weight_records else []
    _, w_ma = rolling_average(w_pairs) if w_pairs else ([], [])
    bf_pairs = [(r['date'], r['bodyfat']) for r in weight_records] if weight_records else []
    _, bf_ma = rolling_average(bf_pairs) if bf_pairs else ([], [])

    summary = {
        'png_path': png_path,
        'temp_dir': TEMP_DIR,
        'records_count': len(weight_records),
        'has_nutrition_data': has_nutrition,
        'has_exercise_data': has_exercise,
        'tdee': tdee,
        'goal_deficit': goal_deficit,
    }
    if weight_records:
        summary['first_date'] = weight_records[0]['date'].isoformat()
        summary['last_date'] = weight_records[-1]['date'].isoformat()
        summary['first_weight'] = weight_records[0]['weight']
        summary['last_weight'] = weight_records[-1]['weight']
        summary['last_weight_ma'] = round(w_ma[-1], 1) if w_ma else None
        summary['last_bodyfat_ma'] = round(bf_ma[-1], 1) if bf_ma else None
        summary['total_change'] = round(weight_records[-1]['weight'] - weight_records[0]['weight'], 1)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
