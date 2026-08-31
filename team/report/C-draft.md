# C (@LIN XIAOXIAO) — Chapters 5 & 7 + 全篇整合润色

> 任务卡：[`team/报告-分章大纲.md`](../报告-分章大纲.md) §5。**直接写英文**。
> **先写完自己这两章（目标 02:30），再开始整合** —— 不要一边写一边整合。
> 数字只从 **附录 A 口径快照表** 取。合计 1100 词。
>
> **第 8 章鲁棒性已移交 A**（见大纲 §3 负载说明）。若第 7 章的成本表你也吃不下，
> 说一声，A 代写数字部分，你只写模型选型那半。

---

# Chapter 5 · Ranking

**The question this chapter answers:** once every constraint the customer has stated already
matches, what separates the target from the products tied with it?

## 1. We changed the question: not "best match" but "what a real person actually bought"

At 0.861 the system stalled. Forty-four sessions had the target inside the top ten but ranked fourth
to tenth: every disclosed constraint matched, and the scorer had nothing left to break the tie with.
Dense semantic similarity did not help — among the tied candidates the target's median similarity
rank sat in the eighties, because semantic and verbatim signal are driven by the same text (exp 7).

So we stopped asking *which product best matches this sentence* and asked *which product a real
person actually bought*. The targets come from real purchase records, and purchases are not uniform
over a catalogue:

| Signal | Targets | Catalogue | Ratio |
|---|---|---|---|
| `rating_number` (median) | 6,846 | 12 | **570×** |
| has a `price` field | 89.0% | 20.8% | **4.3×** |

`has_price` is not a proxy for popularity: inside the low-popularity subset the catalogue is 20.2%
against 86.3% for targets. Two independent pieces of evidence for one fact — someone bought this.
Both priors together resolved 86% of the forty-four tied sessions and took the score from 0.861 to
0.935 (intermediate states).

## 2. The stopping rule, applied to the weights we actually ship

The popularity prior improved the score monotonically up to weight 6 with no plateau — an
over-fitting alarm, not a win — so we kept only changes where all three difficulty buckets improved
together. That selected weight 2.0 (exp 10c). Removing early-turn withholding (§3) moved the
optimum, because all ten recommendations now score, so we re-swept (exp 39/43): 2.7 → 0.9453,
**2.75 → 0.9466**, 2.8 → 0.9457, 3.0 → 0.9444.

The grid peaks at 2.75 and 2.75 is what we ship — but the peak is one grid point wide and stands
**+0.0009** above its neighbour, precisely the figure our own noise rule (§10) calls one session
flipping. Under paraphrase stress the ordering does not survive: at L1, at L3, and on the L1–L3
mean, weight 3.0 equals or beats it. The advantage exists only on the unmodified two hundred
sessions we tuned on. We therefore report 2.75 as where our grid landed, not as an optimum the
stopping rule selected; anything in 2.5–3.0 is the same system to within 0.0035.
`HAS_PRICE_WEIGHT=0.95` is different in kind — it beats 1.0 by 0.0025, above our threshold — so that
one we do claim.

## 3. Removing early-turn withholding was a product decision, not a score decision

A hit ends the session and locks in that turn's rank, so converting at turn one in seventh place is
worth less than converting at turn two in first. Thirty-one sessions sat in exactly that trade, and
showing one product instead of ten on low-confidence turns is worth **+0.0244** against the weights
we ship: `EARLY_TOPK=1` scores 0.9710 where the default scores 0.9466.

Showing a shopper a single product is not a storefront, so we removed it. The measured price:
HitRate unchanged at every one of the five stress levels, MTTC *improves* from 2.130 to 1.935, and
the entire cost falls on MRR — on ranking precision the mechanism had been buying by declining to
show candidates. One flag restores it.

## 4. We proved our own ceiling

Thirty-eight of two hundred sessions are not ranked first, and comparing them against the
withholding configuration splits them cleanly. **Seven** are imperfectly ranked under both and are
information-theoretically indistinguishable: the target shares an identical intent card and category
with other catalogue items, so the generated dialogue is byte-identical — one target has forty-six
such twins. The other **thirty-one** are exactly the sessions withholding used to rescue: the same
thirty-one from Chapter 1, and the measured price of §3. Beyond those seven the reachable MRR gain
was 0.00075, below our own noise threshold (exp 27).

**Net effect:** the prior axis is worth 0.074, the largest single gain in the project — and it came
not from a better method but from noticing we had asked the wrong question. The ceiling above it is
seven sessions wide and provably closed.

---

# Chapter 7 · Model choice, cost, latency and tokens · official disclosure

**The question this chapter answers:** where in the pipeline does a language model earn its keep,
what does running it cost in money, latency and tokens, and what happens when the network is taken
away?

## 1. We tested the LLM in both positions; only one worked

| LLM used for | Measured | Verdict |
|---|---|---|
| **Ranking** — listwise rerank of the top 20 | titles only **−0.020**; with verbatim-hit evidence **−0.0004** (3-run mean 0.9511 ±0.0005); **106×** latency, 9.7 s → 18 min; irreproducible at `temperature=0` | Ceiling is parity, not improvement |
| **Understanding** — parsing paraphrased utterances | **+0.012 to +0.090** across stress levels L1–L4 | Genuinely irreplaceable |

The first negative result read as "the model is bad at this". A controlled experiment showed
otherwise: it was information starvation. Once the model sees the same verbatim-hit evidence the
rule scorer sees, the deficit collapses from −0.020 to −0.0004 — converging to *equality*, because
the rule scorer has already extracted everything that evidence contains (exp 25/25a/25b).

Both results are one finding seen from two ends. Constraints here are verbatim quotations of
catalogue text, so in ranking — where the text is already matched — semantics has nothing left to
add; in parsing under paraphrase the verbatim signal is precisely what has been destroyed, and
semantics is the only thing that can recover it. **The model is used to listen, not to rank.** That
is the configuration we submit: **`USE_LLM=0`**, no model in ranking, and **`LLM_PARSE=1`**, the
parsing layer, which on unmodified phrasing never fires. The re-ranker stays behind its flag with
the measurements above beside it.

## 2. Cost, latency and token disclosure

| | Submitted configuration | Five-level stress sweep, parsing layer active |
|---|---|---|
| Third-party dependencies | **none** — standard library only | none |
| Network calls | **none** | outbound HTTPS to the configured endpoint |
| Model calls | **0** (`llm_calls = 0`, all 200 sessions) | 1,109 |
| Tokens | **0** | 214,250 |
| Estimated cost | **¥0** | **¥0.13 – ¥0.39** |
| Per-turn `respond()` | median **2.3 ms** / p95 2.8 ms | + 0.72–1.18 s mean per call (p95 1.0–5.6 s) |
| Full 200-session run | **9.7 s** including startup | — |
| Peak resident memory | **530 MB** | unchanged |

Startup is 4.1–6.9 s once, loading 50,000 products and building the FTS5 index. Working notes:
[`COST_AND_LATENCY.md`](COST_AND_LATENCY.md).

## 3. Network access declaration

**The submitted configuration requires no network access, no credentials and no third-party
packages, and its score is unchanged without them.** `LLM_PARSE=1` is a default-on *enhancement*,
not a dependency: on unmodified phrasing it makes zero calls, bit-identical to the rule-only path
session by session, and wakes only where both rule layers have already failed. With no credentials
the client returns without opening a socket; with credentials but no route, two consecutive failures
trip a circuit breaker and the process reverts to rules for its remaining lifetime. We verified this
against a black-holed proxy (exp 29).

## 4. Model and timeout configuration

The endpoint is `deepseek-v4-flash` via `LLM_BASE_URL` / `LLM_MODEL`; any OpenAI-compatible endpoint
substitutes, and configuring none is itself a valid configuration. The parsing layer carries its own
budget, `LLM_PARSE_TIMEOUT=12`, rather than sharing the 45 s ranking timeout: measured p95 for a
parse call is 1.0–5.6 s, so 12 s leaves roughly a factor of two and caps the worst turn at two
attempts of 12 s instead of two of 45 s. The specification reserves the right to score a timeout as
a miss, which makes the tighter budget the conservative choice.

**Net effect:** zero tokens, zero cost and zero network on the path that is actually scored; a
measured ¥0.13–¥0.39 and a documented degradation path on the one that is not.

---

## 整合阶段清单（03:00 起）

- [ ] 术语与拼写统一（大纲附录 C），英式拼写全篇一致
- [ ] 每章有"要回答的问题"开头句和"净影响"结尾句
- [ ] 每个数字对得上附录 A 快照表；作废数字黑名单里的一个都没漏进来
- [ ] 章序拼装 + 过渡句（第 4 章末尾接第 5 章、第 6 章末尾接第 9 章）
- [ ] 字数：目标 5100，硬上限 5400；超了按大纲 §4 的砍单顺序砍
- [x] ~~现稿抬头 "reaches 0.9710 with one flag" 已删除~~ → **作废，那句成立，别删**（T-029：
      A 自撤回，实测当前先验下单开 `EARLY_TOPK=1` = 0.971025 / hit 1.000 / MRR 0.9788 / MTTC 2.13；
      他原判据取自实验 28 的旧档。⚠️ 大纲附录 A 的作废数字表仍把 `0.9710` 列为黑名单，
      整合时按"标明口径的对照档"处理，并请 @陈智龙 顺手改大纲那行）
- [ ] **联网声明的两处是故意重复**（官方 Model Policy 要 clearly document，早晚各一次）：
      A 第 2 章是**结论版方框**、C 第 7 章第 3 节是**机制版**。整合时确认两段用词不同、
      不读起来像复制粘贴——第 2 章答"要不要联网"，第 7 章答"不联网时它凭什么不掉分"
- [ ] **天花板段与 2.75 邻域扫描已归第 5 章**（T-029：A 把第 10 章压到 470 词，
      只留"三桶齐涨"规则本身 + 一句 +0.0009 + 指向 §5）。整合时确认第 10 章没有回流重复
- [ ] 第 0 章摘要下方有分场景四行表（大纲附录 A）
- [ ] 第 12 章每人自述**不改调子**，只改明显语法错

## ⚠️ 请顺手确认一件事
demo 脚本第 13 / 51 / 226 行还是 0.9694，视频按哪个口径录的？见大纲 §7②。
