# README 草稿（供 @陈智龙 统稿）

> **这不是最终 README。** 分工 §5 里 README 归 A 主责，这份是 C 按 @BestBucky 在 T-014②
> 的建议（"M3 草稿建议直接写，别等统稿"）提前写的**可粘贴素材**。
>
> **写法说明**：写成可以直接替换掉根目录 `README.md` 的完整形态，而不是零散片段——
> 你要么整份采用后改，要么挑段落搬走，都比给你一堆碎片省事。`TODO(A)` 标的是我不该替你定的地方。
>
> **为什么英文**：官方 kit、`submission_rules`、Devpost 全是英文，评委按这个读。
> 团队内部文档保持中文不变。
>
> **优先级提醒**：`submission_rules.md` 原文 —— *"If your code cannot be reproduced from the
> submitted bundle and instructions, the organizer may treat the run as invalid."*
> 这是板子上唯一一个期望损失＝**全部分数**的事项。

---

# NiuLai — Conversational Shopping Agent

**TikTok TechJam 2026 · Track 4**

A multi-turn shopping agent that locates a customer's intended product among 50,000 items within
10 conversational turns.

| | Public set (200 sessions) |
|---|---|
| **TechnicalScore** | **0.9694** |
| HitRate@10 | **1.000** — all 200 sessions converted |
| MRR | 0.975 |
| MTTC | 2.155 turns |
| Official weak-BM25 baseline | 0.107 |

Runs fully offline: **no third-party dependencies, no network calls, no API cost.**
Full 200-session evaluation completes in **~10 seconds**.

## Quick start

```bash
python3 scripts/prepare_catalog.py     # verify SHA-256 and extract the catalogue (once)
python3 -m evaluator.local_evaluator   # → recommended_technical_score: 0.9694
```

Python 3.10+. Nothing else to install — the default path uses only the standard library.
`requirements.txt` applies solely to an optional dense-retrieval route that is **disabled in the
submitted configuration** (see *Configuration*).

## How it works

The customer discloses requirements gradually; the agent must decide what to ask and what to
recommend on every turn. Three properties of the evaluation harness shaped our design more than any
modelling choice:

**The customer never reads our prose.** `customer_reply()` consumes only `ask_attribute`, a single
value from a 10-item enumeration — the `message` field is type-checked and discarded. Our entire
channel to the customer is ≈3.3 bits per turn. Clarification copy therefore targets human readers,
not score.

**Customer utterances are a deterministic function of the target product.** Constraint strings are
verbatim fragments of the target's own catalogue text, so exact substring matching against the
catalogue behaves like a fingerprint. This is the single strongest feature in our ranker.

**A hit ends the session and locks in that turn's rank.** Converting at turn 1 in position 7 scores
0.743; converting at turn 2 in position 1 scores 0.980. We found 31 sessions sitting in exactly that
losing trade.

### Pipeline

```
respond()
  └─ M1  dialogue control  — slot state machine, three-layer parsing defence, question policy
  └─ M2  retrieval          — FTS5 keyword + per-constraint phrase recall (+ optional dense route)
  └─ M3  ranking            — offline rule scorer (LLM rerank available but disabled)
       └─ message + ask_attribute + ranked recommendations
```

**Ranking signals.** Weighted verbatim constraint hits · intent-card mirror consistency · category
match · **purchase priors** · normalised BM25 rank.

The purchase priors were the largest single gain. At 0.861 we had 44 sessions where the target sat
in positions 4–10 with every constraint matched — a tie the scorer could not break, and one that
dense semantic similarity could not break either (median similarity rank of the target inside those
ties: 81, versus 3 in sessions we ranked correctly). Instead of asking *which product best matches
this sentence*, we asked *which product a real person is more likely to have actually bought*:

| Signal | Target products | Whole catalogue |
|---|---|---|
| `rating_number` (median) | 6,846 | 12 |
| has a `price` field | 89.0% | 20.8% |

Both follow from targets being drawn from real purchase records. Adding them resolved 86% of the
tied sessions.

**Question policy.** Always ask `other`. This is provably optimal against the published simulator:
`classify_constraint()` can never return `category` or `brand`, so asking either is guaranteed to
return nothing, while `other` matches any undisclosed constraint. A general entropy-based policy
remains available (`ASK_POLICY=entropy`) and is measured in `team/experiments.md`.

**Low-confidence withholding.** On the first turns the agent returns only its single best candidate
rather than ten — deliberately trading MTTC for MRR, given that a hit locks in its rank.

## Robustness

The specification reserves the right to add natural-language paraphrasing to the simulator. Because
the public set uses fixed templates, that exposure is invisible to normal evaluation, so we built a
harness to measure it (`scripts/paraphrase_stress.py`) — it rewrites customer utterances before the
agent sees them **without modifying the evaluator**.

The first finding was counter-intuitive: changing only sentence templates, leaving every constraint
string verbatim, cost **−0.183** — 87% of the total damage. The fragility was in template matching,
not in verbatim matching. That turned the fix from "understand meaning" into "extract fragments",
which needs no model:

| | L0 unmodified | L1 phrasing | L2 + short values | L3 + spec strings | L4 no colons |
|---|---|---|---|---|---|
| Before | 0.9620 | 0.7792 | 0.7585 | 0.7523 | 0.8330 |
| After | **0.9694** | **0.9501** | **0.9218** | **0.8896** | **0.9327** |

Three layers, each firing only when the previous one fails — strict templates, rule-based salvage,
then optional verbatim-verified LLM extraction. Layers 2 and 3 are constructed so they cannot fire
on the public set; the L0 column is unchanged by their presence.

## Configuration

Every non-default behaviour is an environment flag, and every flag has a measured ablation in
`team/experiments.md`.

| Flag | Default | Effect |
|---|---|---|
| `USE_LLM` | `0` | LLM listwise reranking. **Disabled deliberately** — see below |
| `LLM_PARSE` | `0` | LLM fallback for the third parsing layer |
| `USE_DENSE` | `0` | Dense retrieval route. **Disabled deliberately** — see below |
| `POP_WEIGHT` / `HAS_PRICE_WEIGHT` | `2.0` / `1.0` | Purchase priors |
| `EARLY_TOPK` / `EARLY_TURNS` | `1` / `3` | Low-confidence withholding |
| `ASK_POLICY` | `other_first` | `entropy` selects the general information-gain policy |

**Why LLM reranking is off.** We tested it in a controlled three-arm experiment. Given only titles it
scored **−0.020**; given the same verbatim-hit evidence the rule scorer sees, the deficit collapsed to
**−0.0004** (three-run mean 0.9511 ±0.0005). So the original negative result was information
starvation, not model weakness — but the ceiling is *parity*, because the rule scorer has already
extracted everything that evidence contains. Enabling it costs ~106× the wall-clock latency and makes
scores irreproducible. The LLM earns its place in *understanding* (L4 above: 0.8330 → 0.9327), not in
ranking.

**Why dense retrieval is off.** It is worth +0.0016 and costs 1191 MB peak RSS versus 530 MB for the
default path (+661 MB is the torch runtime itself; the embedding matrix is only 77 MB). The
specification reserves the right to impose memory limits without stating them. A gain of +0.0016 sits
below our own 0.002 noise threshold, so enabling it would mean accepting a new runtime failure mode
for a benefit we had already agreed not to credit elsewhere. The route remains in the codebase — it
delivered Recall@100 = 1.000 and degrades byte-identically when its assets are absent.

## Method

Three rules, adopted after our first over-fitting scare and applied to every change since:

- **Stop where all three difficulty buckets improve together.** The popularity prior kept improving
  the score up to weight 6 — monotone gain with no plateau is an alarm, not a win. At 2.0 easy,
  medium and hard all improved; at 3.0 easy rose while medium fell. We stopped at 2.0.
- **Convert small gains into sessions.** With 200 samples one session is worth 0.0007–0.0025, so a
  +0.0009 result is one session flipping. Two such "improvements" were rejected on this basis.
- **Simulate the failure of every assumption.** Three implementations of the withholding rule scored
  identically on the public set; only a simulated parser failure revealed that one degrades to
  HitRate 0.950 while another exits safely.

`team/experiments.md` logs 29 experiments including every rejected one. We also proved our own
ceiling (`scripts/ceiling_diagnostic.py`): of the 8 sessions not ranked first, **7 are
information-theoretically indistinguishable** — the target shares an identical intent card and
category with other catalogue items, so the generated dialogue is byte-identical. One such target has
46 twins. Reachable remaining MRR is 0.00075, below our own noise threshold.

## Reproduction and verification

```bash
python3 scripts/check_guards.py        # red-line self-check + 27 unit tests
python3 -m unittest discover -s tests  # unit tests alone
python3 scripts/paraphrase_stress.py   # robustness across 5 stress levels
python3 scripts/ceiling_diagnostic.py  # remaining headroom, decomposed
python3 scripts/trace_session.py --id public_0007   # inspect a single conversation
```

`check_guards.py` verifies that `evaluator/` and `data/public_set.jsonl` are byte-identical to the
official kit, that `starter/agent.py` remains a forwarding shell, that no credentials are committed,
and that every declared test is actually collected.

Latency, token usage and cost: [`team/成本与延迟披露.md`](team/成本与延迟披露.md).
Written report: [`REPORT.md`](REPORT.md).

## Team

TODO(A): 队名 / 成员名单 / Devpost 链接 / demo 视频链接。
建议保留 `REPORT.md` §9 的贡献表并在此处只放一行指过去，避免两处维护同一份内容。

## Data

Derived from **Amazon Reviews 2023** (McAuley Lab, UCSD). See
[`DATA_ATTRIBUTION.md`](DATA_ATTRIBUTION.md). The frozen 50,000-product catalogue and the 200
labelled public sessions are the organiser's; we modified neither.

---

## TODO(A) 清单 —— 我不该替你定的地方

1. **§Team** 队名、成员、Devpost 链接、YouTube demo 链接（视频我 08-31 晚前给你链接）
2. **顶部要不要保留官方 kit 的原始说明**（"What You Receive" 那几段）。我的建议是**不保留**——
   评委看的是我们的系统，官方材料他们本来就有；但这是你的判断。
3. **数字最终核对**：录视频/提交前跑一次 `python3 -m evaluator.local_evaluator` 确认仍是 0.9694
4. **要不要加安装/环境章节**：目前只写了 "Python 3.10+，无需安装"。如果最终提交包含
   `requirements.txt`，可能需要一句更明确的"这些只在 `USE_DENSE=1` 时需要"
