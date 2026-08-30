<!--
给统稿人的说明 —— 定稿前删掉这段注释：
0. ⚠️ 主笔归属已变更（留言板 T-014 ①）：**@陈智龙 落笔、@BestBucky 审阅**。
   下面第 2 条「D 的 AI 助手不可用」的前提已不成立，D 的 §8/§9 部分已自行补完。

1. 语言：写成英文，因为这是给评委看的（官方文档、Devpost 都是英文）。
   团队内部文档保持中文不变。
2. 这是**草稿**，C 起的。你的 AI 助手不可用，所以我没给大纲、直接给了可编辑的初稿。
   每个数字都可复现，命令写在 §7。
3. 需要你补的地方我用 `TODO(D)` 标出来了，主要是 §6 团队贡献里各人的自述，
   和 §8 你想加的个人反思。
4. 篇幅：submission_rules 要求 "a short report"，现在约 1300 词，是合适的长度。
   要砍先砍 §5（Limitations 里的第 3、4 条）。
5. 引用的原始数据全在 team/experiments.md（27 组实验）与 team/成本与延迟披露.md。
-->

# NiuLai — Conversational E-Commerce Search Agent

**TikTok TechJam 2026 · Track 4** · Team NiuLai · Final report

**Public-set TechnicalScore 0.9694** (HitRate@10 **1.000** / MRR 0.975 / MTTC 2.155), up from the
official weak-BM25 baseline of 0.107. Fully offline by default: zero third-party dependencies,
zero API tokens, zero cost, 200 sessions evaluated in 9.7 seconds.

---

## 1. What we found first, and why it shaped everything else

Before writing an agent we read the evaluator's source. Three facts from it determined the whole
architecture, and each one contradicted our initial plan:

**The simulated customer never reads our prose.** `customer_reply()` takes `ask_attribute` — a
single value from a 10-item enum — and nothing else. The `message` field is only type-checked
(`local_evaluator.py:243`). Our entire channel to the customer is ≈3.3 bits per turn. No amount of
prompt craft can change what the customer says. This is why our clarification copy is optimised for
human judges and the demo, not for score.

**The customer's utterances are a deterministic function of the target product.** The hidden intent
card is generated at evaluation time by `intent_card()` from the target's own catalogue metadata,
and the constraint strings the customer speaks are *verbatim fragments of that product's text*.
This makes verbatim substring matching against the catalogue a near-fingerprint signal — the
strongest single feature in our ranker.

**A hit ends the session immediately, locking in that turn's rank.** Hitting at turn 1 in position 7
is worth 0.743 per session; hitting at turn 2 in position 1 is worth 0.980. We found 31 sessions
sitting in exactly that losing state.

## 2. Architecture

```
respond() ─→ M1 parser / state machine ─→ M2 retrieval ─→ M3 ranking ─→ message + ask_attribute + top-10
              (three-layer defence)        (BM25 + dense)   (rules; LLM optional)
```

**M1 — dialogue control.** A slot state machine over the customer's disclosed constraints, plus a
three-layer parsing defence (§4). Question policy is a constant: always ask `other`. This is
provably optimal here — `classify_constraint()` can never return `category` or `brand`, so asking
either is guaranteed to be wasted, while `other` matches any undisclosed constraint. We kept a
general entropy-based policy behind a flag (`ASK_POLICY=entropy`, measured 0.830 vs 0.861 at the
time) for ablation and for the general case.

**M2 — retrieval.** SQLite FTS5 keyword search with field weighting, per-constraint phrase recall
for slots of ≥3 tokens, and an optional pre-computed dense route (bge-small-en-v1.5) fused as a
non-displacing union. Recall@pool reached **1.000** — retrieval stopped being the bottleneck early.

**M3 — ranking.** An offline rule scorer combining weighted verbatim constraint hits, an intent-card
mirror bonus, category match, purchase priors, and normalised BM25 rank. This is the default and only
scoring path.

## 3. The insight that moved the score most: relevance axis vs. prior axis

At 0.861 we hit a wall. 44 sessions had the target inside the top-10 but ranked 4th–10th: every
stated constraint matched, and the scorer had no way to break the tie. Our teammate's diagnostic
showed dense semantic similarity was useless there (median similarity rank of the target among tied
candidates: 81) — semantic and fingerprint signals are driven by the same information.

We changed the question. Instead of asking *"which product best matches this sentence"* we asked
*"which product is a real person more likely to have actually bought"*:

| Signal | Target products | Whole catalogue | Ratio |
|---|---|---|---|
| `rating_number` (median) | 6,846 | 12 | **570×** |
| has a `price` field | 89.0% | 20.8% | **4.3×** |

Both follow from the targets being drawn from real purchase records. `has_price` is *not* a proxy
for popularity: within the low-popularity subset the catalogue is 20.2% vs. targets 86.3%.

Adding these two priors solved **86% of the 44 tied sessions** and took the score 0.861 → 0.935.
Combined with deliberately withholding recommendations on low-confidence turns (§1's third finding —
show one candidate on turns 1–2 instead of ten), rank-1 sessions went from 106 to 189 of 200.

## 4. Robustness: the risk we could not measure, so we built a way to measure it

The official specification reserves the right to add natural-language paraphrasing to the simulator.
Our entire pipeline rested on verbatim matching, and the public set — with its fixed templates —
could never reveal that exposure.

We built a paraphrase stress harness (`scripts/paraphrase_stress.py`) that wraps the Agent and
rewrites the customer's utterances before the Agent sees them, **without modifying the evaluator**.
Five graded levels isolate different failure modes. The first result was counter-intuitive:

> Changing only the *sentence templates*, leaving every constraint string verbatim, cost **−0.183** —
> 87% of the total damage. Changing the constraint values themselves cost only 0.028 more.

The fragility was in template matching, not in verbatim matching. That reframed the fix from
"understand meaning" to "extract fragments from unfamiliar sentences", which needs no model at all.
The result is a three-layer defence, each layer firing only when the previous one fails:

| Layer | Mechanism | Cost |
|---|---|---|
| 1. Strict templates | Exact evaluator句式 | free |
| 2. Rule salvage | Colon payload, separators, override cues, category extraction | free |
| 3. LLM extraction | Verbatim-verified fragment extraction; paraphrased output rejected | optional, default off |

Measured across stress levels (L0 = unmodified public set):

| | L0 | L1 phrasing | L2 + short values | L3 + spec strings | L4 no-colon |
|---|---|---|---|---|---|
| Before | 0.9620 | 0.7792 | 0.7585 | 0.7523 | 0.8330 |
| After | **0.9694** | **0.9501** | **0.9218** | **0.8896** | **0.9327** |

Layer 2 is constructed so it can only fire when strict templates miss — it is byte-for-byte inert on
the public set. Layer 3 additionally validates that anything the model returns is a contiguous
substring of the original message; fingerprint evidence outranks the model's linguistic taste.

## 5. Model choice: we tested the LLM in both positions and only one worked

| LLM used for | Measured | Verdict |
|---|---|---|
| **Ranking** (listwise rerank of top-20) | titles only: **−0.020**; with hit evidence: **−0.0004** (3-run mean 0.9511 ±0.0005) | Ceiling is *parity*, not improvement |
| **Understanding** (parsing paraphrased utterances) | L4 stress **0.8330 → 0.9327** | Genuinely irreplaceable |

The first negative result was initially read as "the LLM is bad at this". A controlled experiment
showed otherwise: it was information starvation. Once the model sees the same verbatim-hit evidence
the rule scorer sees, the deficit collapses from −0.020 to −0.0004 — but it converges to *equality*,
because the rule scorer has already extracted everything that evidence contains. Enabling it costs
**~106× the wall-clock latency** (9.7 s → 18 min for the full set) and makes scores irreproducible
(server-side variation persists at `temperature=0`).

**So the LLM is used to listen, not to rank.** Both LLM paths default to off; the offline path is the
only default path. Model: GLM-4.7-Flash (free tier), swappable via `LLM_BASE_URL` / `LLM_MODEL`.
Full latency/token/cost numbers: [`team/成本与延迟披露.md`](team/成本与延迟披露.md).

## 6. Method: how we decided what to keep

Three rules, adopted after the first over-fitting scare and applied to every change since:

**Stop where all three difficulty buckets improve together.** The popularity prior kept raising the
score up to weight 6 — monotone improvement with no plateau is an over-fitting alarm, not a win. At
weight 2.0 easy/medium/hard all improved; at 3.0 easy rose while medium fell. We stopped at 2.0 and
left 0.008 on the table.

**Convert small gains into "how many sessions is that?"** With 200 samples one session is worth
0.0007–0.0025. A tuning result of +0.0009 is one session flipping — indistinguishable from noise. We
rejected two such "improvements".

**Every assumption gets a failure simulation.** Three implementations of the withholding rule scored
identically on the public set; only by simulating parser failure did we find that one of them
degrades catastrophically (HitRate 0.950) while another exits safely. Public-set parity is not
evidence of equivalence.

We also disproved things and kept the records: profile-based soft preferences (permutation test:
1.021×, p≈0.18 — the apparent 1.745× lift was a text-length artefact), dense similarity as a
tie-breaker, feature-count priors, and prior-weight decay.

**We then proved our own ceiling.** `scripts/ceiling_diagnostic.py` decomposes the remaining 0.0228
to theoretical maximum: 7 of the 8 imperfectly-ranked sessions are *information-theoretically
indistinguishable* — the target shares an identical intent card and category with other catalogue
items, so the generated dialogue is byte-identical (one target has 46 such twins). The reachable MRR
gain is 0.00075, below our own noise threshold. Further tuning would buy noise and pay for it in
private-set generalisation.

## 7. Reproduction

```bash
python3 scripts/prepare_catalog.py        # verify SHA-256, extract catalogue (once)
python3 -m evaluator.local_evaluator      # 0.9694 — no dependencies, no network, ~10 s
python3 scripts/check_guards.py           # red-line self-check + 26 unit tests
python3 scripts/paraphrase_stress.py      # robustness across 5 stress levels
python3 scripts/ceiling_diagnostic.py     # remaining headroom, decomposed
```

Python 3.10+. The base path requires no third-party packages; `requirements.txt` applies only to the
optional dense route (`USE_DENSE=1`), which degrades to pure BM25 when assets are absent.

## 8. Limitations

1. **Public-set saturation is not private-set safety.** HitRate is 1.000 on 200 public sessions; the
   private 800 use different users and targets. Our best proxy is the paraphrase stress table in §4 —
   we expect 0.84–0.95 if paraphrasing is applied, and we have no way to narrow that range.
2. **The `other`-only question policy is specific to this simulator.** It is provably optimal against
   the published `classify_constraint()`, and we disclose that openly; the general entropy policy
   remains available behind a flag.
3. **The dense route ships disabled (`USE_DENSE=0`) — the one place we knowingly left measurable
   value on the table.** It is not dead code: it lifts Recall@pool to 1.000, and under paraphrase
   stress it adds +0.011 to +0.020 at levels L1-L3 — five to ten times our own 0.002 noise
   threshold, and far more than the +0.0016 it is worth on the unmodified public set. We ship it
   off anyway, for two reasons worth stating rather than rounding off. Its benefit is conditional
   on a scenario nobody has confirmed: those paraphrase levels come from a mechanical rewriter we
   wrote ourselves, useful for isolating which layer breaks first, not evidence about the private
   set. Its cost is not a lower score but a harder failure mode: peak RSS rises from 530 MB to
   1191 MB on the torch backend, or 787 MB on ONNX, against a memory ceiling the organizer
   reserves the right to impose and never states. Missing assets degrade gracefully to pure BM25;
   an OOM kill does not degrade at all. Thirty hours from the deadline we were not willing to
   trade an unbounded downside for a conditional gain — but it is one environment variable away
   if those limits turn out to be generous.
4. **Latency was measured on one machine** (Apple M5). Absolute numbers will differ; the ~106× ratio
   between offline and LLM paths should not.

## 9. Team contributions

| | Module | Contribution |
|---|---|---|
| Chen Zhilong (A) | M1 dialogue control | Full-chain prototype (0.107 → 0.861), state machine, value normalisation, three-layer parsing defence, intent-card mirror bonus and phrase recall (→ 0.9694), stability hardening |
| Zhou Junkai (B) | M2 retrieval | Dense route with non-displacing fusion, Recall@pool 1.000, recall regression tooling, the negative diagnostic that redirected ranking work away from semantic signals |
| Lin Xiaoxiao (C) | M3 ranking & generation | Prior-axis discovery (0.861 → 0.935), low-confidence withholding (→ 0.962), paraphrase stress harness and rule salvage layer, LLM three-arm controlled experiment, cost disclosure, ceiling proof, CI and guard tooling |
| Bi Yongqi (D) | M4 memory | Context distillation, profile lexicon, cross-turn signals, and the permutation test that closed the profile-signal question definitively |
| — (E) | M5 evaluation | Absent for the event; responsibilities redistributed across the team |

**In their own words** — one line each; the table alone reads as boilerplate, and this section is
where judges look for evidence of real collaboration.

> **Bi Yongqi (D):** Mine is the module that never moved the score, and the most useful thing I
> produced was the proof of why it could not. After two wiring attempts failed I stopped testing
> implementations and tested the premise instead: shuffling profiles across the same target items
> showed the apparent 1.745x lift was an artefact of target items simply carrying more text, and
> that the true profile-to-target association is 1.021x (p 0.18). That turned "maybe tune it
> differently" into a closed question, and it is why this report gives what we disproved the same
> weight as what we kept.

TODO(A/B/C): three lines still missing — @Chen Zhilong, @Zhou Junkai, @Lin Xiaoxiao.

---

*Evidence for every number in this report: [`team/experiments.md`](team/experiments.md) (27 logged
experiments, including the ones we rejected), [`team/成本与延迟披露.md`](team/成本与延迟披露.md),
and the four module handover documents under `team/`.*
