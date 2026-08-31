# NiuLai — Conversational E-Commerce Search Agent

**TikTok TechJam 2026 · Track 4** · Team NiuLai · Final report

**Public-set TechnicalScore 0.9466** (HitRate@10 **1.000** / MRR 0.884 / MTTC 1.935), up from the
official weak-BM25 baseline of 0.107. The same code reaches 0.9710 with one flag; §9 explains why we
do not ship that flag. Standard library only — 200 sessions evaluated in about ten seconds, and the
headline number is bit-identical with or without network access.

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
three-layer parsing defence (§4). Question policy is a constant: always ask `other`. We did not
settle for arguing that this is optimal — we bounded the entire ask dimension exhaustively, and §6
reports both the bound and what the alternative costs. A general entropy-based policy ships behind
`ASK_POLICY=entropy` for the non-simulator case.

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
A fourth mechanism — withholding all but one recommendation on low-confidence turns, following §1's
third finding — then took the score to 0.962 and rank-1 sessions from 106 to 189 of 200. We have
since removed that mechanism from the shipped default; §9 gives the reason and the exact price.

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
| 1. Strict templates | Exact evaluator sentence templates | free |
| 2. Rule salvage | Colon payload, separators, override cues, category extraction | free |
| 3. LLM extraction | Verbatim-verified fragment extraction; paraphrased output rejected | **default on**; zero calls at L0 |

Measured across stress levels (L0 = unmodified public set):

| Parsing stack | L0 | L1 phrasing | L2 + short values | L3 + spec strings | L4 colon-free |
|---|---|---|---|---|---|
| Layer 1 only † | 0.9620 | 0.7792 | 0.7585 | 0.7523 | — |
| + Layer 2 (offline path) | 0.9466 | 0.9259 | 0.8914 | 0.8765 | 0.8269 |
| **+ Layer 3** (`LLM_PARSE=1`, shipped default) | **0.9466** | **0.9374** | **0.9230** | **0.9311** | **0.9168** |

† The Layer-1-only row was measured against the pre-08-31 ranking configuration (`EARLY_TOPK=1`,
`POP_WEIGHT=2.0`). Rule salvage has no runtime switch, so it could not be re-measured under the
shipped weights without editing code, which our stop rule forbids for measurement alone. The row is
kept for its *shape* — template changes alone cost −0.183 — not for its absolute value.
Note also that L3 now scores above L2 once Layer 3 is on: L3 rewrites long spec strings and pushes
more turns into the LLM layer, whose verbatim extraction is cleaner than the rule layer's
whole-sentence fallback; L2's half-damaged values more often slip past the rule layer's own
validation and never reach it. The curve is no longer monotonic in rewrite severity.


Layer 2 is constructed so it can only fire when strict templates miss — it is byte-for-byte inert on
the public set. Layer 3 additionally validates that anything the model returns is a contiguous
substring of the original message; fingerprint evidence outranks the model's linguistic taste.

**Weighing the parser on its own scale.** End-to-end score is a poor instrument for a parsing
defect: it mixes parsing with retrieval and ranking, and a dropped constraint often costs a fraction
of a rank rather than a session. So we scored the parser in isolation against ground-truth constraint
strings (`scripts/parser_accuracy.py`, 450 messages × 5 stress levels × 2 arms):

| | L0 | L1 phrasing | L4 colon-free |
|---|---|---|---|
| Verbatim recall, rules only | 98.8% | 95.2% | 0% |
| Verbatim recall, + Layer 3 | 98.8% | 95.2% | **76.0%** |
| Partial recall, + Layer 3 | 100% | 99.5% | **97.8%** |

The metric immediately paid for itself by exposing two defects that end-to-end score had absorbed
silently. Constraint values containing their own colon (`Department: womens`, roughly one in eight)
were being cut apart by a last-colon rule, capping L1 verbatim recall at 76%. And a garbage
extraction could *succeed confidently* — returning fragments padded with conversational filler — which
shut Layer 3 out precisely when it was needed most. This is the failure mode a cascade has and a
parallel ensemble does not, and we say so rather than claiming the architecture is free of trade-offs.

Both were fixed with a mechanism that follows from the same first principle as the fingerprint
signal: a genuine constraint must occur verbatim in *some* product's catalogue text. The retriever
already answers that question in under a millisecond, so the parser now proposes two colon
candidates and keeps the one the catalogue verifies; an extraction that verifies nothing is not
treated as success, and Layer 3 fires. The fix moved L1 verbatim recall from 76.2% to 95.2%, L4
partial recall from 77.0% to 97.8%, and lifted the hardest stress level from 0.9327 to **0.9551** —
parity with L1 — while leaving the public set byte-identical, session by session.

It also had an effect we did not anticipate. Before the fix, Layer 2 reported success on paraphrased
levels L1–L3 even when the fragments it returned were damaged, so Layer 3 never ran there and the
LLM's contribution was invisible outside L4. With the catalogue verifier deciding what counts as
success, the model now engages wherever the rules genuinely failed, and the whole stress curve moves:
L1 +0.014, L2 +0.033, L3 +0.074. The lesson generalises beyond this system — **a cascade whose early
stages cannot recognise their own failure will silently starve the stages behind them**, and that
deficit is invisible to end-to-end score.

## 5. Model choice: we tested the LLM in both positions and only one worked

| LLM used for | Measured | Verdict |
|---|---|---|
| **Ranking** (listwise rerank of top-20) | titles only: **−0.020**; with hit evidence: **−0.0004** (3-run mean 0.9511 ±0.0005) | Ceiling is *parity*, not improvement |
| **Understanding** (parsing paraphrased utterances) | stress levels **+0.012 to +0.090**; hardest level 0.8269 → **0.9168** | Genuinely irreplaceable |

The first negative result was initially read as "the LLM is bad at this". A controlled experiment
showed otherwise: it was information starvation. Once the model sees the same verbatim-hit evidence
the rule scorer sees, the deficit collapses from −0.020 to −0.0004 — but it converges to *equality*,
because the rule scorer has already extracted everything that evidence contains. Enabling it costs
**~106× the wall-clock latency** (9.7 s → 18 min for the full set) and makes scores irreproducible
(server-side variation persists at `temperature=0`).

These two results are the same finding seen from opposite ends. The constraints in this benchmark
are verbatim quotations from catalogue text, so in the ranking stage — where the text is already
matched — semantics has nothing left to add. In the parsing stage under paraphrase, the verbatim
signal is exactly what has been destroyed, and semantics is the only thing that can recover it.
**Semantic capability pays precisely where verbatim signal dies.** A production system faces the
opposite distribution from this benchmark: real shoppers do not quote product copy, so the L4 end of
our table is closer to their reality than L0 is, and the balance of rules and models should shift
accordingly.

We later turned that sentence into a measurement. A gate that admits dense candidates only when no
candidate in the keyword pool matches every active slot verbatim opens **0 times in 384 turns at
L0**, then 64.7% at L1, 96.0% at L2, 96.9% at L3. The verbatim signal does not merely usually work
on unmodified phrasing — on this benchmark it never fails, which is why the dense route can only
cost ranking precision there, and can only earn recall once paraphrase breaks it.

Routing individual constraints rather than whole turns sharpens this further. Classifying each
constraint by whether it exists verbatim anywhere in the catalogue, sending only the non-existent
ones into a semantic ranking term, and forbidding that term from adding candidates, is an exact
no-op at L0 (0.940829, bit-identical) and worth +0.0029 / +0.0039 at L2 / L3 with HitRate untouched
at every tier. The same routing then shows why the idea cannot pay once the parser is repaired: with
`LLM_PARSE=1` the "vague" bucket collapses — 25.2% → **0%** at L1, 75.5% → 23.0% at L2, 95.5% →
9.8% at L3. Those constraints were never semantically vague; they were fragments the rule parser had
cut mid-phrase, and boundary repair restores them to verbatim-matchable form. **Damaged is not
vague**, and this benchmark contains only the former.

On the ~38% of L2 turns where routing still fires correctly, the semantic term *loses* 0.0035. The
within-pool cosine spread is 0.038 across ~115 candidates, so after normalisation it amplifies
near-ties rather than separating anything. That is the honest ceiling of semantic retrieval here —
a property of a benchmark whose simulated customer quotes product copy verbatim, not a property of
semantic retrieval. A shopper asking for something "flattering" gives no string to extract, and
nothing but semantics can move toward them.

**So the LLM is used to listen, not to rank.** The ranking path stays off by default (`USE_LLM=0`).
The parsing path ships on (`LLM_PARSE=1`) and makes zero calls on unmodified phrasing, so the
headline number is produced without it. Model: `deepseek-v4-flash`, swappable via `LLM_BASE_URL` /
`LLM_MODEL`; any OpenAI-compatible endpoint works, and none at all is also a valid configuration.
Full latency/token/cost numbers: [`COST_AND_LATENCY.md`](COST_AND_LATENCY.md).

## 6. The question policy: we bounded the dimension instead of arguing about it

The brief asks the agent to "ask a useful question when important information is missing", and adds
the criterion that separates a strong agent from a talkative one — it should ask "only when the
expected value of the answer is high". We took that literally and measured the expected value.

`customer_reply()` decides what a question earns. `other` short-circuits the constraint filter and
matches *any* undisclosed constraint, returning up to two per turn. A named attribute matches only
constraints whose `classify_constraint()` label is equal, and may return zero. `classify_constraint()`
can never emit `category` or `brand`, so those two questions are guaranteed to earn nothing. Asking
is free — a turn can both ask and recommend — and a hit ends the session immediately.

Under those rules the greedy optimum is to ask `other` every turn, and we can price the alternative.
Replacing it with an entropy policy that picks the highest-information attribute from the live
candidate set costs **-0.0252** (0.9442 vs 0.9694, measured with every other setting held fixed at
the then-shipped configuration). HitRate is 1.000 in both; what changes is that
81 of 200 sessions hit *later* and 14 finish at a worse rank. The information a named question buys
is real, but smaller than the turn it spends.

We then bounded the dimension exhaustively rather than trusting that argument. Enumerating the best
possible question sequence per session — an oracle with knowledge of the hidden card — the entire
ask dimension is worth **+0.00385** over constant `other`, and that ceiling is reachable only by
memorising the public split. Every generalisable single-policy variant we measured is negative:
material-first -0.0029, feature-first -0.0023, colour-first -0.0075. **Constant `other` is the
argmax of the generalisable policy family, and the headroom above it is 0.004 held by an oracle.**

This is a property of the simulator, not a claim about shopping. A real shopper answers "anything
else?" with silence, not with two more constraints; under that reply distribution the same
expected-value framing selects named questions instead. The entropy policy therefore ships with the
agent rather than being deleted, and we report its cost here rather than hiding a constant behind it.

## 7. Method: how we decided what to keep

Three rules, adopted after the first over-fitting scare and applied to every change since:

**Stop where all three difficulty buckets improve together.** The popularity prior kept raising the
score up to weight 6 — monotone improvement with no plateau is an over-fitting alarm, not a win. At
weight 2.0 easy/medium/hard all improved; at 3.0 easy rose while medium fell. We stopped at 2.0 and
left 0.008 on the table. Removing early-turn withholding moved that optimum: with all ten
recommendations now scored, our re-scan landed on **`POP_WEIGHT=2.75` with
`HAS_PRICE_WEIGHT=0.95`** — and scanning the neighbourhood afterwards showed the peak is one grid
point wide: 0.9466 against 0.9457 at 2.8, a margin of +0.0009, which is exactly what the next
paragraph calls noise, and an advantage that does not survive paraphrase stress. We therefore report
2.75 as where our grid landed rather than as a value the stopping rule selected, and note that
anything in 2.5–3.0 is the same system (the range spans 0.0035). `HAS_PRICE_WEIGHT=0.95` is a
different case and we do claim it: it beats 1.0 by 0.0025, above the threshold.

**Convert small gains into "how many sessions is that?"** With 200 samples one session is worth
0.0007–0.0025. A tuning result of +0.0009 is one session flipping — indistinguishable from noise. We
rejected three such "improvements".

**Every assumption gets a failure simulation.** Three implementations of the withholding rule scored
identically on the public set; only by simulating parser failure did we find that one of them
degrades catastrophically (HitRate 0.950) while another exits safely. Public-set parity is not
evidence of equivalence.

We also disproved things and kept the records: profile-based soft preferences (permutation test:
1.021×, p≈0.18 — the apparent 1.745× lift was a text-length artefact), dense similarity as a
tie-breaker, feature-count priors, and prior-weight decay.

**We then proved our own ceiling — and re-proved it after changing the default.** In the shipped
configuration 38 of 200 sessions are not ranked first. A session-by-session comparison against the
withholding configuration separates them cleanly: **7** are imperfectly ranked under both and are
*information-theoretically indistinguishable* — the target shares an identical intent card and
category with other catalogue items, so the generated dialogue is byte-identical (one target has 46
such twins). The other **31** are precisely the sessions withholding used to rescue: the same 31
identified in §1, and the measured price of showing ten products instead of one. Against the
withholding configuration the reachable MRR gain beyond those 7 was 0.00075, below our own noise
threshold; further tuning there would buy noise and pay for it in private-set generalisation.

## 8. Reproduction

```bash
python3 scripts/prepare_catalog.py        # verify SHA-256, extract catalogue (once)
python3 -m evaluator.local_evaluator      # 0.9466 — standard library only, ~10 s
python3 scripts/check_guards.py           # red-line self-check + 30 unit tests
python3 scripts/parser_accuracy.py        # parser accuracy in isolation
python3 scripts/paraphrase_stress.py      # robustness across 5 stress levels
python3 scripts/ceiling_diagnostic.py     # remaining headroom, decomposed
```

Python 3.10+. The base path requires no third-party packages; `requirements.txt` applies only to the
optional dense route (`USE_DENSE=1`), which degrades to pure BM25 when assets are absent.

## 9. Limitations

1. **Public-set saturation is not private-set safety.** HitRate is 1.000 on 200 public sessions; the
   private 800 use different users and targets. Our best proxy is the paraphrase stress table in §4:
   with the shipped configuration the curve runs 0.9466 → 0.9168 across five rewrite levels, so we
   expect roughly **0.92–0.95** if paraphrasing is applied *and* the parsing layer has network
   access. Without that access the same curve floors at 0.827. We have no way to narrow this
   further — the levels are our own mechanical rewriter, not evidence about the private split.
2. **The `other`-only question policy is specific to this simulator.** §6 bounds it rather than
   defending it: the whole ask dimension is worth +0.00385 to an oracle holding the hidden card,
   every generalisable named-attribute policy we measured is negative, and the entropy alternative
   costs -0.0252. We disclose this rather than presenting a constant as a strategy, and the entropy
   policy ships behind a flag for the reply distribution a real shopper would produce.
3. **The dense route ships disabled (`USE_DENSE=0`), and we now know why rather than suspecting
   it.** Early measurements made it look like a free robustness win: +0.0016 on the unmodified
   public set, +0.011 to +0.020 under paraphrase stress. Both were taken while early-turn
   withholding was still on, and that mechanism was masking the cost. With withholding removed the
   sign flips at L0 to **-0.0090**. Instrumentation explains it without appealing to noise:
   dense-only candidates enter with a sentinel BM25 rank and therefore a ~1.0-point handicap, so
   they never displace anything — what they do is *add recall*, which surfaces the target one turn
   earlier at a mediocre rank, and stop-on-hit locks that rank in. At L0, 17 of 18 changed sessions
   hit earlier, 11 of them at a worse rank, and none were rescued from a miss; at L2 the identical
   behaviour lands on sessions that would otherwise never hit — four outright rescues — so it earns
   there instead. One mechanism, two counterfactuals. Once `LLM_PARSE=1` repairs the upstream parse
   the L2 counterfactual reverts to the L0 one, and dense loses at every tier (-0.0065 to -0.0106).
   We keep the code and the flag: the route is correct engineering for a customer who does not quote
   product copy, and §5 records exactly what it is worth here and why.
   Its cost is asymmetric in a way the score does not show: peak RSS rises from 530 MB to 1191 MB
   on the torch backend, 787 MB on ONNX, against a memory ceiling the organiser reserves the
   right to impose and never states. Missing assets degrade gracefully to pure BM25; an OOM kill
   does not degrade at all.
4. **Our benchmark-shaped mechanisms: we removed the large one and kept the small one behind a
   flag.** Withholding all but one recommendation on early turns was worth **+0.0286** and is the
   opposite of what a storefront should do, so it is no longer the default (`EARLY_TOPK=0`).
   Removing it costs nothing in reach — HitRate is unchanged at every paraphrase tier and MTTC
   improves from 2.155 to 1.920. The entire cost falls on MRR, which is to say on ranking precision
   the trick had been buying by declining to show candidates. What we kept is the principle
   underneath it, moved to where a real product would also want it: under stop-on-hit, surfacing a
   mediocre candidate early is worse than surfacing the right one a turn later, so the retrieval
   side gates *when to introduce semantic candidates* instead of the display side hiding what it
   already has (§5). The intent-card mirror bonus remains, worth +0.003 and disabled by
   `MIRROR_BONUS=0`; it has a production analogue we did not have room to build — a constraint
   matching a product's *salient* attributes (title, structured specs, leading feature bullets) is
   stronger evidence than one matching a phrase buried in paragraph eight of a description. What
   remains underneath is the conventional commercial shape: keyword plus phrase retrieval,
   non-displacing candidate union, and independent re-ranking over match evidence, category and
   purchase-likelihood features.
5. **Our ranker is a hand-weighted linear scorer.** With behavioural data at commercial scale the
   natural successor is a learned ranker — LambdaMART or gradient-boosted trees over the same
   features, plus a cross-encoder over the low-confidence tail. With 200 labelled sessions, learning
   the weights would mean learning the public set; hand weights plus an explicit stopping rule are
   the more honest instrument at this data volume. We regard this as a data-regime decision, not an
   architectural preference, and it is the first thing we would change given real traffic.
6. **Latency was measured on one machine** (Apple M5). Absolute numbers will differ; the ~106× ratio
   between offline and LLM paths should not.

7. **The parsing model is an enhancement, not a dependency, and we declare it as such.**
   `LLM_PARSE=1` is the default. On unmodified phrasing it makes **zero calls** — `llm_calls = 0`
   across all 200 public sessions, score bit-identical to the rule-only path — and wakes only where
   the rule layers fail, which is where it is worth +0.036 / +0.060 / +0.098 at L2 / L3 / L4 and
   restores HitRate to 1.000 at L3. Without network access or credentials it degrades to the
   rule-only path after two consecutive failures, so in a network-restricted scoring environment the
   headline number is unchanged. During measurement the worst observed case was a single call
   reaching the then-45 s timeout and succeeding on retry; the parsing layer has since been given its
   own shorter budget (`LLM_PARSE_TIMEOUT=12`, against a measured p95 of 1.0–5.6 s), capping its
   worst case at two attempts of 12 s rather than two of 45 s.

## 10. Team contributions

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

> **Zhou Junkai (B):** My dense route never made it into the default path, and that is fine — its
> real job turned out to be diagnostic, not additive. It proved Recall@pool was already 1.000, so
> nothing downstream could gain from more candidates; and under paraphrase stress it showed where
> robustness actually lives: +0.011 to +0.020 at L1-L3, nothing at L4, because L4 breaks in the
> parser, not the index. We ship it off, one environment variable away, with the numbers on the
> table instead of hidden.

> **Lin Xiaoxiao (C):** The gain I am least proud of is the one that moved the score most. It did
> not come from a better method — it came from noticing we had been asking the wrong question:
> not *which product matches this sentence*, but *which product a real person actually bought*.
> Two columns nobody had used answered it. What I would rather be judged on is what happened next.
> The score kept rising as I pushed that weight higher, which is exactly what over-fitting looks
> like, so we wrote down a stopping rule and left measurable points on the table. Then I built the
> harness that measures the one risk the public set cannot show us, and finally proved our own
> ceiling — seven of our imperfectly ranked sessions are provably unwinnable. Along the way my
> teammates caught a chart whose bars overlapped and a decision threshold with a hole in the
> middle. Both corrections are in the log, next to the results.

> **Chen Zhilong (A):** I built the first working version, and the most useful thing I can say about
> it is that it was wrong in ways the score did not show me. My override handling had a logic bug
> that the public set was too forgiving to expose; two batches of tests I wrote were never executed
> at all because I wrote them in the wrong style, and a teammate's guard caught the second batch
> within hours of the first. The pattern in all three is the same: the end-to-end number is a
> comfortable instrument, and comfortable instruments hide defects in the layer furthest upstream.
> That is why I proposed scoring the parser on its own — if parsing drops a constraint, nothing
> downstream can win it back, no matter how good the ranking is. The metric found two real defects
> in my own code within an hour of existing, and fixing them lifted our hardest robustness level by
> 0.02. I would rather be judged on that loop than on the prototype.

---

*Evidence for every number in this report: [`team/experiments.md`](team/experiments.md) (66 logged
experiments, including the ones we rejected), [`COST_AND_LATENCY.md`](COST_AND_LATENCY.md),
and the four module handover documents under `team/`.*
