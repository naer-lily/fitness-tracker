# fitness-tracker 2.0

AI 辅助健身减重追踪 Skill — 多轴科学模型，AI-first 设计。

## 核心理念

旧版（v1）是一个**单轴模型**：一切围绕热量缺口，蛋白质是可选字段。

v2 基于 2023-2024 运动营养学研究，重构为**四轴模型**：

1. **蛋白质优先** — 与热量缺口同等的第一公民。科学共识：热量缺口期间 1.6–2.2 g/kg/日维持瘦体重（Helms 2024, Henselmans 2023 meta-analysis, ISSN 立场声明）
2. **避免代谢适应** — 长期大缺口导致 RMR 下降。Poon et al. (2024) 系统综述 & meta-analysis（12 RCT, 881 人）证实间歇饮食休息显著减弱代谢适应
3. **训练日差异化** — 区分高强度训练日 / 轻度活动日 / 休息日，不同日类型有不同蛋白质和热量目标，避免皮质醇升高
4. **周循环模式** — 平日温和缺口 → 周末高强度缺口 → 周日恢复

## 设计原则：基础设施保证反馈

AI 调用任何写操作后，stdout 已经包含当日状态摘要 + 排序好的 alerts。AI 不需要"记得"调用 status.py——**机制保证，不依赖主观能动性**。

## 快速开始

1. 将 Skill 放入 skills 目录
2. 首次使用时 AI 自动启动初始化访谈（检测 `data/profile.md` 不存在）
3. 日常使用：

```
# 记录体重/体脂 → stdout 带趋势 + 里程碑
python scripts/record.py 73.5 24.5

# 记录一餐 → stdout 带当日饮食状态 + 蛋白质缺口 + alerts
python scripts/nutrition.py add lunch 650 --protein 35 --carbs 70 --fat 20

# 记录运动 → stdout 带当日运动+饮食合并状态 + alerts
python scripts/exercise.py add 力量训练 200 --duration 45

# 查看完整状态（按需，非必须）
python scripts/status.py

# 检查蛋白质专项
python scripts/nutrition.py protein-check

# 手动调整日类型
python scripts/exercise.py set-day-type rest
```

## 操作速查

| 命令 | 类型 | 反馈 |
|------|------|------|
| `record.py <kg> <%>` | 写入 | 趋势 + 里程碑 + 波动预警 |
| `nutrition.py add <餐次> <kcal> [--protein g]` | 写入 | 当日饮食状态 + 蛋白质缺口 + alerts |
| `exercise.py add <类型> <kcal> [--duration min]` | 写入 | 运动+饮食合并状态 + 代谢适应预警 |
| `status.py` | 读取 | 完整快照（body/today/week/diet_break/phase） |
| `nutrition.py summary [--days N]` | 读取 | N 日饮食明细 + 蛋白质摘要 |
| `nutrition.py protein-check [--days N]` | 读取 | g/kg 均值 + 连续不足天数 |
| `nutrition.py defaults [--set k=v]` | 配置 | 查看/修改缺省餐次热量 |
| `exercise.py summary [--days N]` | 读取 | N 日运动明细 + 日类型分布 |
| `exercise.py set-day-type <type> [--date]` | 配置 | 覆盖某天的日类型 |
| `review.py` | 读取 | 全维度回顾（体重+蛋白质+代谢风险+饮食休息+日类型合规） |

## 脚本输出结构

所有写操作的 stdout JSON 遵循统一结构：

```json
{
  "ok": true,
  "<action>": { ... },        // 本次写入的数据
  "today_summary": { ... },   // 当日累计状态（nutrition/exercise 有）
  "trend": { ... },           // 趋势（record 有）
  "milestone": null | {...},
  "alerts": [                 // 优先级排序：蛋白质 > 代谢风险 > 其他
    {"priority": 1, "level": "warning", "metric": "protein", "message": "...", "action": "..."}
  ]
}
```

## per-alerts 优先级

| priority | 触发条件 | level |
|----------|---------|-------|
| 1 | 蛋白质差距 > 30g，剩余餐次 ≤ 1 | warning |
| 1 | 蛋白质接近但低于最低目标 | info |
| 2 | 连续 N 天缺口超激进上限 | warning（代谢适应风险） |
| 3 | 当日缺口超 aggressive 阈值 | warning |
| 4 | 缺口超日类型目标但未超 aggressive | info |
| 5 | 超过 3 天未记录体重 | info |

## 新 tracker.json 概览

按关注点模块化组织：

- `user` — 当前体重/体脂/去脂体重
- `energy` — REE（静息消耗）
- `targets` — 目标体重 + 阶段计划
- **`protein`** — 目标 g/kg、最低 g/kg、连续不足预警天数
- **`deficit`** — mild/moderate/aggressive 三级缺口
- **`day_types`** — 三种日类型，各配 deficit_target + protein_g_per_kg
- **`weekly_schedule`** — 周循环模板 + 周五/六额外缺口
- **`diet_breaks`** — 饮食休息周期配置
- `overrides` — 日类型手动覆盖记录
- `milestones` / `review` / `defaults` — 里程碑/回顾/缺省值

## 文件结构

```
fitness-tracker/
├── SKILL.md
├── README.md
├── scripts/
│   ├── common.py              # 共享库（数据加载/日类型/缺口/alerts）
│   ├── record.py              # 体重/体脂记录
│   ├── nutrition.py           # 饮食记录 + 蛋白质检查
│   ├── exercise.py            # 运动记录 + 日类型管理
│   ├── status.py              # 完整状态快照
│   ├── review.py              # 定期回顾
│   ├── export.py              # 数据导出（保留，待增强）
│   └── plot.py                # 仪表盘（保留，不再作为主要输出）
├── references/
│   ├── profile-schema.md
│   └── planning-guide.md
└── data/
    ├── profile.md
    ├── tracker.json
    ├── records.csv
    ├── nutrition_log.csv
    └── exercise_log.csv
```

## 依赖

- Python 3.8+
- 无外部依赖（纯 stdlib）

## License

MIT
