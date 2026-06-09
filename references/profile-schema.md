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

## 蛋白质目标
- 目标摄入：x.x g/kg/日
- 每日蛋白质：约 xx g
- 偏好来源：xxx

## 能量与饮食
- REE：xxxx kcal
- 缺口偏好：mild / moderate（基于科学建议）
- 缺省三餐：早/午/晚各 xxx kcal
- 饮食原则：xxx
- 饮食休息偏好：每 N 周安排一周维持

## 训练日分布
- 高强度训练日：周x、周x
- 轻度活动日：周x、周x
- 完全休息日：周x

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

完整 schema（v2）：

```json
{
  "_version": 2,

  "user": {
    "name": "xxx",
    "current_weight_kg": 74.0,
    "current_bodyfat_pct": null,
    "lean_body_mass_kg": null
  },

  "energy": {
    "ree": 2000
  },

  "targets": {
    "goal_weight_kg": 55.0,
    "weekly_loss_kg": 0.5,
    "phases": [
      {
        "name": "阶段名",
        "start": "YYYY-MM-DD",
        "end": "YYYY-MM-DD",
        "start_weight_kg": 74.0,
        "target_weight_kg": 71.0,
        "target_bodyfat": null
      }
    ]
  },

  "protein": {
    "target_g_per_kg": 1.8,
    "min_g_per_kg": 1.4,
    "warning_consecutive_days": 3
  },

  "deficit": {
    "mild": 300,
    "moderate": 500,
    "aggressive": 700,
    "max_consecutive_aggressive_days": 3
  },

  "day_types": {
    "training": {
      "deficit_target": "mild",
      "protein_g_per_kg": 2.0,
      "calorie_modifier_kcal": 0
    },
    "light_active": {
      "deficit_target": "moderate",
      "protein_g_per_kg": 1.8,
      "calorie_modifier_kcal": -100
    },
    "rest": {
      "deficit_target": "moderate",
      "protein_g_per_kg": 1.6,
      "calorie_modifier_kcal": -200
    }
  },

  "weekly_schedule": {
    "enabled": true,
    "pattern": {
      "1": "training", "2": "training", "3": "light_active",
      "4": "training", "5": "training", "6": "light_active", "7": "rest"
    },
    "fri_sat_deficit_boost_kcal": 200
  },

  "diet_breaks": {
    "enabled": true,
    "every_weeks": 4,
    "duration_days": 7,
    "last_break_start": null,
    "in_break": false
  },

  "overrides": {},

  "milestones": {
    "interval_kg": 2.0,
    "last_weight_kg": 74.0,
    "hit": []
  },

  "review": {
    "cadence_days": 7,
    "last_review_date": null,
    "last_record_date": null,
    "warning_kg": 1.0,
    "critical_kg": 2.0
  },

  "defaults": {
    "meals": {"breakfast": 450, "lunch": 650, "dinner": 600},
    "snack_calories_if_unrecorded": 0
  }
}
```

### 字段说明

| 顶级模块 | 字段 | 类型 | 说明 |
|---------|------|------|------|
| `user` | `name` | string | 用户称呼 |
| | `current_weight_kg` | number\|null | 最新体重（kg），record.py 自动更新 |
| | `current_bodyfat_pct` | number\|null | 最新体脂率（%），record.py 自动更新 |
| | `lean_body_mass_kg` | number\|null | 去脂体重（kg），自动计算 |
| `energy` | `ree` | number | 日均静息消耗（kcal） |
| `targets` | `goal_weight_kg` | number\|null | 最终目标体重 |
| | `weekly_loss_kg` | number | 目标周减重速度 |
| | `phases` | array | 分阶段计划 |
| `protein` | `target_g_per_kg` | number | 目标蛋白质（g/kg/日），默认 1.8 |
| | `min_g_per_kg` | number | 最低蛋白质下限，默认 1.4 |
| | `warning_consecutive_days` | int | 连续低于下限天数触发预警 |
| `deficit` | `mild` | number | 温和缺口（kcal），默认 300 |
| | `moderate` | number | 中等缺口（kcal），默认 500 |
| | `aggressive` | number | 激进缺口上限（kcal），默认 700 |
| | `max_consecutive_aggressive_days` | int | 连续激进天数触发警告 |
| `day_types` | `training` / `light_active` / `rest` | object | 每种日类型配置 |
| ↓ 每个日类型 | `deficit_target` | string | 引用 deficit 等级（"mild"/"moderate"/"aggressive"） |
| | `protein_g_per_kg` | number | 该日类型蛋白质目标 |
| | `calorie_modifier_kcal` | number | 相对基础摄入的热量调整 |
| `weekly_schedule` | `enabled` | bool | 是否启用周循环 |
| | `pattern` | object | ISO weekday → day_type 映射 |
| | `fri_sat_deficit_boost_kcal` | number | 周五/六额外缺口 |
| `diet_breaks` | `enabled` | bool | 是否启用饮食休息 |
| | `every_weeks` | int | 间隔周数 |
| | `duration_days` | int | 每次持续天数 |
| | `in_break` | bool | 当前是否处于休息期 |
| `overrides` | — | object | `{ "YYYY-MM-DD": "day_type" }` 手动覆盖 |
| `milestones` | `interval_kg` | number | 里程碑间隔 |
| | `last_weight_kg` | number | 上次触发时的体重 |
| | `hit` | array | 已达成里程碑历史 |
| `review` | `cadence_days` | number | 回顾间隔天数 |
| | `last_review_date` | string\|null | 上次回顾日期 |
| | `last_record_date` | string\|null | 上次记录日期 |
| | `warning_kg` | number | 黄灯偏差阈值 |
| | `critical_kg` | number | 红灯偏差阈值 |
| `defaults` | `meals` | object | 三餐缺省热量 |
| | `snack_calories_if_unrecorded` | number | 零食默认值（>0 才记账，0 就是不记） |

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
- **肌肉量kg**：可选
- **去脂体重kg**：由 record.py 自动计算（体重 × (1 - 体脂率/100)）

---

## data/nutrition_log.csv（CSV，饮食记录）

```
日期,餐次,热量kcal,蛋白质g,碳水g,脂肪g,备注
2026-06-01,breakfast,450,20,55,15,
2026-06-01,lunch,650,35,70,20,
2026-06-01,dinner,600,30,60,18,
2026-06-01,snack,200,5,30,8,下午奶茶
```

- **蛋白质g**：强烈推荐填写。蛋白质是第一公民，不只是可选字段
- 零食可有多条记录（0 到 N 条），未记的零食默认 0 kcal
- 三餐未记录的，计算时用 tracker.json 的 defaults.meals 填充

---

## data/exercise_log.csv（CSV，运动记录）

```
日期,运动类型,时长分钟,消耗kcal,备注
2026-06-01,跑步,30,280,
2026-06-01,力量训练,45,200,
```

- **运动类型**：自由文本
- **时长分钟**：可选
- **消耗kcal**：必填（用户手环/手表数据）
- 一天可有多条记录
