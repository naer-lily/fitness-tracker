# 用户数据 Schema

## data/profile.md（Markdown，人类可读）

初始化时由 AI 在对话中生成。自由格式，推荐包含以下段落：

```markdown
# 健身档案

## 基本信息
- 称呼：xxx

## 当前状态 (截至 YYYY-MM-DD)
- 体重：xx kg
- 体脂率：xx %
- 肌肉量：xx kg（可选）

## 目标
- 目标体重：xx kg
- 期望达成时间：YYYY-MM-DD 或 "N个月内"

## 约束条件
- 可用时间段：工作日/周末分别描述
- 可用设施：健身房/户外/居家
- 饮食偏好与禁忌
- 健康注意事项

## 历史经验
- 成功经历（什么方法有效，当时的状态）
- 失败/反弹经历（触发因素、过程、教训）
```

`profile.md` 是 AI 的"记忆文件"，每次会话开始时可读取以获取用户背景。

---

## data/tracker.json（JSON，脚本消费）

```json
{
  "created_at": "2026-01-01T00:00:00",
  "last_review": "2026-01-08T00:00:00",
  "last_record": "2026-01-08T00:00:00",
  "phases": [
    {
      "name": "阶段名称",
      "target_weight": 71.0,
      "target_bodyfat": null,
      "start": "2026-05-27",
      "end": "2026-06-30",
      "start_weight": 74.0
    }
  ],
  "milestone_interval_kg": 2.0,
  "review_cadence_days": 7,
  "warning_kg": 1.0,
  "critical_kg": 2.0,
  "last_milestone_weight": 74.0,
  "milestones_hit": [],
  "ree": 2200,
  "default_meals": {
    "breakfast": 450,
    "lunch": 650,
    "dinner": 600,
    "snack": 0
  },
  "goal_deficit": 500
}
```

### 字段说明

| 字段 | 类型 | 说明 |
|------|------|------|
| `created_at` | ISO datetime | skill 初始化时间 |
| `last_review` | ISO datetime | 上次回顾的时间，`review.py` 据此判断是否到期 |
| `last_record` | ISO datetime | 上次记录数据的时间，用于检测停滞 |
| `phases` | array | 分阶段计划，按时间顺序排列 |
| `phases[].target_weight` | number\|null | 该阶段结束时的目标体重 (kg)，可为 null |
| `phases[].target_bodyfat` | number\|null | 该阶段的目标体脂率 (%)，可为 null |
| `phases[].start` | date string | 阶段开始日期 |
| `phases[].end` | date string | 阶段结束日期 |
| `phases[].start_weight` | number | 该阶段起始体重 |
| `milestone_interval_kg` | number | 每减多少 kg 触发一次里程碑庆祝 |
| `review_cadence_days` | number | 两次回顾之间的天数，默认 7 |
| `warning_kg` | number | 黄灯偏差阈值 (kg) |
| `critical_kg` | number | 红灯偏差阈值 (kg) |
| `last_milestone_weight` | number | 上次触发里程碑时的体重 |
| `milestones_hit` | array | 已达成的里程碑历史 |
| `ree` | number | 日均静息消耗 (kcal)，初始化时访谈收集 |
| `default_meals` | object | 三餐缺省热量值，未记餐次自动填充；零食无缺省值，没记就是 0 |
| `goal_deficit` | number | 每日目标热量缺口 (kcal)，默认 500 |

---

## data/records.csv（CSV，时序数据）

```
日期,体重kg,体脂率%,肌肉量kg,去脂体重kg
2026-05-25,74.0,25.0,,
2026-05-26,73.8,24.8,55.5,55.5
```

- **日期**：YYYY-MM-DD
- **体重kg**：必填
- **体脂率%**：必填
- **肌肉量kg**：可选，留空
- **去脂体重kg**：由 `record.py` 或 `plot.py` 自动计算（体重 × (1 - 体脂率/100)），也可预填

`plot.py` 读取此文件时，去脂体重列为空则自动补算。

---

## data/nutrition_log.csv（CSV，饮食记录）

```
日期,餐次,热量kcal,蛋白质g,碳水g,脂肪g,备注
2026-06-01,breakfast,450,20,55,15,
2026-06-01,lunch,650,35,70,20,
2026-06-01,dinner,600,30,60,18,
2026-06-01,snack,200,5,30,8,下午奶茶
2026-06-01,snack,150,3,25,5,坚果
```

- **日期**：YYYY-MM-DD
- **餐次**：`breakfast` / `lunch` / `dinner` / `snack`
- **热量kcal**：必填
- 蛋白质/碳水/脂肪：选填
- 零食可有多条记录（0 条到 N 条）
- 未记录的餐次，计算时用 `tracker.json` 中 `default_meals` 的值填充

---

## data/exercise_log.csv（CSV，运动记录）

```
日期,运动类型,时长分钟,消耗kcal,备注
2026-06-01,跑步,30,280,
2026-06-01,力量训练,45,200,
```

- **日期**：YYYY-MM-DD
- **运动类型**：自由文本
- **时长分钟**：可选
- **消耗kcal**：必填（用户手环/手表数据）
- 一天可有多条记录
