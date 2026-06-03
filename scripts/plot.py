#!/usr/bin/env python3
"""Generate interactive fitness dashboard HTML with Plotly.

Charts:
  1. Weight trend (7-day MA + phase target lines)
  2. Body fat trend (7-day MA)
  3. Weekly loss rate (7-day diff, 0.5-1.0 kg safe zone)
  4. Daily calorie intake (stacked bar by meal type)
  5. Daily calorie deficit (bar chart vs goal)

Output: single HTML file saved to TEMP/opencode/fitness-tracker/dashboard.html
"""

import os
import sys
import json
import csv
from datetime import date, timedelta
from collections import defaultdict

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
    """Build day-level calorie data across the full date span."""
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
        deficit = float(tdee or 0) + float(exercise_burn or 0) - float(total_intake or 0)  # type: ignore[operator]

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
# Plotly chart builders
# ---------------------------------------------------------------------------

def make_dashboard(weight_records, tracker, calorie_daily, has_nutrition, has_exercise, goal_deficit):
    from plotly.subplots import make_subplots
    import plotly.graph_objects as go

    has_weight = len(weight_records) > 0
    tdee = tracker.get('tdee', 2200)

    fig = make_subplots(
        rows=3, cols=2,
        specs=[
            [{"colspan": 2}, None],
            [{}, {}],
            [{}, {}],
        ],
        subplot_titles=(
            '体重变化趋势 (7日滑动平均)',
            '体脂率趋势 (7日滑动平均)',
            '每周减重速度 (负值=减重)',
            '🔥 每日热量摄入',
            '📉 每日热量缺口',
        ),
        vertical_spacing=0.13,
        horizontal_spacing=0.10,
    )

    # ---- Row 1, Col 1: Weight trend ----
    if has_weight:
        w_pairs = [(r['date'], r['weight']) for r in weight_records]
        dates_ma, w_ma = rolling_average(w_pairs)
        fig.add_trace(
            go.Scatter(
                x=dates_ma, y=w_ma, mode='lines+markers',
                line=dict(color='#0984E3', width=3),
                marker=dict(size=5),
                name='体重 (7日均线)',
                hovertemplate='%{x|%m-%d}<br>体重: %{y:.1f} kg<extra></extra>',
            ),
            row=1, col=1,
        )

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
                fig.add_trace(
                    go.Scatter(
                        x=[ps, pe], y=[tw, tw],
                        mode='lines',
                        line=dict(color='#D63031', dash='dash', width=2),
                        name=f"{ph.get('name', '阶段')} → {tw}kg",
                        hovertemplate='阶段目标: %{y:.1f} kg<extra></extra>',
                    ),
                    row=1, col=1,
                )

        if w_ma:
            fig.add_annotation(
                x=dates_ma[-1], y=w_ma[-1],
                text=f'{w_ma[-1]:.1f} kg',
                showarrow=True, arrowhead=1, ax=30, ay=-20,
                font=dict(size=13, color='#0984E3'),
                bgcolor='rgba(255,255,255,0.8)',
                row=1, col=1,
            )
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref='x domain', yref='y domain',
            text='暂无体重数据', showarrow=False,
            font=dict(size=16, color='gray'),
            row=1, col=1,
        )

    # ---- Row 2, Col 1: Body fat trend ----
    if has_weight:
        bf_pairs = [(r['date'], r['bodyfat']) for r in weight_records]
        dates_bf, bf_ma = rolling_average(bf_pairs)
        fig.add_trace(
            go.Scatter(
                x=dates_bf, y=bf_ma, mode='lines+markers',
                line=dict(color='#00B894', width=3),
                marker=dict(size=5),
                name='体脂率 (7日均线)',
                hovertemplate='%{x|%m-%d}<br>体脂: %{y:.1f}%<extra></extra>',
            ),
            row=2, col=1,
        )
        if bf_ma:
            fig.add_annotation(
                x=dates_bf[-1], y=bf_ma[-1],
                text=f'{bf_ma[-1]:.1f}%',
                showarrow=True, arrowhead=1, ax=30, ay=-20,
                font=dict(size=13, color='#00B894'),
                bgcolor='rgba(255,255,255,0.8)',
                row=2, col=1,
            )
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref='x domain', yref='y domain',
            text='暂无体重数据', showarrow=False,
            font=dict(size=16, color='gray'),
            row=2, col=1,
        )

    # ---- Row 2, Col 2: Weekly loss rate ----
    if has_weight and len(weight_records) >= 8:
        w_pairs = [(r['date'], r['weight']) for r in weight_records]
        dates_ma, w_ma = rolling_average(w_pairs)

        weekly_dates, weekly_vals = [], []
        for i in range(7, len(w_ma)):
            weekly_dates.append(dates_ma[i])
            weekly_vals.append(round(w_ma[i] - w_ma[i - 7], 2))

        fig.add_trace(
            go.Scatter(
                x=weekly_dates, y=weekly_vals, mode='lines+markers',
                line=dict(color='#6C5CE7', width=3),
                marker=dict(size=5),
                name='周减重 (kg/周)',
                hovertemplate='%{x|%m-%d}<br>周减重: %{y:+.2f} kg<extra></extra>',
            ),
            row=2, col=2,
        )

        fig.add_hrect(
            y0=-1.0, y1=-0.5, line_width=0,
            fillcolor='rgba(0, 184, 148, 0.15)',
            name='安全区间 (0.5-1.0 kg/周)',
            row=2, col=2,
        )
        fig.add_hline(y=0, line=dict(color='gray', width=1, dash='dot'), row=2, col=2)
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref='x domain', yref='y domain',
            text='数据不足 (需≥8天)', showarrow=False,
            font=dict(size=16, color='gray'),
            row=2, col=2,
        )

    # ---- Row 3, Col 1: Daily calorie intake ----
    if calorie_daily:
        dates_cal = [d['date'] for d in calorie_daily]
        for meal in MEAL_ORDER:
            vals = [d[meal] for d in calorie_daily]
            fig.add_trace(
                go.Bar(
                    x=dates_cal, y=vals,
                    name=MEAL_LABELS[meal],
                    marker_color=MEAL_COLORS[meal],
                    hovertemplate='%{x|%m-%d}<br>' + MEAL_LABELS[meal] + ': %{y:.0f} kcal<extra></extra>',
                ),
                row=3, col=1,
            )

        fig.add_trace(
            go.Scatter(
                x=[dates_cal[0], dates_cal[-1]], y=[tdee, tdee],
                mode='lines',
                line=dict(color='#D63031', width=2, dash='dash'),
                name=f'TDEE ({tdee} kcal)',
                hovertemplate='TDEE: %{y:.0f} kcal<extra></extra>',
            ),
            row=3, col=1,
        )

        if not has_nutrition:
            fig.add_annotation(
                x=0.5, y=0.95, xref='x domain', yref='y domain',
                text='(使用缺省值填充)', showarrow=False,
                font=dict(size=11, color='#999'),
                row=3, col=1,
            )
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref='x domain', yref='y domain',
            text='暂无热量数据', showarrow=False,
            font=dict(size=16, color='gray'),
            row=3, col=1,
        )

    # ---- Row 3, Col 2: Daily calorie deficit ----
    if calorie_daily:
        dates_cal = [d['date'] for d in calorie_daily]
        deficits = [d['deficit'] for d in calorie_daily]

        colors = ['#00B894' if v >= 0 else '#D63031' for v in deficits]

        fig.add_trace(
            go.Bar(
                x=dates_cal, y=deficits,
                marker_color=colors,
                name='热量缺口',
                hovertemplate='%{x|%m-%d}<br>缺口: %{y:+.0f} kcal<extra></extra>',
            ),
            row=3, col=2,
        )

        if goal_deficit:
            fig.add_trace(
                go.Scatter(
                    x=[dates_cal[0], dates_cal[-1]], y=[goal_deficit, goal_deficit],
                    mode='lines',
                    line=dict(color='#0984E3', width=2, dash='dash'),
                    name=f'目标缺口 ({goal_deficit} kcal)',
                    hovertemplate='目标: %{y:.0f} kcal<extra></extra>',
                ),
                row=3, col=2,
            )

        fig.add_hline(y=0, line=dict(color='gray', width=1), row=3, col=2)
    else:
        fig.add_annotation(
            x=0.5, y=0.5, xref='x domain', yref='y domain',
            text='暂无热量数据', showarrow=False,
            font=dict(size=16, color='gray'),
            row=3, col=2,
        )

    return fig


# ---------------------------------------------------------------------------
# Layout & output
# ---------------------------------------------------------------------------

def apply_layout(fig, start_date, end_date, tracker):
    title_text = f'📊 健身周报 — {start_date} ~ {end_date}'
    if tracker.get('phases'):
        current_phases = [
            ph for ph in tracker['phases']
            if ph.get('target_weight') is not None
        ]
        if current_phases:
            phase_names = ' | '.join(
                f"{ph.get('name', '')}: {ph['target_weight']}kg"
                for ph in current_phases
            )
            title_text += f'<br><sub style="font-size:13px">{phase_names}</sub>'

    fig.update_layout(
        title=dict(text=title_text, x=0.05, font=dict(size=22, color='#2D3436')),
        font=dict(family='Microsoft YaHei, SimHei, sans-serif', size=12, color='#2D3436'),
        template='plotly_white',
        hovermode='x unified',
        showlegend=True,
        legend=dict(
            orientation='h', yanchor='bottom', y=1.02, xanchor='center', x=0.5,
            font=dict(size=11),
        ),
        barmode='stack',
        height=1400,
        margin=dict(l=60, r=30, t=120, b=50),
        paper_bgcolor='white',
        plot_bgcolor='#FAFAFA',
    )

    for i in range(1, 4):
        for j in range(1, 3):
            if i == 1 and j == 2:
                continue
            fig.update_xaxes(
                row=i, col=j,
                tickformat='%m-%d',
                dtick='M1' if i <= 2 else None,
                ticklabelmode='period',
                gridcolor='#E0E0E0',
                zeroline=False,
            )
            fig.update_yaxes(
                row=i, col=j,
                gridcolor='#E0E0E0',
                zeroline=False,
            )

    fig.update_yaxes(title_text='体重 (kg)', row=1, col=1)
    fig.update_yaxes(title_text='体脂率 (%)', row=2, col=1)
    fig.update_yaxes(title_text='速度 (kg/周)', row=2, col=2)
    fig.update_yaxes(title_text='热量 (kcal)', row=3, col=1)
    fig.update_yaxes(title_text='缺口 (kcal)', row=3, col=2)


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
        # Try nutrition or exercise dates
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
            # Nothing at all
            min_date = date.today() - timedelta(days=6)
            max_date = date.today()

    calorie_daily, has_nutrition, has_exercise = compute_daily_calories(
        weight_records, min_date, max_date, default_meals, tdee
    )

    fig = make_dashboard(
        weight_records, tracker, calorie_daily,
        has_nutrition, has_exercise, goal_deficit,
    )
    apply_layout(fig, min_date.isoformat(), max_date.isoformat(), tracker)

    os.makedirs(TEMP_DIR, exist_ok=True)
    html_path = os.path.join(TEMP_DIR, 'dashboard.html')
    fig.write_html(html_path, include_plotlyjs='cdn', config={
        'displayModeBar': True,
        'displaylogo': False,
        'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
        'toImageButtonOptions': {'format': 'png', 'filename': 'fitness_dashboard'},
    })

    png_path = os.path.join(TEMP_DIR, 'dashboard.png')
    fig.write_image(png_path, width=1600, height=1400, scale=1.5)


    w_pairs = [(r['date'], r['weight']) for r in weight_records] if weight_records else []
    _, w_ma = rolling_average(w_pairs) if w_pairs else ([], [])
    bf_pairs = [(r['date'], r['bodyfat']) for r in weight_records] if weight_records else []
    _, bf_ma = rolling_average(bf_pairs) if bf_pairs else ([], [])

    summary = {
        'html_path': html_path,
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
