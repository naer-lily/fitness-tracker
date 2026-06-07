#!/usr/bin/env python3
"""Generate fitness dashboard PNG with matplotlib.

Charts:
  1. Weight trend (7-day MA + phase target lines)
  2. Body fat trend (7-day MA)
  3. Weekly loss rate (7-day diff, 0.5-1.0 kg safe zone)
  4. Daily calorie intake (stacked bar by meal type)
  5. Daily calorie deficit (bar chart vs goal)

Output: PNG file saved to TEMP/opencode/fitness-tracker/dashboard.png
"""

import os
import sys
import json
import csv
from datetime import date, timedelta
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
    os.environ.get('TEMP', os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')),
    'opencode', 'fitness-tracker'
)

MEAL_LABELS = {'breakfast': '早餐', 'lunch': '午餐', 'dinner': '晚餐', 'snack': '零食'}
MEAL_ORDER = ['breakfast', 'lunch', 'dinner', 'snack']
MEAL_COLORS = {'breakfast': '#FF9F43', 'lunch': '#EE5A24', 'dinner': '#0ABDE3', 'snack': '#10AC84'}

# ---------------------------------------------------------------------------
# Font — cross-platform: system font first, then bundled fallback
# ---------------------------------------------------------------------------

_FONT_DIR = os.path.join(SKILL_ROOT, 'fonts')          # bundled fonts directory

def _register_chinese_font():
    """Find a Chinese-capable font, register it with matplotlib, and set
    rcParams so all text renders Chinese correctly.

    Priority:
      1. System fonts by name (works on most platforms without paths)
      2. Bundled font in SKILL_ROOT/fonts/ (portable fallback)
    """
    # ---- System fonts by font-family name (cross-platform) ----
    SYSTEM_CANDIDATES = [
        # Windows
        'Microsoft YaHei',
        'SimHei',
        # macOS
        'PingFang SC',
        'Heiti SC',
        'STHeiti',
        'Hiragino Sans GB',
        # Linux
        'Noto Sans CJK SC',
        'Noto Sans SC',
        'WenQuanYi Micro Hei',
        'WenQuanYi Zen Hei',
        'Source Han Sans SC',
    ]
    for name in SYSTEM_CANDIDATES:
        try:
            # Check if matplotlib already knows this font
            from matplotlib.font_manager import fontManager
            if any(f.name == name for f in fontManager.ttflist):
                plt.rcParams['font.sans-serif'] = [name, 'DejaVu Sans']
                plt.rcParams['font.family'] = 'sans-serif'
                return
        except Exception:
            continue

    # ---- Bundled font files (relative path, cross-platform) ----
    BUNDLED_FONTS = [
        'NotoSansSC-Regular.ttf',
        'NotoSansSC-Regular.otf',
        'SourceHanSansSC-Regular.otf',
    ]
    for fname in BUNDLED_FONTS:
        fp = os.path.join(_FONT_DIR, fname)
        if os.path.exists(fp):
            try:
                from matplotlib.font_manager import fontManager
                fontManager.addfont(fp)
                # Re-read the registered name from the just-added font
                for f in fontManager.ttflist:
                    if os.path.samefile(f.fname, fp) if hasattr(os.path, 'samefile') else False:
                        plt.rcParams['font.sans-serif'] = [f.name, 'DejaVu Sans']
                        plt.rcParams['font.family'] = 'sans-serif'
                        return
                # Fallback: just set DejaVu Sans (no Chinese)
                plt.rcParams['font.sans-serif'] = ['DejaVu Sans']
                plt.rcParams['font.family'] = 'sans-serif'
                return
            except Exception:
                continue

    # Nothing found — warn but don't crash
    import warnings
    warnings.warn('No Chinese font found. Install one or place a .ttf in fonts/')

_register_chinese_font()
plt.rcParams['axes.unicode_minus'] = False

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

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
                'date': row[0].strip(),
                'meal': row[1].strip(),
                'calories': float(row[2]),
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


# ---------------------------------------------------------------------------
# Computations
# ---------------------------------------------------------------------------

def rolling_average(pairs, window=7):
    if len(pairs) < window:
        window = len(pairs)
    result_dates, result_vals = [], []
    for i in range(window - 1, len(pairs)):
        avg = sum(pairs[j][1] for j in range(i - window + 1, i + 1)) / window
        result_dates.append(pairs[i][0])
        result_vals.append(round(avg, 2))
    return result_dates, result_vals


def compute_daily_calories(weight_records, min_date, max_date, default_meals, tdee):
    nutrition = load_nutrition()
    exercise = load_exercise()

    nut_by_date = defaultdict(lambda: defaultdict(float))
    for r in nutrition:
        nut_by_date[r['date']][r['meal']] += r['calories']

    ex_by_date = defaultdict(float)
    for r in exercise:
        ex_by_date[r['date']] += r['calories']

    has_any_nutrition = len(nutrition) > 0
    has_any_exercise = len(exercise) > 0

    daily = []
    d = min_date
    while d <= max_date:
        ds = d.isoformat()
        day_nut = nut_by_date.get(ds, {})

        breakfast_cal = day_nut.get('breakfast', default_meals.get('breakfast', 0))
        lunch_cal = day_nut.get('lunch', default_meals.get('lunch', 0))
        dinner_cal = day_nut.get('dinner', default_meals.get('dinner', 0))
        snack_cal = day_nut.get('snack', 0)

        total_intake = breakfast_cal + lunch_cal + dinner_cal + snack_cal
        exercise_burn = ex_by_date.get(ds, 0)
        deficit = float(tdee or 0) + float(exercise_burn or 0) - float(total_intake or 0)

        daily.append({
            'date': d,
            'breakfast': breakfast_cal,
            'lunch': lunch_cal,
            'dinner': dinner_cal,
            'snack': snack_cal,
            'total_intake': round(total_intake),
            'exercise_burn': round(exercise_burn),
            'tdee': tdee,
            'deficit': round(deficit),
        })
        d += timedelta(days=1)

    return daily, has_any_nutrition, has_any_exercise


# ---------------------------------------------------------------------------
# Chart drawing
# ---------------------------------------------------------------------------

def draw_weight_trend(ax, weight_records, tracker):
    """Row 1: Weight trend with 7-day MA and phase target lines."""
    if not weight_records:
        ax.text(0.5, 0.5, '暂无体重数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('体重变化趋势 (7日滑动平均)', fontsize=13, fontweight='bold', color='#2D3436')
        return

    w_pairs = [(r['date'], r['weight']) for r in weight_records]
    dates_ma, w_ma = rolling_average(w_pairs)

    ax.plot(dates_ma, w_ma, color='#0984E3', linewidth=2.5, marker='o', markersize=4,
            label='体重 (7日均线)', zorder=3)
    ax.fill_between(dates_ma, w_ma, alpha=0.08, color='#0984E3')

    # Phase target lines
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

    # Annotate last value
    if w_ma:
        last_x = mdates.date2num(dates_ma[-1])
        ax.annotate(f'{w_ma[-1]:.1f} kg', xy=(dates_ma[-1], w_ma[-1]),
                    xytext=(15, -15), textcoords='offset points',
                    fontsize=11, color='#0984E3', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#DDD', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', color='#0984E3', lw=1.2))

    ax.set_title('体重变化趋势 (7日滑动平均)', fontsize=13, fontweight='bold', color='#2D3436')
    ax.set_ylabel('体重 (kg)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))


def draw_bodyfat_trend(ax, weight_records):
    """Row 2 col 1: Body fat trend."""
    if not weight_records:
        ax.text(0.5, 0.5, '暂无数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('体脂率趋势 (7日滑动平均)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    bf_pairs = [(r['date'], r['bodyfat']) for r in weight_records]
    dates_bf, bf_ma = rolling_average(bf_pairs)

    ax.plot(dates_bf, bf_ma, color='#00B894', linewidth=2.5, marker='s', markersize=4,
            label='体脂率 (7日均线)')
    ax.fill_between(dates_bf, bf_ma, alpha=0.08, color='#00B894')

    if bf_ma:
        ax.annotate(f'{bf_ma[-1]:.1f}%', xy=(dates_bf[-1], bf_ma[-1]),
                    xytext=(15, -15), textcoords='offset points',
                    fontsize=11, color='#00B894', fontweight='bold',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='#DDD', alpha=0.9),
                    arrowprops=dict(arrowstyle='->', color='#00B894', lw=1.2))

    ax.set_title('体脂率趋势 (7日滑动平均)', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('体脂率 (%)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)
    ax.yaxis.set_major_formatter(mticker.FormatStrFormatter('%.1f'))


def draw_weekly_rate(ax, weight_records):
    """Row 2 col 2: Weekly loss rate with safe zone."""
    if not weight_records or len(weight_records) < 8:
        ax.text(0.5, 0.5, '数据不足 (需≥8天)', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每周减重速度 (负值=减重)', fontsize=12, fontweight='bold', color='#2D3436')
        return

    w_pairs = [(r['date'], r['weight']) for r in weight_records]
    dates_ma, w_ma = rolling_average(w_pairs)

    weekly_dates, weekly_vals = [], []
    for i in range(7, len(w_ma)):
        weekly_dates.append(dates_ma[i])
        weekly_vals.append(round(w_ma[i] - w_ma[i - 7], 2))

    # Safe zone shading
    if weekly_dates:
        x_min = mdates.date2num(weekly_dates[0])
        x_max = mdates.date2num(weekly_dates[-1])
        ax.axhspan(-1.0, -0.5, xmin=0, xmax=1, alpha=0.12, color='#00B894',
                   label='安全区间 (0.5-1.0 kg/周)')

    ax.plot(weekly_dates, weekly_vals, color='#6C5CE7', linewidth=2.5, marker='D', markersize=4,
            label='周减重 (kg/周)')
    ax.axhline(y=0, color='gray', linewidth=0.8, linestyle=':')

    ax.set_title('每周减重速度 (负值=减重)', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('速度 (kg/周)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)


def draw_calorie_intake(ax, calorie_daily, tdee, has_nutrition):
    """Row 3 col 1: Stacked bar chart of daily calorie intake by meal type."""
    if not calorie_daily:
        ax.text(0.5, 0.5, '暂无热量数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每日热量摄入', fontsize=12, fontweight='bold', color='#2D3436')
        return

    dates_cal = [d['date'] for d in calorie_daily]
    dnums = [mdates.date2num(d) for d in dates_cal]
    bar_width = max(0.6, 0.9 * max(0.5, (dnums[-1] - dnums[0]) / max(1, len(dnums)) if len(dnums) > 1 else 1))

    bottom = np.zeros(len(dates_cal))
    for meal in MEAL_ORDER:
        vals = [d[meal] for d in calorie_daily]
        ax.bar(dates_cal, vals, width=bar_width, bottom=bottom,
               color=MEAL_COLORS[meal], label=MEAL_LABELS[meal],
               edgecolor='white', linewidth=0.3)
        bottom += np.array(vals)

    # TDEE line
    ax.axhline(y=tdee, color='#D63031', linewidth=1.5, linestyle='--',
               label=f'TDEE ({tdee} kcal)')

    if not has_nutrition:
        ax.text(0.5, 0.98, '(使用缺省值填充)', transform=ax.transAxes, ha='center',
                fontsize=9, color='#999', va='top')

    ax.set_title('每日热量摄入', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('热量 (kcal)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9, ncol=2)


def draw_calorie_deficit(ax, calorie_daily, goal_deficit):
    """Row 3 col 2: Daily calorie deficit bar chart."""
    if not calorie_daily:
        ax.text(0.5, 0.5, '暂无热量数据', transform=ax.transAxes, ha='center', va='center',
                fontsize=14, color='gray')
        ax.set_title('每日热量缺口', fontsize=12, fontweight='bold', color='#2D3436')
        return

    dates_cal = [d['date'] for d in calorie_daily]
    deficits = [d['deficit'] for d in calorie_daily]
    colors = ['#00B894' if v >= 0 else '#D63031' for v in deficits]

    bar_width = max(0.6, 0.9 * max(0.5, (mdates.date2num(dates_cal[-1]) - mdates.date2num(dates_cal[0])) / max(1, len(dates_cal)) if len(dates_cal) > 1 else 1))
    ax.bar(dates_cal, deficits, width=bar_width, color=colors,
           edgecolor='white', linewidth=0.3)

    # Goal deficit line
    if goal_deficit:
        ax.axhline(y=goal_deficit, color='#0984E3', linewidth=1.5, linestyle='--',
                   label=f'目标缺口 ({goal_deficit} kcal)')

    ax.axhline(y=0, color='gray', linewidth=0.8)

    ax.set_title('每日热量缺口', fontsize=12, fontweight='bold', color='#2D3436')
    ax.set_ylabel('缺口 (kcal)')
    ax.legend(loc='upper left', framealpha=0.8, fontsize=9)


# ---------------------------------------------------------------------------
# Main figure assembly
# ---------------------------------------------------------------------------

def build_dashboard(weight_records, tracker, calorie_daily, has_nutrition, has_exercise, goal_deficit):
    tdee = tracker.get('tdee', 2200)

    fig = plt.figure(figsize=(16, 18), facecolor='white')
    gs = fig.add_gridspec(3, 2, height_ratios=[1, 1, 1.05], hspace=0.35, wspace=0.25,
                          left=0.07, right=0.97, top=0.93, bottom=0.05)

    # Row 1: Weight trend (full width)
    ax1 = fig.add_subplot(gs[0, :])
    draw_weight_trend(ax1, weight_records, tracker)

    # Row 2: Body fat + Weekly rate
    ax2 = fig.add_subplot(gs[1, 0])
    draw_bodyfat_trend(ax2, weight_records)

    ax3 = fig.add_subplot(gs[1, 1])
    draw_weekly_rate(ax3, weight_records)

    # Row 3: Calorie intake + Deficit
    ax4 = fig.add_subplot(gs[2, 0])
    draw_calorie_intake(ax4, calorie_daily, tdee, has_nutrition)

    ax5 = fig.add_subplot(gs[2, 1])
    draw_calorie_deficit(ax5, calorie_daily, goal_deficit)

    # ---- Global styling ----
    for ax in [ax1, ax2, ax3, ax4, ax5]:
        ax.set_facecolor('#FAFAFA')
        ax.grid(True, color='#E0E0E0', linewidth=0.5, alpha=0.7)
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
        ax.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax.tick_params(labelsize=9)
        for spine in ax.spines.values():
            spine.set_visible(False)

    # Title
    start_date = calorie_daily[0]['date'] if calorie_daily else (weight_records[0]['date'] if weight_records else date.today())
    end_date = calorie_daily[-1]['date'] if calorie_daily else (weight_records[-1]['date'] if weight_records else date.today())

    title_text = f'健身周报 — {start_date.isoformat()} ~ {end_date.isoformat()}'
    if tracker.get('phases'):
        current_phases = [ph for ph in tracker['phases'] if ph.get('target_weight') is not None]
        if current_phases:
            phase_names = ' | '.join(
                f"{ph.get('name', '')}: {ph['target_weight']}kg" for ph in current_phases
            )
            title_text += f'\n{phase_names}'

    fig.suptitle(title_text, fontsize=20, fontweight='bold', color='#2D3436',
                 x=0.07, ha='left', y=0.97)

    return fig


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    weight_records = load_weight_records()
    tracker = load_tracker()
    default_meals = tracker.get('default_meals', {
        'breakfast': 450, 'lunch': 650, 'dinner': 600, 'snack': 200,
    })
    tdee = tracker.get('tdee', 2200)
    goal_deficit = tracker.get('goal_deficit', None)

    # Determine date range
    if weight_records:
        min_date = weight_records[0]['date']
        max_date = weight_records[-1]['date']
    else:
        nutrition = load_nutrition()
        exercise = load_exercise()
        all_d = set()
        for r in nutrition:
            all_d.add(date.fromisoformat(r['date']))
        for r in exercise:
            all_d.add(date.fromisoformat(r['date']))
        if all_d:
            min_date = min(all_d)
            max_date = max(all_d)
        else:
            min_date = date.today() - timedelta(days=6)
            max_date = date.today()

    calorie_daily, has_nutrition, has_exercise = compute_daily_calories(
        weight_records, min_date, max_date, default_meals, tdee
    )

    fig = build_dashboard(
        weight_records, tracker, calorie_daily,
        has_nutrition, has_exercise, goal_deficit,
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
        'total_change': round(weight_records[-1]['weight'] - weight_records[0]['weight'], 1) if weight_records else None,
    }

    if weight_records:
        summary['first_date'] = weight_records[0]['date'].isoformat()
        summary['last_date'] = weight_records[-1]['date'].isoformat()
        summary['first_weight'] = weight_records[0]['weight']
        summary['last_weight'] = weight_records[-1]['weight']
        summary['last_weight_ma'] = round(w_ma[-1], 1) if w_ma else None
        summary['last_bodyfat_ma'] = round(bf_ma[-1], 1) if bf_ma else None

    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
