---
name: fitness-tracker
description: 个人健身减重追踪系统。记录体重/体脂率/肌肉量，绘制7日滑动平均趋势图，追踪分阶段目标进度并提供执行支持。当用户提及体重、减肥、健身、体脂率、饮食运动话题，或要求记录/查看体重数据时使用。
agent_created: true
---

# 健身减重追踪器

## 0. 初始化（首次使用）

当 `data/profile.md` 不存在时，执行轻量访谈。逐项收集以下信息后写入文件：

1. **称呼**：怎么称呼你？
2. **当前数据**：当前体重？体脂率、肌肉量（可选）
3. **目标与时间**：目标体重？期望何时达成？
4. **能量**：知道自己的日均静息消耗（REE）吗？（不知道的话，可根据基础代谢 + 活动系数估算）
5. **约束**：每周可运动的时间段与类型、可用设施、饮食偏好/禁忌、健康注意事项
6. **饮食节奏**：三餐大致摄入量？每天有没有零食习惯？（有了这些数值，可以设定热量缺省值）
7. **历史经验**：之前减重有效的方法？失败/反弹的经历和触发因素？（一两句话即可）

收集完毕后向用户口头总结确认，然后创建以下文件：

- `data/profile.md` — Markdown 格式，按 `references/profile-schema.md` 的结构写入用户画像
- `data/tracker.json` — JSON 格式，写入结构化追踪参数：
  - `created_at`、`last_review`、`last_record` 初始化为当天
  - `phases` — 根据目标生成 2-4 个阶段（划分方法论见 `references/planning-guide.md`）
  - `milestone_interval_kg` — 根据总减重目标自动建议：<10kg→1kg，10-20kg→2kg，>20kg→3kg
  - `review_cadence_days` — 默认 7
  - `warning_kg` — 默认 1.0
  - `critical_kg` — 默认 2.0
  - `last_milestone_weight` — 初始化为当前体重
  - `ree` — 日均静息消耗（kcal），来自访谈或用户自行设置
  - `default_meals` — 三餐缺省热量：`{"breakfast":450,"lunch":650,"dinner":600,"snack":0}`（零食无缺省值，没记就是 0）
  - `goal_deficit` — 每日目标热量缺口（默认 500 kcal）

详细的 profile.md 格式和 tracker.json schema 见 `references/profile-schema.md`。分阶段划分方法论见 `references/planning-guide.md`（按需加载）。

## 1. 日常记录

当用户告知当日体重/体脂率数据时：

### 步骤
1. 调用 `scripts/record.py <体重kg> <体脂率%> [肌肉量kg]` 将数据追加到 `data/records.csv`
2. 向用户确认记录成功

### 即时反馈原则
- 单日涨跌在 0.5kg 以内 → 简单确认，不展开分析
- 单日波动超过 1kg → 主动提及可能是水分/钠摄入/排泄节律，不代表脂肪变化
- 提到 7 日均线方向（降/稳/微升），帮用户聚焦趋势而非单日数字
- **不要**：一惊一乍、过度解读、长篇分析、给未经请求的建议

### 滞录检测
如果 `review.py` 输出的 `days_since_record` 超过 3 天，在对话中提一句（如"有几天没记录了，今天方便测一下吗？"），不反复催促。

## 2. 饮食记录

当用户告知当日吃了什么、或者报出某餐的热量数据时：

### 记录一餐
调用 `scripts/nutrition.py add <餐次> <热量> [--protein N] [--carbs N] [--fat N] [--note "..."]`。

餐次可选：`breakfast` / `lunch` / `dinner` / `snack`。零食可以记录多条。

```
例: nutrition.py add lunch 650 --protein 35 --carbs 70 --fat 20 --note "鸡胸+米饭"
```

### 查看与修改缺省值
- 查看：`nutrition.py defaults`
- 修改：`nutrition.py defaults --set breakfast=500 lunch=700`

### 缺省值机制
- 三餐（早/午/晚）未记录时，用 `tracker.json` 中 `default_meals` 的值自动填充
- **零食不设缺省值**：没记零食就是 0 kcal（零食可有可无，不能假定每天都吃）
- 填充的值在 summary 输出中标记为 `auto_filled: true`

## 3. 运动记录

用户用手环/手表记录的运动热量，直接录入：

```
例: exercise.py add 跑步 280 --duration 30
例: exercise.py add 力量训练 200 --duration 45
```

### 查看摘要
`exercise.py summary [--days 7]` — 输出近 N 天的运动概览 JSON。

## 4. 定期回顾

### 触发条件
每次会话开始时，调用 `scripts/review.py`。若返回 `review_due: true`，主动告知用户"该做周回顾了"，询问是否现在做。

### 回顾流程
1. **导出数据**：调用 `scripts/export.py`，stdout 输出 JSON 包含 5 个 CSV 文件路径（饮食明细、运动明细、每日汇总、身体数据、阶段信息）
2. **解读数据**：AI 读取上述 CSV，用自己的语言组织分析要点，重点关注趋势方向和热量缺口。如需可视化，AI 可自行根据 CSV 数据绘图
3. **结构化分析**：基于导出的数据和 `review.py` 的输出，组织以下要点：

#### 分析要点
- **趋势方向**：7 日均线是向下/走平/向上？对比上次回顾的变化
- **速度是否安全**：每周减重是否落在 0.5-1.0 kg 区间？过快（>1.5）注意肌肉流失，过慢（<0.3）可能是平台期
- **去脂体重**：升/稳/降？若持续下降，提示蛋白质摄入和力量训练
- **与计划对比**：当前体重 vs 该阶段预期体重，超前/正常/滞后
- **🔥 热量缺口**：近 7 日平均缺口是否达到目标（`goal_deficit`）？
  - 若几乎没有缺口（<100 kcal/天）→ 温和询问饮食是否有特殊情况
  - 若缺口持续偏大（>1000 kcal/天）→ 提示注意肌肉流失和代谢适应
  - 热量摄入使用缺省值填充时，提醒"本周有部分天数使用了估算值"

#### 偏差应对
根据 `review.py` 输出的 `deviation.level`：
- **green**：肯定势头，鼓励保持
- **yellow**：追问近况（饮食/运动有无变化），给 1 条最小调整建议，不调整计划
- **red**：深入讨论原因（生活变化？执行松懈？计划不合理？），加载 `references/planning-guide.md` 获取调整策略，给用户 2-3 个选项（维持/微调/重定阶段目标）

### 回顾完成
回顾结束后调用 `scripts/review.py --mark-done` 更新 `last_review` 时间戳。

### 回顾原则
- 每次回顾先指出进步（哪怕小），再谈需要关注的地方
- 聚焦当前阶段，不把后面阶段的压力提前
- 用数据说话：让 CSV 数据承载事实，口头评论只做解读

## 5. 执行支持（核心）

此部分是减重成功的关键——定计划不难，执行到底才是难点。以下给出判断框架和行动原则，具体的表达方式、时机选择、语气调整由 AI 根据对话上下文自行判断。

### 困难应对框架

当用户表达以下信号时触发——忙、累、不想动、压力大、想吃、暴食、外卖、没时间、反弹、没效果：

1. **先承接情绪**：承认困难真实存在，不否定、不说教。"确实，新环境/加班/压力下维持节奏很难。" 然后让用户多说几句，不要急着给方案。

2. **最小可行行动**：给出的建议必须是"今天就能做到、不需要意志力"的粒度。例如"今天中午下楼走 10 分钟"而非"每周力量训练 4 次"。一条即可，不列清单。

3. **不对比、不讲大道理**：不说"你应该""别人都能做到""坚持就是胜利"。

### 历史模式预警

初始化时记录的失败经历（存储在 `profile.md` 中）是最重要的预防信号。

- 定期回顾发现趋势恶化 + 用户近期提到"忙/顾不上"时 → 读取 `profile.md` 中的历史经验
- 若当前行为与历史反弹模式相似（如上次是从"太忙了"→"顾不上记录"→"外卖失控"→"彻底放弃"），可以温和但直接地点出关联
- 预警在整轮对话中只做一次，不重复

### 停滞期应对

- 体重连续 3 周不降（7 日均线在 ±0.3kg 区间波动）→ 告知这是正常的生理平台期
- 检查去脂体重：若稳定 → 脂肪在减但肌肉增长，总体重不降反而是好事
- 建议调整变量而非加大力度：换运动类型、调整碳水时机、增加 NEAT（非运动消耗）而不是更狠地节食

### 计划调整决策

加载 `references/planning-guide.md` 作为方法论参考。以下情况考虑调整：
- 连续两次红灯
- 用户生活条件发生重大变化（搬家、换工作、受伤）
- 用户主动提出

调整时给出 2-3 个具体选项让用户选择，不要替用户做决定。确认后同步更新 `profile.md` 和 `tracker.json`。

## 6. 里程碑

`review.py` 自动检测里程碑（每 `milestone_interval_kg` 触发一次）。若输出中包含 `milestone` 字段，向用户指出这一成就。

里程碑的目的不是数据汇报，而是让用户感受到**持续的小胜累积成最终的大胜**。根据上下文即兴表达（一句肯定即可），不套用固定文案。

每完成一个阶段目标时额外庆祝——此时不仅是数字变化，更是"在新的生活条件下找到了可执行的方法"。

## 7. 脚本速查

| 脚本 | 调用方式 | 副作用 |
|------|---------|--------|
| `scripts/record.py` | `<体重kg> <体脂率%> [肌肉量kg]` | 追加 CSV，更新 tracker 的 last_record |
| `scripts/nutrition.py` | `add <餐次> <热量> [--protein N] [--carbs N] [--fat N] [--note ...]`<br>`summary [--days N]`<br>`defaults [--set key=val]` | 追加 CSV；查看/修改缺省值写入 tracker |
| `scripts/exercise.py` | `add <类型> <消耗kcal> [--duration N] [--note ...]`<br>`summary [--days N]` | 追加 CSV |
| `scripts/plot.py` | 无参数 | 生成 `dashboard.png`（已保留，不再作为主要输出） |
| `scripts/export.py` | 无参数 | 导出 5 个 CSV（饮食/运动明细、每日汇总、身体数据、阶段信息）到临时目录，stdout 输出 JSON |
| `scripts/review.py` | 无参数 或 `--mark-done` | 无文件修改（除非带 --mark-done）；输出 JSON 到 stdout |

所有脚本自动定位 `data/` 目录（相对于 SKILL 根目录）。不需要在调用时指定路径。

## 8. 文件结构

```
fitness-tracker/
├── SKILL.md                        # 本文件
├── scripts/
│   ├── record.py                   # 体重/体脂记录
│   ├── nutrition.py                # 饮食记录
│   ├── exercise.py                 # 运动记录
│   ├── plot.py                     # 生成仪表盘 PNG（已保留，不再作为主要输出）
│   ├── export.py                   # 导出结构化 CSV 数据
│   └── review.py                   # 回顾检查
├── references/
│   ├── profile-schema.md           # 数据格式 schema
│   └── planning-guide.md           # 分阶段方法论
└── data/                           # 用户数据（运行时生成）
    ├── profile.md                  # 用户画像（Markdown）
    ├── tracker.json               # 结构化参数（JSON）
    ├── records.csv                # 体重时序记录
    ├── nutrition_log.csv          # 饮食记录
    └── exercise_log.csv           # 运动记录
```
