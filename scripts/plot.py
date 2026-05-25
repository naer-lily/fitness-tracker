#!/usr/bin/env python3
"""Generate 5 standalone fitness trend charts from records.csv and tracker.json.

Each chart is saved as a separate PNG to a temporary directory.
Outputs a JSON array of file paths to stdout for the AI to consume.

Charts:
  1. trend_weight.png        - 体重趋势 (7日滑动平均 + 阶段目标线)
  2. trend_bodyfat.png       - 体脂率趋势 (7日滑动平均)
  3. trend_weight_lbm.png    - 体重 vs 去脂体重 (双Y轴，调整刻度)
  4. trend_weekly_loss.png   - 每周减重速度 (7日均差，0.5-1.0kg 安全区)
  5. trend_raw_weight.png    - 原始体重 (线性插值补全缺失日期)
"""

import os
import sys
import json
import csv
from datetime import date, timedelta

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SKILL_ROOT = os.path.dirname(SCRIPT_DIR)
DATA_DIR = os.path.join(SKILL_ROOT, 'data')
RECORDS_PATH = os.path.join(DATA_DIR, 'records.csv')
TRACKER_PATH = os.path.join(DATA_DIR, 'tracker.json')

TEMP_DIR = os.path.join(
    os.environ.get('TEMP', os.path.join(os.path.expanduser('~'), 'AppData', 'Local', 'Temp')),
    'opencode', 'fitness-tracker'
)

plt.rcParams['font.sans-serif'] = ['SimHei', 'Microsoft YaHei', 'WenQuanYi Micro Hei', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False
plt.rcParams['font.size'] = 14
plt.rcParams['axes.titlesize'] = 18
plt.rcParams['axes.labelsize'] = 15
plt.rcParams['xtick.labelsize'] = 12
plt.rcParams['ytick.labelsize'] = 12
plt.rcParams['legend.fontsize'] = 12
plt.rcParams['figure.titlesize'] = 20


def load_records():
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
        return None
    with open(TRACKER_PATH, 'r', encoding='utf-8') as f:
        return json.load(f)


def rolling_average(values, window=7):
    if len(values) < window:
        window = len(values)
    result_dates = []
    result_vals = []
    for i in range(window - 1, len(values)):
        avg = sum(values[j][1] for j in range(i - window + 1, i + 1)) / window
        result_dates.append(values[i][0])
        result_vals.append(avg)
    return result_dates, result_vals


def interpolate_missing(records):
    if len(records) < 2:
        return [r['date'] for r in records], [r['weight'] for r in records]

    date_to_w = {r['date']: r['weight'] for r in records}
    all_dates = []
    d = records[0]['date']
    end = records[-1]['date']
    while d <= end:
        all_dates.append(d)
        d += timedelta(days=1)

    values = []
    for d in all_dates:
        if d in date_to_w:
            values.append(date_to_w[d])
        else:
            left_v = right_v = None
            for offset in range(1, 60):
                ld = d - timedelta(days=offset)
                rd = d + timedelta(days=offset)
                if left_v is None and ld in date_to_w:
                    left_v = (ld, date_to_w[ld])
                if right_v is None and rd in date_to_w:
                    right_v = (rd, date_to_w[rd])
                if left_v is not None and right_v is not None:
                    break
            if left_v and right_v:
                span = (right_v[0] - left_v[0]).days
                frac = (d - left_v[0]).days / span
                values.append(left_v[1] + frac * (right_v[1] - left_v[1]))
            elif left_v:
                values.append(left_v[1])
            elif right_v:
                values.append(right_v[1])
            else:
                values.append(None)

    return all_dates, values


def save_fig(fig, filename):
    path = os.path.join(TEMP_DIR, filename)
    fig.savefig(path, dpi=150, bbox_inches='tight', facecolor='white')
    plt.close(fig)
    return path


def apply_date_fmt(ax):
    ax.xaxis.set_major_formatter(mdates.DateFormatter('%m-%d'))
    ax.grid(True, alpha=0.3)


def chart_weight(records, tracker):
    """Chart 1: 体重趋势 (7日滑动平均 + 阶段目标线)"""
    fig, ax = plt.subplots(figsize=(12, 6))
    w_pairs = [(r['date'], r['weight']) for r in records]
    dates_ma, w_ma = rolling_average(w_pairs)
    ax.plot(dates_ma, w_ma, 'b-', linewidth=2.5, label='体重 (7日滑动平均)', zorder=2)

    if tracker and tracker.get('phases'):
        for ph in tracker['phases']:
            tw = ph.get('target_weight')
            if tw is None:
                continue
            try:
                ps = date.fromisoformat(ph['start'])
                pe = date.fromisoformat(ph['end'])
            except (KeyError, ValueError):
                continue
            ps_num = float(mdates.date2num(ps))
            pe_num = float(mdates.date2num(pe))
            ax.hlines(tw, ps_num, pe_num, colors='crimson', linestyles='--',
                      linewidth=2, alpha=0.6, zorder=1)
            ax.text(ps_num, tw + 0.15, f" {ph.get('name', '')} → {tw} kg",
                    fontsize=11, va='bottom', color='crimson', alpha=0.85)

    if w_ma:
        ax.annotate(f'{w_ma[-1]:.1f} kg', xy=(dates_ma[-1], w_ma[-1]),
                    xytext=(15, 15), textcoords='offset points',
                    fontsize=13, fontweight='bold', color='b',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('体重变化趋势 (7日滑动平均)', fontweight='bold')
    ax.set_ylabel('体重 (kg)')
    apply_date_fmt(ax)
    return save_fig(fig, 'trend_weight.png')


def chart_bodyfat(records):
    """Chart 2: 体脂率趋势 (7日滑动平均)"""
    fig, ax = plt.subplots(figsize=(12, 6))
    bf_pairs = [(r['date'], r['bodyfat']) for r in records]
    dates_ma, bf_ma = rolling_average(bf_pairs)
    ax.plot(dates_ma, bf_ma, 'g-', linewidth=2.5, label='体脂率 (7日滑动平均)')

    if bf_ma:
        ax.annotate(f'{bf_ma[-1]:.1f}%', xy=(dates_ma[-1], bf_ma[-1]),
                    xytext=(15, 15), textcoords='offset points',
                    fontsize=13, fontweight='bold', color='g',
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))

    ax.set_title('体脂率变化趋势 (7日滑动平均)', fontweight='bold')
    ax.set_ylabel('体脂率 (%)')
    apply_date_fmt(ax)
    return save_fig(fig, 'trend_bodyfat.png')


def chart_weight_lbm(records):
    """Chart 3: 体重 vs 去脂体重 (双Y轴，距离越远越接近)"""
    fig, ax1 = plt.subplots(figsize=(12, 6))

    w_pairs = [(r['date'], r['weight']) for r in records]
    lbm_pairs = [(r['date'], r['lbm']) for r in records]
    dates_w, w_ma = rolling_average(w_pairs)
    dates_lbm, lbm_ma = rolling_average(lbm_pairs)

    ax1.plot(dates_w, w_ma, 'b-', linewidth=2.5, label='体重')
    ax1.set_ylabel('体重 (kg)', color='b')
    ax1.tick_params(axis='y', labelcolor='b')

    ax2 = ax1.twinx()
    ax2.plot(dates_lbm, lbm_ma, 'g-', linewidth=2.5, label='去脂体重')
    ax2.set_ylabel('去脂体重 (kg)', color='g')
    ax2.tick_params(axis='y', labelcolor='g')

    if w_ma and lbm_ma:
        min_w, max_w = min(w_ma), max(w_ma)
        max_lbm = max(lbm_ma)
        span = (max_w + 0.5) - (min_w - 0.5)
        ax1.set_ylim(min_w - 0.5, max_w + 0.5)
        ax2.set_ylim(max_lbm + 0.5 - span, max_lbm + 0.5)

    ax1.set_title('体重 & 去脂体重趋势 (距离越远越接近)', fontweight='bold')
    h1, l1 = ax1.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax1.legend(h1 + h2, l1 + l2, fontsize=12, loc='upper right')
    apply_date_fmt(ax1)
    return save_fig(fig, 'trend_weight_lbm.png')


def chart_weekly_loss(records):
    """Chart 4: 每周减重速度 (7日均差，安全区 0.5-1.0 kg)"""
    fig, ax = plt.subplots(figsize=(12, 6))

    w_pairs = [(r['date'], r['weight']) for r in records]
    dates_ma, w_ma = rolling_average(w_pairs)

    if len(w_ma) >= 8:
        weekly_dates, weekly_vals = [], []
        for i in range(7, len(w_ma)):
            loss = w_ma[i] - w_ma[i - 7]
            weekly_dates.append(dates_ma[i])
            weekly_vals.append(loss)

        ax.plot(weekly_dates, weekly_vals, 'b-', linewidth=2.5, label='周均减重 (负=减)')
        ax.axhline(y=0, color='gray', linewidth=1)
        ax.axhspan(-1.0, -0.5, alpha=0.12, color='green', label='安全区间 (0.5-1.0 kg/周)')

        if weekly_vals:
            ax.annotate(f'{weekly_vals[-1]:+.2f} kg/周',
                        xy=(weekly_dates[-1], weekly_vals[-1]),
                        xytext=(15, 15), textcoords='offset points',
                        fontsize=13, fontweight='bold', color='b',
                        bbox=dict(boxstyle='round,pad=0.3', facecolor='white', alpha=0.8))
    else:
        ax.text(0.5, 0.5, '数据不足 (需≥8天)', transform=ax.transAxes,
                ha='center', va='center', fontsize=16, color='gray')

    ax.set_title('每周减重速度 (负值=减重，7日均差)', fontweight='bold')
    ax.set_ylabel('速度 (kg/周)')
    apply_date_fmt(ax)
    return save_fig(fig, 'trend_weekly_loss.png')


def chart_raw_weight(records):
    """Chart 5: 原始体重 (含线性插值补全缺失日期)"""
    fig, ax = plt.subplots(figsize=(12, 6))

    interp_dates, interp_vals = interpolate_missing(records)
    valid = [(d, v) for d, v in zip(interp_dates, interp_vals) if v is not None]
    if valid:
        ax.plot([x[0] for x in valid], [x[1] for x in valid],
                'b-', linewidth=1.5, alpha=0.4, label='线性插值')

    raw_dates = [r['date'] for r in records]
    raw_w = [r['weight'] for r in records]
    ax.scatter(raw_dates, raw_w, c='red', s=40, zorder=5, label='实测值')

    ax.set_title('原始体重 (含线性插值补全缺失日期)', fontweight='bold')
    ax.set_ylabel('体重 (kg)')
    apply_date_fmt(ax)
    return save_fig(fig, 'trend_raw_weight.png')


def main():
    records = load_records()
    if not records:
        print(json.dumps({'error': 'No data in records.csv'}))
        sys.exit(1)

    tracker = load_tracker()
    os.makedirs(TEMP_DIR, exist_ok=True)

    files = [
        chart_weight(records, tracker),
        chart_bodyfat(records),
        chart_weight_lbm(records),
        chart_weekly_loss(records),
        chart_raw_weight(records),
    ]

    summary = {
        'files': files,
        'temp_dir': TEMP_DIR,
        'records_count': len(records),
        'first_date': records[0]['date'].isoformat(),
        'last_date': records[-1]['date'].isoformat(),
        'first_weight': records[0]['weight'],
        'last_weight': records[-1]['weight'],
        'total_change': round(records[-1]['weight'] - records[0]['weight'], 1),
    }
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
