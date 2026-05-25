# fitness-tracker

AI 辅助健身减重追踪 Skill —— 为 [OpenCode](https://github.com/anomalyco/opencode) 设计的技能模块。

## 核心理念

定计划不难，**执行到底**才是难点。此 Skill 偏重后者：

- **对话式初始化** —— 不绑死具体用户/时间/数据，首次使用时 AI 轻量访谈收集信息
- **日常记录** —— 一行命令追加体重/体脂率到 CSV，AI 即时反馈趋势方向
- **定期回顾** —— 每周自动提醒，5 张独立趋势图逐张投递（体重/体脂率/去脂体重/减重速度/原始体重）
- **执行支持** —— 困难应对框架、历史失败模式预警、停滞期策略、计划自适应调整

## 快速开始

1. 将此 Skill 放入 OpenCode 的 skills 目录（用户级或项目级均可）
2. 首次使用时，AI 自动检测缺少 `data/profile.md`，启动初始化访谈
3. 之后每次提到体重数据，AI 调用 `scripts/record.py` 记录
4. 每 7 天 AI 自动提醒回顾，调用 `scripts/plot.py` 生成趋势图

```
# 记录数据
python scripts/record.py 74.0 25.0

# 查看回顾状态
python scripts/review.py

# 生成趋势图（输出 5 张 PNG 到临时目录）
python scripts/plot.py
```

## 文件结构

```
fitness-tracker/
├── SKILL.md                    # Skill 入口（AI 读取的核心指令）
├── README.md
├── .gitignore
├── scripts/
│   ├── record.py               # 记录数据 → data/records.csv
│   ├── plot.py                 # 5 张独立趋势图 → 临时目录
│   └── review.py               # 回顾触发检测 + 偏差评级 + 里程碑
├── references/
│   ├── profile-schema.md       # 数据格式定义（按需加载）
│   └── planning-guide.md       # 分阶段方法论（按需加载）
└── data/                       # 用户数据（不纳入版本控制）
    ├── profile.md
    ├── tracker.json
    └── records.csv
```

## 图表说明

| 图表 | 内容 |
|------|------|
| 体重趋势 | 7 日滑动平均 + 阶段目标水平线 |
| 体脂率趋势 | 7 日滑动平均 |
| 体重 vs 去脂体重 | 双 Y 轴，刻度调整使"线越远离越接近目标" |
| 每周减重速度 | 7 日均差，含 0.5-1.0 kg 安全区间标记 |
| 原始体重 | 线性插值补全缺失日期 + 实测散点 |

## 依赖

- Python 3.8+
- matplotlib（图表生成）

```bash
pip install matplotlib
```

## License

MIT
