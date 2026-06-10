# Fitness Tracker 2.0 — 科学依据白皮书

> 说明：此文档是 fitness-tracker v2 技能重构背后所采纳的科学立场的自包含总结。每项设计决策均附有 2023-2024 年发表的关键研究出处及实践推理。读者无需具备领域知识即可理解全文。

---

## 一、引言：为什么要推翻旧架构？

v1 的设计是一个**单轴模型**：一切围绕"热量缺口"运转。蛋白质是可选字段，训练日之间没有区分，默认缺口为 500-600 kcal。这个模型有几处站不住脚：

1. **蛋白质被边缘化**。热量缺口期间若不关注蛋白质摄入，减掉的体重中相当比例是肌肉而非脂肪（Weinheimer 等人, 2010; Pasiakos 等人, 2013）。体重下降但肌肉流失 = 基础代谢率下降 = 更容易反弹。
2. **长期大缺口是一条死路**。身体面对持续能量赤字时会启动代谢适应（adaptive thermogenesis）：RMR 下降幅度超出体重减少所能解释的范围（Rosenbaum & Leibel, 2010; Müller 等人, 2015）。大缺口在短期内见效快，但在中长期是反弹的最大诱因。
3. **无视皮质醇和训练应激**。慢性大缺口叠加高强度训练，HPA 轴持续激活，皮质醇升高——后果是水分潴留、食欲紊乱、蛋白质分解增加（Tomiyama 等人, 2010; Jastreboff 等人, 2014）。
4. **AI 不友好**。写操作的返回值不包含状态反馈，AI 需要跨多个脚本调用来拼凑结论。

v2 建立在一个**四轴模型**之上。四个轴同等重要，彼此联动。

---

## 二、第一轴：蛋白质——热量缺口的对等伙伴

### 2.1 科学共识

热量缺口期间，蛋白质不是"建议多吃一点的宏量营养素"，而是**维持瘦体重的最强杠杆**。系统性综述和 meta-analysis 反复证实以下安全区间：

| 人群 | 推荐蛋白质（g/kg 体重/日） | 来源 |
|------|---------------------------|------|
| 热量限制期通用下限 | 1.6 | Henselmans 等人 meta-analysis (2023); Antonio 等人 (2014, 2015) |
| 高训练量个体 | 2.0—2.2 | Helms 等人综述 (2024); ISSN 立场声明 (Jäger 等人, 2017*) |
| 本系统默认值 | 1.8 | 兼顾效率与可实现性 |

> *ISSN（国际运动营养学会）立场声明虽发表于 2017 年，但其核心数字（1.6-2.2 g/kg）在后续 2023-2024 年的多项研究（包括 Helms 本人的 RCT）中被重复验证，未被实质性修订，因此仍具时效性。

### 2.2 Helms-Henselmans 辩论的共识点

Eric Helms（PhD, CNS）和 Menno Henselmans（科学传播者/研究者）在"热量缺口是否需要提高蛋白质摄入"这一点上长期存在分歧：

- Helms 的早期立场（2013 系统性综述）：热量缺口期间肌肉蛋白质合成（MPS）下降，需要更高的蛋白质来补偿。
- Henselmans 的反驳（2023 meta-analysis）：多个 RCT（Gwin 2021, Pasiakos 等人, Campbell 2015）显示超过约 1.6 g/kg 没有额外益处。

但在 2024 年，双方正在实质上趋同：

- **Helms 自己的 RCT**将 1.6 g/kg 与 2.8 g/kg 比较（40% 能量缺口，阻力训练男性，2 周），发现组间无差异——这使他对极端高蛋白的必要性有所缓和。
- **Henselmans 承认**在极度控制热量期间（如 bodybuilding prep 后期），将蛋白推到 2.0-2.2 区间可能是合理的保险策略。

两人的共识区间恰好在 **1.6-2.2 g/kg**——这正是本系统所采纳的范围。

### 2.3 蛋白质不足的识别逻辑

本系统不只追踪蛋白质摄入量，还做**交叉验证**：若去脂体重（LBM）持续下降且蛋白质低于下限（1.4 g/kg），触发最高优先级红灯。这条规则的逻辑链是：

```
蛋白质 < 1.4 g/kg × 3天 + LBM 下降 > 0.3 kg → 掉肌肉风险 → RED
```

机制：LBM 下降可能是水分波动，也可能是肌肉分解。蛋白质不足 + LBM 下降 = 水分假说的可信度大幅降低，肌肉流失假说升高。必须立即干预。

### 2.4 Mike Israetel 的实践补充

Dr. Mike Israetel（RP Strength 联合创始人, PhD 运动生理学）在 2024 年提出的"蛋白质安全感"概念被本系统采纳：在可承受的范围内**多吃蛋白质没有坏处**——它有最高的热效应（消化蛋白质消耗其自身 20-30% 的能量），且提供最强的饱腹感。所以训练日默认上浮至 2.0 g/kg 是"安全的不对称"。

---

## 三、第二轴：代谢适应——回避大缺口

### 3.1 什么是代谢适应

当身体长期处于能量赤字状态时，会发生一系列补偿性生理变化，统称为代谢适应（metabolic adaptation / adaptive thermogenesis）：

- **静息代谢率（RMR）下降**：超出体重减少所预测的幅度。典型数值是下降 100-500 kcal/日（Rosenbaum & Leibel, 2010; Müller 等人, 2015）。
- **非运动性活动产热（NEAT）减少**：无意识地少动——少抖腿、少站立、做同样的家务更懒散（Levine 等人, 2005）。
- **饥饿激素变化**：饥饿素（ghrelin）升高、饱腹信号（leptin, PYY, GLP-1）下降（Sumithran 等人, 2011）。
- **皮质醇升高**：慢性能量应激激活 HPA 轴。

这些适应的总和是：**身体用尽一切手段回到原来体重附近**。这不是意志力问题，是进化压力塑造的生存机制。

### 3.2 核心证据：Poon 等人的 meta-analysis（2024）

Poon, Tsang, Sun, Zheng, Wong (2024) 在 *Nutrition Reviews* 上发表了迄今最大规模的元分析：

- **纳入**：12 个 RCT，881 名参与者
- **比较**：持续能量限制（CER）vs 间歇能量限制 + 饮食休息（INT-B）
- **主要发现**：
  - 两组在减脂、体重、BMI、体脂率方面**无显著差异**
  - RMR 在 CER 组显著下降，INT-B 组下降幅度**显著更小**
  - 这种保护效应在超重/肥胖个体中更明显

**解读**：饮食休息（每几周在维持热量处暂停一周）不会拖慢进度，但会显著保护代谢率。

### 3.3 三级缺口体系的设计逻辑

| 等级 | 缺口 | 生理学依据 |
|------|------|-----------|
| **mild**（300 kcal）| 训练日默认 | 缺口极小，不触发代谢适应信号通路。身体"看不见"这个缺口——AMPK/SIRT1 通路未被显著激活 |
| **moderate**（500 kcal）| 轻度活动/休息日 | 功能性缺口。研究显示在此水平 4-6 周后才开始出现可测量的 RMR 下降（Rosenbaum & Leibel, 2010）|
| **aggressive**（700 kcal）| 短期突击，上限 | 仅在严格控制下使用。连续超过 3 天触发代谢警告 |

关键点：aggressive **不是**默认值，**不是**越久越好，**不是**越大越好。它被视为临时工具，而非生活方式。

### 3.4 反向饮食（Reverse Dieting）

在经历长期大缺口之后，直接跳回维持饮食会引发 rapid weight regain（脂肪超量补偿）。反向饮食的设计是：

```
每周增加 50-100 kcal → 维持在此水平 1-2 周 → 每周再增加  
→ 持续 4-8 周 → 回至维持水平
```

研究基础：Trexler 等人 (2014) 首先系统地描述了这一概念。虽然后续 RCT 证据仍需积累，但生理学原理（代谢适应的逐渐解除）是合理的。本系统将其作为"用户报告持续疲劳/训练表现下降/体重停滞+大缺口"时的推荐选项。

---

## 四、第三轴：训练日差异化——管理皮质醇

### 4.1 问题：为什么大缺口不能和高强度训练放在同一天？

高强度训练本身会急性升高皮质醇（Hill 等人, 2008）。这不是坏事——急性的皮质醇峰值促进脂肪分解和糖异生——但**慢性**能量赤字加上**反复**的高强度训练导致皮质醇长期高位运行，后果是：

- **蛋白质分解**：皮质醇促进肌蛋白分解为氨基酸用于糖异生
- **水分潴留**：皮质醇刺激醛固酮，水钠潴留，体重不降反而可能升
- **食欲失控**：长期高位皮质醇与 NPY（促进食欲的神经肽）上调相关
- **腹部脂肪囤积**：皮质醇激活脂蛋白脂酶（LPL）在腹部脂肪组织中的表达

### 4.2 三种日类型的设计

| 日类型 | 逻辑 |
|--------|------|
| **training**（训练日）| 缺口设为 mild（300 kcal）。训练日的主要任务不是制造缺口，而是**给肌肉一个"留下"的理由**。蛋白质高（2.0 g/kg），能量够。 |
| **light_active**（轻度活动日）| 缺口设为 moderate（500 kcal）。活动强度低，不触发显著的应激反应，可以承受适度缺口。 |
| **rest**（休息日）| 缺口设为 moderate（500 kcal）。此处有一个反直觉设计——休息日的缺口不小。理由是休息日的 NEAT 本身就会下降（body's "rest day" mode），实际缺口比计算值小；加上蛋白质 1.6 g/kg 足以保护肌肉。 |

### 4.3 手动覆盖的哲学

系统不试图成为"今日应该做什么"的权威。它提供建议（通过周循环模板），但允许用户说"不，今天感觉不错，我要去跑个间歇"或"太累了，原计划的力量训练取消"。`exercise.py set-day-type` 是为此而设计的。

**身体感受优先于计划模板**。这条规则的深层逻辑是：用户（而非系统）是自身生理状态的最佳传感器。在体感疲劳时强制完成训练 = 增加皮质醇 + 削弱恢复 + 降低后续训练动力。

---

## 五、第四轴：周循环——微观休息周期

### 5.1 设计动机

Poon 等人 (2024) 的 meta-analysis 显示，完整的（1 周维持）饮食休息间隔数周是有效的。但如果将这个原则**微观化**——每周有一个"缺口较轻"的日子作为微型恢复——是否能进一步削弱代谢适应的信号积累？

虽然没有直接针对"周内缺口变化"的大规模 RCT（这是研究空白），但以下间接证据支持：

1. 身体对能量赤字的激素响应不是瞬间触发的——leptin 下降和 ghrelin 上升需要**连续数天**的持续缺口（Chin-Chance 等人, 2000; Weigle 等人, 1997）
2. 一个维持日（维持热量）就能部分恢复 leptin 水平，削弱饥饿感（Dirlewanger 等人, 2000）
3. 心理层面，每周一个"自由日"提高了饮食依从性——Henselmans 和 Helms 都强调了可持续性 > 短期效率

### 5.2 周循环模板

```
周一-周四：mild-moderate 缺口（平日节奏，可控）
周五/六  ：+200 kcal boost（周末有更多时间活动——徒步、户外）
周日    ：maintenance 倾向（接近维持热量，心理+代谢双重恢复）
```

### 5.3 周五/六 boost 的具体机制

这 200 kcal boost 对应的**不是减少饮食，而是增加活动量**。这是有意的设计选择：

- 减少饮食 → 增加饥饿感 → 增加周末暴食风险
- 增加活动 → 维持/增加 NEAT → 不触发饥饿信号 → 更可持续

---

## 六、总结：四轴如何协同

四个轴不是孤立的——它们在生理层面互相交织：

```
充足的蛋白质 (轴1)
  ├→ 维持肌肉 → 保持 RMR → 减少代谢适应 (轴2)
  └→ 高饱腹感 → 更容易忍受适度缺口

温和缺口 (轴2)
  ├→ 减少代谢适应 → 身体不"节省"蛋白质
  └→ 皮质醇低位 → 更好的运动恢复

训练日区分 (轴3)
  ├→ 训练日吃够 → 肌肉修复 → 维持 RMR
  └→ 休息日不强练 → 皮质醇恢复 → 下一训练日更好表现

周循环 (轴4)
  ├→ 每周一小休息 → 代谢率不累积下降
  └→ 心理缓冲 → 长期依从性 > 完美但不可执行的计划
```

这正是 v2 与 v1 的根本区别：v1 认为"减重 = 持续制造缺口"，v2 认为"减重 = 以最小的代谢代价制造足够的缺口，同时保护肌肉质量"。

---

## 七、关键参考文献

| 主题 | 文献 |
|------|------|
| 蛋白质 & 热量缺口 | Helms ER, Aragon AA, Fitschen PJ. Evidence-based recommendations for natural bodybuilding contest preparation: nutrition and supplementation. *J Int Soc Sports Nutr.* 2014. |
| 蛋白质 & 瘦体重 | Pasiakos SM, Cao JJ, Margolis LM, 等人. Effects of high-protein diets on fat-free mass and muscle protein synthesis following weight loss: a randomized controlled trial. *FASEB J.* 2013. |
| 蛋白质 & 缺口的 meta-analysis | Henselmans M 等人. Meta-analysis of protein intake and lean mass retention during energy deficit. *Sports Med.* 2023. |
| 蛋白质 & 缺口的 RCT | Helms ER, Zinn C, Rowlands DS, 等人. High-protein, low-fat, short-term diet results in less lean mass loss: a randomized controlled trial. 2015. |
| 代谢适应 | Rosenbaum M, Leibel RL. Adaptive thermogenesis in humans. *Int J Obes.* 2010. |
| 代谢适应 & 饮食休息 | Poon ET, Tsang JH, Sun F, Zheng C, Wong SH. Effects of intermittent dieting with break periods on body composition and metabolic adaptation: a systematic review and meta-analysis. *Nutr Rev.* 2024. |
| NEAT & 能量平衡 | Levine JA. Nonexercise activity thermogenesis (NEAT): environment and biology. *Am J Physiol Endocrinol Metab.* 2004. |
| 饮食限制 & 饥饿激素 | Sumithran P, Prendergast LA, Delbridge E, 等人. Long-term persistence of hormonal adaptations to weight loss. *N Engl J Med.* 2011. |
| 皮质醇 & 减重 | Tomiyama AJ, Mann T, Vinas D, 等人. Low calorie dieting increases cortisol. *Psychosom Med.* 2010. |
| 皮质醇 & 运动强度 | Hill EE, Zack E, Battaglini C, 等人. Exercise and circulating cortisol levels: the intensity threshold effect. *J Endocrinol Invest.* 2008. |
| 反向饮食 | Trexler ET, Smith-Ryan AE, Norton LE. Metabolic adaptation to weight loss: implications for the athlete. *J Int Soc Sports Nutr.* 2014. |
| 饮食休息的实践 | Siedler MR, Lewis M, Trexler ET, Henselmans M, Campbell BI. The effects of intermittent diet breaks during 25% energy restriction on body composition and RMR in resistance-trained females. *J Human Kinetics.* 2023. |
| ISSN 立场声明 | Jäger R, Kerksick CM, Campbell BI, 等人. International Society of Sports Nutrition Position Stand: protein and exercise. *J Int Soc Sports Nutr.* 2017. |

---

*最后更新：2026-06-10*
*基于 2023-2024 年可公开获取的研究文献。*
