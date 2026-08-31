# D (@BestBucky) — Chapters 6 & 9

> 任务卡：[`team/报告-分章大纲.md`](../报告-分章大纲.md) §5。**直接写英文**，写完交 @LIN XIAOXIAO 整合润色。
> 动笔前扫 **附录 C 术语表**（英式拼写；permutation test / prior axis 等术语照表用）。
> 数字只从 **附录 A 口径快照表** 取。合计 1000 词。**03:00 前交**。
>
> **两章都是纯新增，也都是你自己的第一手工作。** 记忆单独成章的理由见大纲 §2 ——
> 官方 Innovation Directions 第 5 条点名了 "safe personalization using the aggregate profile"，
> 评委按单子看，缺席比负结果更糟。

---

# Chapter 6 · Safe personalisation: a negative result on a direction the brief named (400 words)

## The question this chapter answers

## 1. What we built
<!-- preference_tags (closed set of 9) → soft-preference lexicon; cross-turn signals (stagnation / rejection);
     context distillation; two wiring attempts.
     可写可不写的好数字：第 10 轮 prompt 长度 = 第 3 轮的 0.80×（不增反减，状态是收敛的） -->

## 2. The first number looked like signal: 1.745× lift

## 3. The confound
<!-- 目标商品都是热门商品（第 5 章那个 570×）→ 文案更长更丰富 → 任何词都更容易命中，与"匹配"无关 -->

## 4. The permutation test
<!-- 同一批目标，只打乱 profile 配对 → 1.021×, z = +0.93, p ≈ 0.18 (200 permutations)；效应量 2% -->

## 5. State the conclusion as information, not implementation  ← 本章的落点
<!-- "The ceiling is not set by how we wire it, weight it or gate it — it is set by information content,
     and the data does not carry it."
     这一句关掉了整类工作（冷启动限定 / 只接检索 / 只接排序 / 扫权重 / 按 tag 分档）——
     请把"省下的时间比它可能提的分多得多"这层意思写出来 -->

## 6. Two same-batch negatives
<!-- rating_style → 目标 avg_rating 4.41 / 4.28 / 4.31 无区分度；
     preference_tags → 目标品类的表面偏离全是小计数噪声（112 个品类分 200 样本） -->

## 7. Where the code went
<!-- lexicon.py / signals.py 保留在仓库、15 个单测、不接生产路径；
     actionable_rejections 接入实测零效果 (exp 18)：HitRate 已 0.995、MTTC 2.23，
     绝大多数会话在攒到停滞信号之前就结束了 -->

## 8. One sentence handing off to Chapter 9
<!-- 什么条件下它会成立：需要购买序列 / 浏览行为，而不是聚合标签 -->

## Net effect

---

# Chapter 9 · From benchmark to a real storefront (600 words)

## The question this chapter answers

## 1. The benchmark-shaped mechanisms unload with one flag
<!-- exp 30: MIRROR_BONUS=0 EARLY_TOPK=0 → 0.9694 → 0.9383, HitRate 1.000 in both configurations
     ⚠️ 这两个数是旧档（藏牌开）口径，必须标明，别和 0.9466 混
     论点不是"我们没作弊"，是"赛技可一键卸载，卸载后命中率不掉" -->

## 2. Mechanism-by-mechanism mapping  ← 本章骨架，至少六行

| Mechanism | Why it holds in this benchmark | In a real storefront | Keep / replace |
|---|---|---|---|
| Verbatim substring match |  |  |  |
| Intent-card mirror bonus |  |  |  |
| Constant `other` question |  |  |  |
| Stop-on-hit |  |  |  |
| Hand-weighted linear scorer |  |  |  |
| Aggregate profile |  |  |  |

<!-- 第 6 行是你和第 6 章的接口：你有第一手证据说明"数据里没有这个信息"，
     所以你最有资格说真实世界需要什么数据这套才成立 -->

## 3. Engineering budget
<!-- 50k SKU / SQLite FTS5 → 千万级要换 ANN；延迟预算（规则 2.3 ms vs LLM 解析 p95 1.0–5.6 s）
     ⇒ 只在低置信轮调用的成本模型；冷启动 4.1–6.9 s；内存 530 MB / dense 1191 MB（onnx 787 MB） -->

## 4. Path to production and observability
<!-- 影子流量 → A/B → learned ranker；把 parser_accuracy 这种分层指标搬到线上
     （理由：端到端指标会吸收上游缺陷，我们这次已经吃过一次） -->

## 5. Risks and compliance
<!-- 隐私边界；**推荐可解释性**（官方 Innovation Direction 第 7 条，现稿最弱的一环）；冷启动；长尾品类 -->

## Net effect
