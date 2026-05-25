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
      "end": "2026-06-30"
    }
  ],
  "milestone_interval_kg": 2.0,
  "review_cadence_days": 7,
  "warning_kg": 1.0,
  "critical_kg": 2.0
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
| `milestone_interval_kg` | number | 每减多少 kg 触发一次里程碑庆祝。初始化时根据总目标自动建议 |
| `review_cadence_days` | number | 两次回顾之间的天数，默认 7 |
| `warning_kg` | number | 黄灯偏差阈值 (kg)，超过计划目标此值触发警告 |
| `critical_kg` | number | 红灯偏差阈值 (kg)，超过此值触发严重警告 |

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
