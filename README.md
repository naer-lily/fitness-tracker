# fitness-tracker

AI 辅助健身减重追踪 Skill —— 为 [OpenCode](https://github.com/anomalyco/opencode) 设计的技能模块。

## 核心理念

定计划不难，**执行到底**才是难点。此 Skill 偏重后者：

- **对话式初始化** —— 不绑死具体用户/时间/数据，首次使用时 AI 轻量访谈收集信息
- **日常记录** —— 一行命令追加体重/体脂率到 CSV，AI 即时反馈趋势方向
- **定期回顾** —— 每周自动提醒，通过 `export.py` 导出 5 张结构化 CSV，AI 自行解读趋势
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

# 生成趋势图（已保留，不再作为主要输出）
python scripts/plot.py

# 导出结构化数据（推荐——5 个 CSV 供 AI 解读或自行绘图）
python scripts/export.py
```

## 文件结构

```
fitness-tracker/
├── SKILL.md                    # Skill 入口（AI 读取的核心指令）
├── README.md
├── .gitignore
├── scripts/
│   ├── record.py               # 记录数据 → data/records.csv
│   ├── nutrition.py             # 饮食记录 → data/nutrition_log.csv
│   ├── exercise.py              # 运动记录 → data/exercise_log.csv
│   ├── plot.py                  # 仪表盘 PNG（已保留，不再作为主要输出）
│   ├── export.py                # 导出 5 张结构化 CSV（饮食/运动明细、每日汇总、身体数据、阶段信息）
│   └── review.py                # 回顾触发检测 + 偏差评级 + 里程碑
├── references/
│   ├── profile-schema.md       # 数据格式定义（按需加载）
│   └── planning-guide.md       # 分阶段方法论（按需加载）
└── data/                       # 用户数据（不纳入版本控制）
    ├── profile.md
    ├── tracker.json
    ├── records.csv
    ├── nutrition_log.csv
    └── exercise_log.csv
```

## 数据导出

`scripts/export.py` 输出 5 个结构化 CSV 文件（全中文列名）：

| CSV | 内容 |
|------|------|
| 饮食明细 | 每餐原文备注 + 热量/蛋白/碳水/脂肪 |
| 运动明细 | 每次运动类型/时长/消耗 + 备注 |
| 每日汇总 | 近 14 天 — 早/午/晚/零食、运动消耗、纯缺口、脂肪校正缺口 |
| 身体数据 | 全量 — 体重/体脂率/去脂体重/脂肪量/瘦体重/7日均线 |
| 阶段信息 | 所有阶段的起止/目标/天数，自动计算日均所需缺口 |

## 依赖

- Python 3.8+

无额外依赖（纯 stdlib：csv, json, datetime）。原 `plot.py` 需要 matplotlib，但已不作为主要输出。

## License

MIT
