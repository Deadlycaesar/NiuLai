# B (@周峻恺) — Chapter 4: Retrieval

> 任务卡：[`team/报告-分章大纲.md`](../报告-分章大纲.md) §5。**直接写英文**，写完交 @LIN XIAOXIAO 整合润色。
> 动笔前扫 **附录 C 术语表**（英式拼写：optimised / behaviour / normalised）。
> 数字只从 **附录 A 口径快照表** 取，每条标实验号。目标 600 词。**03:00 前交**。
> 你还兼**全篇数字审计**（05:30–06:30 那一轮）。

## The question this chapter answers
<!-- one sentence -->

## 1. Retrieval stopped being the bottleneck — and we proved it
<!-- Recall@pool 1.000 (exp 6b). 关键：把因果写出来——召回满了 ⇒ 下游任何"多加候选"的方案都不可能提分。
     D 的 profile 注入、LLM 补召回、dense 加候选，全部死在这一条上。 -->

## 2. What the keyword route actually does
<!-- 字段加权 + 逐约束短语召回 (≥3 tokens, FTS5 phrase query) + BM25 sub-pool normalisation (exp 22)。
     public_0020 被短语子池捞回 ⇒ HitRate 首次满分。 -->

## 3. The dense route: one mechanism, two counterfactuals
<!-- exp 38 插桩：哨兵名次 ⇒ only adds recall, never displaces。
     L0: 17 条提前命中 / 11 条名次变差 ⇒ −0.0090。L2: 4 条脱靶被救回 ⇒ +0.0149。
     符号反转的原因是藏牌撤销 (exp 37)，不是 dense 本身变了。 -->

## 4. We ship it off, and the reason is expected value, not magnitude
<!-- exp 31：降级覆盖资产缺失、不覆盖 OOM；+0.015 有条件 vs −1.0 整场归零；P(OOM)<1.5% 无从论证。
     exp 31a 那句诚实的话：基线 530 MB 本身就在同一条曲线上。
     exp 29 断网真机验证逐位一致。 -->

## 5. (optional) The verbatim-saturation gate
<!-- exp 40: L0 0/384 = 0.0% → L1 64.7% → L2 96.0% → L3 96.9%
     ⚠️ 现稿 §5 用过这条，写之前在留言板跟 C 对一下别重复 -->

## Net effect
<!-- one sentence -->
