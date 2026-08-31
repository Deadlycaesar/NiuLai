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

Once every constraint the customer has stated already matches, what separates the target from the
products tied with it?

## 1. We changed the question: not "best match" but "what a real person actually bought"

At 0.861 the system stalled. Forty-four sessions had the target inside the top ten but ranked fourth
to tenth: every disclosed constraint matched, and the scorer had nothing left to break the tie with.
Dense semantic similarity did not help — among the tied candidates the target's median similarity
rank was 81 — because the semantic and the verbatim signal are driven by the same text (exp 10a).

So we stopped asking *which product best matches this sentence* and asked *which product a real
person actually bought*. The targets are drawn from real purchase records, and purchases are not
uniform over a catalogue:

| Signal | Targets | Catalogue | Ratio |
|---|---|---|---|
| `rating_number` (median) | 6,846 | 12 | **570×** |
| has a `price` field | 89.0% | 20.8% | **4.3×** |

`has_price` is not a proxy for popularity. Inside the low-popularity subset the catalogue is 20.2%
against 86.3% for targets — two independent pieces of evidence for the same fact: someone bought
this. Adding both priors resolved 86% of the forty-four tied sessions and moved the score from 0.861
to 0.935 (both intermediate states).

## 2. The stopping rule, applied to the weights we actually ship

The popularity prior kept improving the score as we raised its weight, monotonically, to weight 6
with no plateau. Monotone improvement with no plateau is an over-fitting alarm, not a win, so we
adopted a rule: keep a change only where all three difficulty buckets improve together. That
selected weight 2.0 and left measurable points on the table (exp 10c).

Removing early-turn withholding (§3) moved that optimum, because all ten recommendations now score.
We re-swept — and this is where we want to be exact about what a 200-session grid can and cannot
tell us (exp 39/43):

| `POP_WEIGHT` | 2.6 | 2.7 | **2.75** | 2.8 | 2.9 | 3.0 |
|---|---|---|---|---|---|---|
| TechnicalScore | 0.9425 | 0.9453 | **0.9466** | 0.9457 | 0.9450 | 0.9444 |

The grid peaks at 2.75, and 2.75 is what we ship. But the peak is one grid point wide and stands
**+0.0009** above its neighbour — which is precisely the figure our own noise rule (§10) calls one
session flipping. Under paraphrase stress the ordering does not survive: at L1 and L3, and on the
L1–L3 mean, weight 3.0 equals or beats 2.75. The advantage exists only on the unmodified two hundred
sessions we tuned on.

We therefore report 2.75 as where our grid landed, not as an optimum our stopping rule selected, and
anything in 2.5–3.0 is the same system to within 0.0035. The companion weight is different in kind:
`HAS_PRICE_WEIGHT=0.95` beats 1.0 by 0.0025, above our threshold, so that one we do claim.

## 3. Removing early-turn withholding was a product decision, not a score decision

Showing one product instead of ten on low-confidence turns was worth **+0.0286** (exp 37). A hit
ends the session and locks in that turn's rank, so converting at turn one in seventh place is worth
less than converting at turn two in first. Thirty-one sessions sat in exactly that trade.

Showing a shopper a single product is not a storefront, so we removed it from the default. The
measured price: HitRate is unchanged at every one of the five paraphrase levels, MTTC improves from
2.155 to 1.920, and the entire cost falls on MRR — on ranking precision the mechanism had been
buying by declining to show candidates.

## 4. We proved our own ceiling

Thirty-eight of two hundred sessions are not ranked first. A session-by-session comparison against
the withholding configuration splits them cleanly: **seven** are imperfectly ranked under both and
are information-theoretically indistinguishable — the target shares an identical intent card and
category with other catalogue items, so the generated dialogue is byte-identical, and one target has
forty-six such twins. The other **thirty-one** are exactly the sessions withholding used to rescue:
the same thirty-one identified in Chapter 1, and the measured price of Section 3. Against the
withholding configuration the reachable MRR gain beyond those seven was 0.00075, below our own noise
threshold (exp 27).

## Net effect

The prior axis is worth 0.074 (0.861 → 0.935) and is the largest single gain in the project. It did
not come from a better method; it came from noticing we had been asking the wrong question. The
ceiling above it is 7/200 sessions wide and provably closed.

---

# Chapter 7 · Model choice, cost, latency and tokens (500 words) · official disclosure

## The question this chapter answers

Where in the pipeline does a language model earn its keep, what does running it cost in money,
latency and tokens, and what happens when the network is taken away?

## 1. We tested the LLM in both positions; only one worked

| LLM used for | Measured | Verdict |
|---|---|---|
| **Ranking** — listwise rerank of the top 20 | titles only **−0.020**; with verbatim-hit evidence **−0.0004** (3-run mean 0.9511 ±0.0005); **106×** latency, 9.7 s → 18 min; irreproducible at `temperature=0` | Ceiling is parity, not improvement |
| **Understanding** — parsing paraphrased utterances | **+0.012 to +0.090** across stress levels L1–L4 | Genuinely irreplaceable |

The first negative result initially read as "the model is bad at this". A controlled experiment
showed otherwise: it was information starvation. Once the model sees the same verbatim-hit evidence
the rule scorer sees, the deficit collapses from −0.020 to −0.0004 — and converges to *equality*,
because the rule scorer has already extracted everything that evidence contains (exp 25/25a/25b).

Both results are one finding seen from two ends. Constraints in this benchmark are verbatim
quotations of catalogue text, so in ranking — where the text is already matched — semantics has
nothing left to add; in parsing under paraphrase the verbatim signal is exactly what has been
destroyed, and semantics is the only thing that can recover it. **The model is used to listen, not
to rank.**

## 2. Cost, latency and token disclosure

| | Submitted configuration | Five-level stress sweep with the parsing layer active |
|---|---|---|
| Third-party dependencies | **none** — Python standard library only | none |
| Network calls | **none** | outbound HTTPS to the configured endpoint |
| Model calls | **0** (`llm_calls = 0` across all 200 sessions) | 1,109 |
| Tokens | **0** | 214,250 |
| Estimated cost | **¥0** | **¥0.13 – ¥0.39** |
| Per-turn `respond()` | median **2.3 ms** / p95 2.8 ms / max 3.5 ms | + 0.72–1.18 s mean per model call (p95 1.0–5.6 s) |
| Full 200-session run | **9.7 s** including startup | — |
| Peak resident memory | **530 MB** | unchanged |

Startup is 4.1–6.9 s once, loading 50,000 products and building the SQLite FTS5 index. Full working
notes: [`COST_AND_LATENCY.md`](COST_AND_LATENCY.md).

## 3. Network access declaration

**The submitted configuration requires no network access, no credentials and no third-party
packages, and its score is unchanged without them.** `LLM_PARSE=1` is a default-on *enhancement*,
not a dependency: on unmodified phrasing it makes zero calls — the score is bit-identical to the
rule-only path, session by session — and it wakes only where both rule layers have already failed.
With no credentials the client returns immediately without opening a socket; with credentials but no
route, two consecutive failures trip a circuit breaker and the process reverts to the rule-only path
for its remaining lifetime. In a network-restricted scoring environment the headline number is
therefore identical, which we verified directly against a black-holed proxy (exp 29).

## 4. Model and timeout configuration

The endpoint is `deepseek-v4-flash`, reached through `LLM_BASE_URL` and `LLM_MODEL`; any
OpenAI-compatible endpoint substitutes, and configuring none at all is a valid configuration. The
parsing layer carries its own budget, `LLM_PARSE_TIMEOUT=12`, rather than sharing the 45 s ranking
timeout: measured p95 for a parse call is 1.0–5.6 s, so 12 s leaves roughly a factor of two, and it
caps the worst turn at two attempts of 12 s instead of two of 45 s. The specification reserves the
right to score a timeout as a miss, which makes the tighter budget the conservative choice.

## Net effect

Zero tokens, zero cost and zero network on the path that is actually scored; a measured
¥0.13–¥0.39 and a documented degradation path on the one that is not.

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
