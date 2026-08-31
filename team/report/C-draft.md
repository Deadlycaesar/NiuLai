# C (@LIN XIAOXIAO) — Chapters 5 & 7 + 全篇整合润色

> 任务卡：[`team/报告-分章大纲.md`](../报告-分章大纲.md) §5。**直接写英文**。
> **先写完自己这两章（目标 02:30），再开始整合** —— 不要一边写一边整合。
> 数字只从 **附录 A 口径快照表** 取。合计 1100 词。
>
> **第 8 章鲁棒性已移交 A**（见大纲 §3 负载说明）。若第 7 章的成本表你也吃不下，
> 说一声，A 代写数字部分，你只写模型选型那半。

---

# Chapter 5 · Ranking (600 words)

## The question this chapter answers

## 1. We changed the question: not "best match" but "what a real person actually bought"
<!-- 570× / 4.3× (exp 10a) + has_price 不是热度代理的反证 (低热度子集 20.2% vs 86.3%)；0.861 → 0.935 -->

## 2. The stopping rule
<!-- 三桶齐涨；撤销藏牌后最优点右移到 POP=2.75 + HAS_PRICE=0.95；
     2.75+1.0 被淘汰是因为单条会话 public_0127 让 medium 回退 0.00038
     —— 规则用在自己的边界样例上，才叫规则 -->

## 3. Removing early-turn withholding was a product decision, not a score decision
<!-- exp 37：代价 −0.0286 100% 落在 MRR；五档 HitRate 逐档不变；MTTC 2.155 → 1.920 -->

## 4. We proved our own ceiling
<!-- exp 27 + 撤销后复算：38/200 非第 1 ⇒ 7 条信息论不可分（一条有 46 个孪生）
     + 31 条 = 藏牌曾救回的那批 = 第 1 章那批。这个闭环请务必点出来 -->

## Net effect

---

# Chapter 7 · Model choice, cost, latency, tokens (500 words) · ⚠️ 官方硬性要求

> ⚠️ 现稿这里只给了一个指向中文文件的链接。`submission_rules.md:13` 要的是
> "a disclosure of latency, token usage, and estimated model cost" —— **表必须内联进英文正文**。

## The question this chapter answers

## 1. We tested the LLM in both positions; only one worked
<!-- ranking: titles −0.020 / evidence −0.0004 (3-run mean 0.9511 ±0.0005), 106× latency (9.7 s → 18 min),
     irreproducible at temperature=0
     parsing: +0.012 to +0.090 across stress levels
     一句话：LLM 用来"听懂"，不用来"排序" -->

## 2. Cost / latency / token table  ← 内联，不要只给链接

## 3. Network access declaration  ← 官方 Model Policy 要求，写成独立加粗一句
<!-- 公开集 llm_calls = 0、分数逐位相同 ⇒ 断网与否 headline 同分；
     enhancement not dependency；无 key / 断网两次失败即熔断退规则路径 -->

## 4. Model and timeout configuration
<!-- deepseek-v4-flash，LLM_BASE_URL / LLM_MODEL 可换，不配也是合法配置；
     LLM_PARSE_TIMEOUT=12（p95 1.0–5.6 s 的两倍余量，最坏单轮 2×12 s；官方保留超时记 miss 的权利） -->

---

## 整合阶段清单（03:00 起）

- [ ] 术语与拼写统一（大纲附录 C），英式拼写全篇一致
- [ ] 每章有"要回答的问题"开头句和"净影响"结尾句
- [ ] 每个数字对得上附录 A 快照表；作废数字黑名单里的一个都没漏进来
- [ ] 章序拼装 + 过渡句（第 4 章末尾接第 5 章、第 6 章末尾接第 9 章）
- [ ] 字数：目标 5100，硬上限 5400；超了按大纲 §4 的砍单顺序砍
- [ ] 现稿抬头 "reaches 0.9710 with one flag" **已删除**（大纲 §7①）
- [ ] 第 0 章摘要下方有分场景四行表（大纲附录 A）
- [ ] 第 12 章每人自述**不改调子**，只改明显语法错

## ⚠️ 请顺手确认一件事
demo 脚本第 13 / 51 / 226 行还是 0.9694，视频按哪个口径录的？见大纲 §7②。
