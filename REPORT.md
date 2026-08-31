# NiuLai — Conversational E-Commerce Search Agent

**TikTok TechJam 2026 · Track 4** · Team NiuLai · Final report

# 0. Summary

**Public-set TechnicalScore 0.9466** — HitRate@10 **1.000**, MRR 0.884, MTTC 1.935 — against the
official weak-BM25 baseline of 0.107. The submitted path uses the Python standard library only: 200
sessions evaluate in **9.7 seconds**, and the headline number is bit-identical with the network
removed.

| Scenario | n | HitRate@10 | MRR | MTTC |
|---|---|---|---|---|
| Buying | 80 | **1.000** | 0.880 | 1.413 |
| Browsing | 80 | **1.000** | 0.839 | 1.750 |
| Intent Override | 30 | **1.000** | 0.978 | 3.600 |
| Boundary | 10 | **1.000** | 1.000 | 2.600 |
| **All** | **200** | **1.000** | **0.884** | **1.935** |

Three decisions shaped this report more than the score did. We read the evaluator before writing the
agent, and what we found there overrode our initial plan (§1). We removed our single largest
benchmark-shaped mechanism after measuring exactly what it was worth — it cost us 0.0244 and we
shipped without it anyway (§5). And we give the things we disproved the same space as the things we
kept, because the negative results are what told us where not to spend the remaining hours (§10).

**Where to look, if you are short of time.** The seven technical chapters, **§3 to §9**, each open
with the question they answer and close with their net effect; those two lines are enough to skip
any of them safely. §1 and §2 are context and configuration; §10 to §13 are method, limitations,
contributions and reproduction. If you read only three: **§3** is how the system survives a customer
who does not phrase things the way the benchmark does, **§5** is the idea that moved the score most,
and **§9** is what of this survives outside the benchmark. **§7** carries the required cost, latency
and token disclosure; **§11** carries the limitations, including the one place we knowingly left
measurable score on the table.


---

# 1. What we read first, and why it decided everything after

Before writing an agent we read the evaluator's source. Three facts from it determined the whole
architecture, and each one contradicted the plan we had walked in with.

**The simulated customer never reads our prose.** `customer_reply()` takes `ask_attribute` — a
single value from a ten-item enum — and nothing else. The `message` field is only type-checked
(`local_evaluator.py:243`). Our entire channel to the customer is **≈3.3 bits per turn**. No amount
of prompt craft can change what the customer says next. This is why our clarification copy is
written for human judges and for the demo rather than tuned for score, and why we say so instead of
presenting it as a modelling achievement.

**The customer's utterances are a deterministic function of the target product.** The hidden intent
card is generated at evaluation time by `intent_card()` from the target's own catalogue metadata,
and the constraint strings the customer speaks are *verbatim fragments of that product's text*.
Verbatim substring matching against the catalogue is therefore close to a fingerprint, and it became
the strongest single feature in our ranker. Almost every later decision in this report — which
retrieval route to trust (§4), where semantics can and cannot pay (§7), why our parser validates
against the catalogue rather than against a grammar (§3) — follows from this one property.

**A hit ends the session immediately, and locks in that turn's rank.** Hitting at turn 1 in position
7 is worth 0.743 for that session; hitting at turn 2 in position 1 is worth 0.980. Being *earlier*
is not automatically better — being earlier at a mediocre rank is a trade the metric punishes. We
found **31 sessions** sitting in exactly that losing state, and they reappear three times in this
report: as the motivation for a mechanism (§5), as the measured price of removing it (§5), and as
the reason the dense route changes sign (§4).

The first fact bounds what conversation can achieve here. The second says where the signal is. The
third says that *when* we show a candidate matters as much as *which* one. None of the three is
inferable from the problem statement; all three are visible in forty minutes of reading the
evaluator.

---

# 2. Architecture, configuration, and one session end to end

```
respond() ─→ M1 dialogue control ─→ M2 retrieval ─→ M3 ranking ─→ message + ask_attribute + top-10
             parser + slot state    BM25 + phrase    rule scorer
             machine, 3-layer        recall (+ opt.  (LLM re-rank
             parsing defence         dense route)     optional, off)
```

**M1 — dialogue control (§3).** A slot state machine over the constraints the customer has
disclosed, fed by a three-layer parsing defence. Question policy is a constant: always ask `other`.
We did not settle for arguing that this is optimal — we bounded the entire ask dimension
exhaustively and report both the bound and what the alternative costs.

**M2 — retrieval (§4).** SQLite FTS5 keyword search with field weighting, per-constraint phrase
recall for slots of three tokens or more, and an optional pre-computed dense route fused as a
non-displacing union. Recall@pool reached **1.000**, which is why retrieval stops being the subject
of this report early and starts being a constraint on everything downstream.

**M3 — ranking (§5).** An offline rule scorer over weighted verbatim constraint hits, an intent-card
mirror bonus, category match, purchase-likelihood priors and normalised BM25 rank. This is the
default and only scoring path.

> **Network access — the declaration `submission_rules.md` asks for.**
> The submitted configuration **requires no network access and no credentials**. One model-backed
> path ships enabled (`LLM_PARSE=1`), but on unmodified phrasing it makes **zero calls**
> (`llm_calls = 0` across all 200 public sessions) and the score is bit-identical to the rule-only
> path. Without connectivity or a key it trips a breaker after two consecutive failures and falls
> back to rules, so in a network-restricted scoring environment the headline number does not move.
> It is an enhancement, not a dependency. Full cost and latency figures: `COST_AND_LATENCY.md`.

**Shipped defaults.** Every mechanism in this report is a flag, and every flag is documented here so
that any claim we make can be switched off and re-measured:

| Flag | Shipped | Effect |
|---|---|---|
| `ASK_POLICY` | `other_first` | Constant `other` question; `entropy` selects the highest-information attribute instead (§3) |
| `LLM_PARSE` | `1` | Third parsing layer; zero calls on unmodified phrasing (§3) |
| `USE_LLM` | `0` | LLM listwise re-ranking; measured at parity, 106× slower (§7) |
| `USE_DENSE` | `0` | Dense retrieval route; negative in this configuration (§4) |
| `EARLY_TOPK` | `0` | Early-turn withholding, **removed from the default**; `1` restores it and scores 0.9710 (§5) |
| `MIRROR_BONUS` | `1.0` | Intent-card mirror bonus; `0` disables it (§9) |
| `PHRASE_RECALL` | `1` | Per-constraint phrase sub-pool (§4) |
| `POP_WEIGHT` / `HAS_PRICE_WEIGHT` | `2.75` / `0.95` | The two purchase-likelihood priors (§5) |

`LLM_PARSE_TIMEOUT=12`, `CANDIDATE_POOL=300`, `PHRASE_TOP_K=50` and the remaining knobs are
documented in `src/config.py` next to the experiment that set them.

**One session, end to end** (`public_0002`, Intent Override; target `B071X54486`, a full-grain
leather belt; reproduce with `python3 scripts/trace_session.py --id public_0002`):

```
turn 1   customer  "I'm looking for Accessories Belts. Buckle closure"
         agent     one soft slot; asks `other`; returns ten — target not among them
turn 2   customer  "For that, what matters is: leather; 100% Leather."
         agent     two hard slots registered; target enters at rank 1.
                   The protocol forbids an override session converting before the pivot
                   arrives, so the session continues rather than ending here.
turn 3   customer  "Actually, ignore my earlier preference. What I need is: leather."
         agent     "Understood — let's prioritise leather instead."
                   Earlier slots are demoted to soft, not erased; target held at rank 1.
         → hit at turn 3, rank 1, RR = 1.000
```

Turn 3 is the whole of §3 in miniature: the override is recognised, the named constraint is promoted
to hard, and the constraints the customer disclosed *before* changing their mind are kept as soft
evidence rather than thrown away. Erasing them instead costs HitRate 0.667 on this scenario.

---

# 3. The dialogue layer: nothing downstream can win back a constraint the parser dropped

**The question this chapter answers:** how do we turn the customer's raw sentences into the
structured state the retrieval and ranking layers consume — and what happens when those sentences
stop looking the way we expect?

**State, not scenario.** We keep a slot state machine: each disclosed constraint becomes a `Slot`
carrying its verbatim value, a hard/soft flag, the turn it arrived, and a normalised list of search
terms. Everything downstream reads slots. This is a deliberate alternative to routing by scenario,
and it is worth being precise about what we did and did not build.

**On Buying/Browsing routing.** The four scenarios *are* recognised and recorded in the dialogue
state, and two of them change behaviour: an override demotes earlier constraints rather than erasing
them (the trace in §2; erasing scores HitRate 0.667), and a boundary refusal does not mark the
attribute as exhausted, so it can be asked again later. But Buying and Browsing are **deliberately
not branched**. The only difference between them is how many constraints are already on the table at
turn 1, and the prior axis (§5) is precisely the mechanism for a turn with no constraints at all.
The per-scenario numbers in §0 are the acceptance test for that choice: **HitRate is 1.000 in all
four**, and the MRR spread orders itself by how many constraints the customer has disclosed
(Override 0.978 > Buying 0.880 > Browsing 0.839), not by scenario label. A real storefront needs the
branch, because there the two modes optimise different objectives; this simulator collapses them,
because its browsing sessions still have a single hidden target and a customer who quotes catalogue
text on request. §9 says what we would build instead.

**Three layers, each firing only when the previous one fails.** Layer 1 matches the evaluator's
exact sentence templates. Layer 2 is rule-based salvage — colon payloads, separators, override cues,
category extraction — and is constructed so it *cannot* fire when Layer 1 matched, which makes it
byte-for-byte inert on the public set. Layer 3 asks a model to extract fragments, and anything it
returns must survive a **verbatim check**: normalised, it has to be a contiguous substring of the
original message, or it is discarded. Fingerprint evidence outranks the model's linguistic taste.

**Weighing the parser on its own scale.** End-to-end score is a poor instrument for a parsing
defect: it mixes parsing with retrieval and ranking, and a dropped constraint often costs a fraction
of a rank rather than a session. So we scored the parser in isolation against ground-truth
constraint strings (`scripts/parser_accuracy.py`, 450 messages × 5 stress levels × 2 arms):

| | L0 | L1 phrasing | L4 colon-free |
|---|---|---|---|
| Verbatim recall, rules only | 98.8% | 95.2% | 0% |
| Verbatim recall, + Layer 3 | 98.8% | 95.2% | **76.0%** |
| Partial recall, + Layer 3 | 100% | 99.5% | **97.8%** |

The metric paid for itself within an hour by exposing two defects that end-to-end score had absorbed
silently. Constraint values containing their own colon (`Department: womens`, roughly one in eight)
were being cut apart by a last-colon rule, capping L1 verbatim recall at 76%. And a garbage
extraction could *succeed confidently* — returning fragments padded with conversational filler —
which shut Layer 3 out precisely when it was needed most. That is the failure mode a cascade has and
a parallel ensemble does not, and we state it rather than claiming the architecture is free of
trade-offs.

Both were fixed by the same first principle that produces the fingerprint signal: a genuine
constraint must occur verbatim in *some* product's catalogue text. The retriever answers that in
under a millisecond, so the parser now proposes two colon candidates and keeps the one the catalogue
verifies; an extraction that verifies nothing is not treated as success, and Layer 3 fires. L1
verbatim recall moved 76.2% → 95.2% and L4 partial recall 77.0% → 97.8%, with the public set
byte-identical session by session.

It also had an effect we did not anticipate. Before the fix, Layer 2 reported success on paraphrased
input even when the fragments it returned were damaged, so Layer 3 never ran there and the model's
contribution was invisible outside the hardest level. With the catalogue verifier deciding what
counts as success, the model engages wherever the rules genuinely failed, and the whole robustness
curve moves (§8). The lesson generalises past this system: **a cascade whose early stages cannot
recognise their own failure will silently starve the stages behind them, and that deficit is
invisible to end-to-end score.**

**The question policy: we bounded the dimension instead of arguing about it.** The brief asks the
agent to ask a useful question only when the expected value of the answer is high, so we priced it.
`other` short-circuits the constraint filter and matches *any* undisclosed constraint, returning up
to two per turn; a named attribute matches only constraints whose `classify_constraint()` label is
equal and may return zero; `classify_constraint()` can never emit `category` or `brand`, so those
two questions are guaranteed to earn nothing. Asking is free — a turn can both ask and recommend.
Under those rules constant `other` is the greedy optimum, and we can price the alternative: an
entropy policy that picks the highest-information attribute from the live candidate set costs
**−0.0252** (0.9442 against 0.9694, every other setting held at the then-shipped configuration;
HitRate 1.000 in both — 81 of 200 sessions simply hit later). Enumerating the best possible question
sequence per session — an oracle holding the hidden card — the entire ask dimension is worth
**+0.00385**, reachable only by memorising the public split, and every generalisable single-policy
variant we measured is negative (material-first −0.0029, feature-first −0.0023, colour-first
−0.0075). **Constant `other` is the argmax of the generalisable policy family, and the headroom
above it is 0.004 held by an oracle.** This is a property of the simulator, not a claim about
shopping: a real shopper answers "anything else?" with silence, and under that reply distribution
the same expected-value framing selects named questions instead. The entropy policy therefore ships
behind a flag rather than being deleted.

**Net effect of this chapter.** The parsing defence is worth nothing on the scored split by
construction and everything under paraphrase (+0.012 to +0.090, §8); the question policy is worth at
most 0.004 to an oracle and we spend no further effort on it. Both conclusions come from measuring
the layer in isolation rather than from the end-to-end number, which is the only reason we found the
two parser defects at all.

---

# 4. Retrieval: prove recall is not the bottleneck before reaching for semantics

## The question this chapter answers

Is the target product even inside the candidate pool — and if it always is, what is left for
semantic retrieval to do?

## 1. Retrieval stopped being the bottleneck — and we proved it

Recall@pool is **1.000**: across all 200 sessions, the product the simulated customer will
eventually buy is always inside the 300-candidate pool before any ranking happens (exp 6b). This is
not a boast; it is a premise, and several later negative results stand on it. Once the pool provably
contains the target, no downstream idea of the form *"add more candidates"* can help — profile-based
recall injection, LLM-suggested queries, and dense candidates all died on exactly this fact.
Measuring recall first is what let us spend the rest of the project on the problems that were
actually losing points.

## 2. What the keyword route actually does

The main route is SQLite FTS5 keyword search with field weighting, plus two mechanisms aimed at the
pool's edge cases. Slots with three or more tokens issue per-constraint FTS5 *phrase* queries
alongside the main OR-token pool, and BM25 ranks are normalised within each sub-pool before merging.
The phrase sub-pool exists because of one instructive failure: `public_0020`, an ultra-cold target
whose constraints were all boilerplate, could never climb into the top-300 of the token pool — its
phrase query, against a pool of almost nothing, brought it back. That was the session that took
HitRate to 1.000 for the first time (exp 22, the phrase-recall entry — the number is used twice in
experiments.md).

## 3. The dense route: one mechanism, two counterfactuals

We still built the semantic route — precomputed bge-small-en-v1.5 embeddings fused as a
non-displacing union with sentinel ranks — and then instrumented it to see what it actually does
(exp 38). It only ever adds recall; it never displaces a keyword candidate. But the same behaviour
has two counterfactual outcomes depending on where it lands. On the unmodified public set it
advances 17 sessions to an earlier hit while worsening the final rank of 11 — a net **−0.0090** (exp
37): "one turn earlier" cannot compensate for "not rank 1". Under stress level L2 the identical
behaviour lands on sessions that would *never* have hit at all and rescues 4 of them — a net
**+0.0149**. The sign flip is not the dense route changing; it is the removal of early-turn
withholding (exp 37), which had been masking the harm channel all along. Under the old withholding
configuration the same mechanism had read +0.0016 on the public set (exp 28, historical
configuration) — the masking, measured.

## 4. We ship it off, and the reason is expected value, not magnitude

The decision to ship with `USE_DENSE=0` was not about the size of the gain but the shape of the loss
(exp 31). The route's degradation path covers missing assets and missing dependencies — a missing
embedding file falls back to pure BM25 gracefully, and we verified the whole pipeline bit-identical
with the network physically off (exp 29). It does not cover OOM: a memory-limit kill does not
degrade, it zeroes the run. Against a conditional gain of about +0.015 (paid only if the private set
is paraphrased at all) stands a loss of ≈ −1.0, so the break-even is P(OOM) < 1.5% — and the
organiser reserves memory limits without naming them. One honest footnote (exp 31a): our 530 MB
baseline already sits on the same exposure curve, since a limit tight enough to kill the route's 787
MB ONNX peak (1,191 MB on PyTorch) would likely threaten 530 MB too. Shipping off moves the point
left on that curve; it does not leave it.

## Net effect

Retrieval contributes a candidate pool that provably always contains the target, at zero marginal
runtime risk; the dense route is kept, measured from both directions, and deliberately switched off
(exp 6b, 22 [phrase recall], 28, 29, 31, 37, 38).

---

# 5. Ranking: a prior axis alongside the relevance axis

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
optimum, because all ten recommendations now score, so we re-swept (exp 39/43): 2.7 → 0.9453, **2.75
→ 0.9466**, 2.8 → 0.9457, 3.0 → 0.9444.

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
thirty-one from §1, and the measured price of §3. Beyond those seven the reachable MRR gain was
0.00075, below our own noise threshold (exp 27).

**Net effect:** the prior axis is worth 0.074, the largest single gain in the project — and it came
not from a better method but from noticing we had asked the wrong question. The ceiling above it is
seven sessions wide and provably closed.

---

# 6. Safe personalisation: a negative result on a direction the brief named

**The question this chapter answers:** the brief names "safe personalization using the aggregate
profile" as an innovation direction. We built it. What did it turn out to be worth, and how do we
know?

**What we built.** The evaluator hands us a five-key `user_profile` at `reset()`, before the
customer has said anything — the only signal available for a cold start. We parsed it into a
soft-preference lexicon (`preference_tags` is a closed set of nine values, verified across all 200
public sessions) and added two cross-turn signals: a stagnation counter and a record of previously
shown candidates. A context distiller compresses session state into one bounded line per turn, its
turn-10 output **0.80×** its turn-3 length (exp 22) — the state converges rather than accumulating.

**The first number looked like signal.** Profile keywords occur in the target listing 1.745× more
often than in a random listing (exp 22).

**It was a confound.** Target products come from real purchase records, so they are systematically
the popular ones — the same skew that makes the prior axis work in §5, where targets carry 570× the
median review count. Popular products have longer listings, so *any* word hits them more often. The
lift was measuring listing length, not relevance.

**The permutation test.** Holding the targets fixed and shuffling only which profile pairs with
which session — identical items, identical listing lengths, only the pairing destroyed — the ratio
falls to **1.021×** (z = +0.93, p ≈ 0.18, 200 permutations, exp 22): a 2% effect we cannot
distinguish from zero.

**Stated as information rather than implementation:** the ceiling on this feature is not set by how
we wire it, weight it or gate it — it is set by information content, and this data does not carry
it. That retired an entire class of follow-up work in one measurement — cold-start-only application,
retrieval-only, ranking-only, weight sweeps, per-tag gating — each of which would otherwise have
cost a wiring and a full evaluation to falsify alone. The time saved exceeds anything the feature
could plausibly have scored.

Two same-batch negatives agree: `rating_style` does not predict the target's average rating (4.41 /
4.28 / 4.31, exp 22), and the apparent tag-to-category skews are small-count noise across 112
categories over 200 sessions.

**Where the code went.** `lexicon.py` and `signals.py` remain in the repository under 12 unit tests,
deliberately disconnected from the scoring path. The one signal we did offer the ranker,
`actionable_rejections`, measured as exactly zero when wired in (exp 18): with HitRate at 0.995 and
MTTC at 2.23, almost every session ended before a stagnation signal could accumulate.

**Net effect: 0.0000 on TechnicalScore, by decision rather than by omission.** What generalises is
the entry criterion, and it needs data this benchmark does not have — purchase sequences and
browsing behaviour rather than an aggregate tag set. §9 takes that up.

---

# 7. Model choice, cost, latency and tokens

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

# 8. Robustness: the risk we could not measure, so we built a way to measure it

**The question this chapter answers:** the public set is saturated at HitRate 1.000. What evidence
do we have that the private split will not collapse?

The specification reserves the right to add natural-language paraphrasing to the simulator. Our
entire pipeline rests on verbatim matching (§1), and the public set — with its fixed sentence
templates — can never reveal that exposure. So we built the instrument ourselves: a paraphrase
stress harness (`scripts/paraphrase_stress.py`) that wraps the Agent and rewrites the customer's
utterances before the Agent sees them, **without modifying the evaluator**. Five graded levels
isolate different failure modes.

The first result was counter-intuitive and redirected the whole robustness effort:

> Changing only the *sentence templates*, leaving every constraint string verbatim, cost **−0.183** —
> 87% of the total damage. Changing the constraint values themselves cost only 0.028 more.

The fragility was in template matching, not in verbatim matching. That reframed the fix from
"understand meaning" to "extract fragments from unfamiliar sentences" — which, as §3 shows, needs no
model at all for four levels out of five.

| Parsing stack | L0 | L1 phrasing | L2 + short values | L3 + spec strings | L4 colon-free |
|---|---|---|---|---|---|
| Layer 1 only † | 0.9620 | 0.7792 | 0.7585 | 0.7523 | — |
| + Layer 2 (offline path) | 0.9466 | 0.9259 | 0.8914 | 0.8765 | 0.8269 |
| **+ Layer 3** (`LLM_PARSE=1`, shipped default) | **0.9466** | **0.9374** | **0.9230** | **0.9311** | **0.9168** |

† Measured against the pre-08-31 ranking configuration (`EARLY_TOPK=1`, `POP_WEIGHT=2.0`). Rule
salvage has no runtime switch, so it could not be re-measured under the shipped weights without
editing code, which our stop rule forbids for measurement alone. The row is kept for its *shape* —
template changes alone cost −0.183 — not for its absolute value.

Two readings of that table are worth stating explicitly. **L3 scores above L2 once Layer 3 is on**:
L3 rewrites long specification strings and pushes more turns into the model layer, whose verbatim
extraction is cleaner than the rule layer's whole-sentence fallback, while L2's half-damaged values
more often slip past the rule layer's own validation and never reach it. The curve is no longer
monotonic in rewrite severity, and we would rather report that than smooth it. And **the offline row
is the floor that matters for scoring**: if the organiser disables the network, the shipped agent is
that middle row, bottoming at 0.8269.

What this table is *not* is evidence about the private split. The levels come from a mechanical
rewriter we wrote ourselves; they isolate which layer breaks first, which is exactly what we needed
in order to know where to spend the last day, but they are not a sample from the private
distribution. §11 states the range we expect and why we cannot narrow it.

**Net effect.** The harness did not raise the headline number by a single point. It told us that our
weakest layer was the parser rather than the index, which is why §3 exists in the form it does and
why the dense route (§4) was never going to be the answer.

---

# 9. From benchmark to a real storefront

**The question this chapter answers:** with the evaluator taken away, which parts of this system
survive, which are scaffolding, and what would replace them?

**The benchmark-shaped mechanisms unload with a flag — and one of them is already unloaded.** The
shipped default runs with `EARLY_TOPK=0`: we withdrew early-turn withholding before submission, on a
product judgement rather than a score one, paying −0.0244 entirely out of MRR while HitRate held at
1.000 across all five stress levels. That leaves the intent-card mirror bonus as the only mechanism
in the shipped default with no real-world counterpart. Removing it costs **−0.0031** (0.946642 →
0.943581) with **HitRate unchanged at 1.000 and MTTC unchanged at 1.935** (exp 43). Measured earlier
with withholding still enabled, the full unload was 0.9694 → 0.9383, again at HitRate 1.000 in both
configurations (exp 30, benchmark-configuration figures — not comparable with the shipped default).
The claim is not that we avoided benchmark-specific optimisation; it is that it detaches cleanly,
and that coverage does not depend on it.

| Mechanism | Why it holds in this benchmark | In a real storefront | Keep / replace |
|---|---|---|---|
| Verbatim substring match | The customer's constraints are copied verbatim from the target's own listing | Real shoppers do not quote product copy | **Replace as primary.** Demote to one recall signal among several; the semantic route becomes the main path |
| Intent-card mirror bonus | The intent card is an artefact of the evaluator | No counterpart exists | **Replace** with attribute salience — a match in the title, a structured field or the first bullet weighs more than one in the eighth paragraph of a description |
| Constant `other` question | The simulator discloses up to two constraints per turn and `other` matches any of them | A real shopper asked "anything else?" every turn simply stops replying | **Replace** with expected information gain traded against a patience cost |
| Stop-on-hit | Defined by the evaluation protocol | Add-to-basket or checkout | **Keep.** The objective has the same shape — early and accurate — so the ranking policy transfers unchanged |
| Hand-weighted linear scorer | 200 labelled sessions; learning the weights would mean learning the public set | Real behavioural data at volume | **Replace** with LambdaMART or GBDT, with a cross-encoder on the low-confidence tail |
| Aggregate profile | Carries **no information** about the target (§6) | Purchase sequences and browsing behaviour exist and are genuinely predictive | **Rebuild on different data.** Aggregate tags are the wrong object; sequences are the right one, and they bring a privacy boundary with them |
| Buying / Browsing routing | The simulator collapses browsing into buying: one target, verbatim constraints, stop-on-hit | The two modes optimise different things — precision@1 versus information gain and diversity | **Add.** A continuous `intent_confidence` rather than a branch, diversity re-ranking (MMR/DPP), and expected-information-gain questioning |

The last two rows are where our own evidence is strongest and weakest respectively. On the profile
row we are not speculating: the permutation test says what is missing and therefore what would have
to be present. On the routing row we should be explicit that we did not build a router —
`state.scenario` is populated but never read by retrieval or ranking, so buying and browsing take
one identical path. Both halves of a router already exist in the repository: the prior axis is a
browsing ranker, and `ASK_POLICY=entropy` is a browsing questioner. The latter costs −0.0252 here
(exp 35) precisely because there is no real browsing to serve.

**Engineering budget.** 50k SKUs in SQLite FTS5 answer in 2.3 ms median per turn (p95 2.8 ms); at
tens of millions this becomes an ANN index and the latency budget changes shape. The offline path
holds a 530 MB resident set and starts in 4.1–6.9 s; enabling the dense route takes that to 1191 MB
on torch, or 787 MB on an ONNX backend. LLM parsing runs at p95 1.0–5.6 s against 2.3 ms for rules —
three orders of magnitude — which is the entire argument for invoking it only on low-confidence
turns rather than every turn.

**Path to production.** Shadow traffic first, then A/B, then a learned ranker once behavioural data
accumulates. One observability lesson transfers directly: measure layers, not just the end. Our
end-to-end score absorbed a parser defect for days until the parser was scored on its own, at which
point two real bugs surfaced within an hour. Any deployment should carry the equivalent of
`parser_accuracy` as a live metric.

**Risks and compliance.** Personalisation on purchase sequences crosses a privacy boundary that
aggregate tags do not, and needs consent and retention policy attached rather than assumed.
Explainability also becomes a requirement rather than a nicety: here the reason a product ranked
first is mechanically recoverable — which constraints matched verbatim, and what the priors
contributed — and that trace is exactly what a storefront should surface as "why you are seeing
this". Cold start and long-tail categories remain open: the prior axis favours popular items by
construction, which is correct for conversion and wrong for discovery.

**Net effect: the transferable core is the constraint-driven pipeline, the prior axis and the
layered evaluation discipline; the scaffolding is worth −0.0031 to remove (exp 43) and takes no
coverage with it.**

---

# 10. Method: how we decided what to keep

**The question this chapter answers:** with 200 labelled sessions and no leaderboard, why should any
number in this report be believed?

Three rules, adopted after our first over-fitting scare and applied to every change since.

**Stop where all three difficulty buckets improve together.** The popularity prior kept raising the
score up to weight 6 — monotone improvement with no plateau is an over-fitting alarm, not a win. At
weight 2.0 easy, medium and hard all improved; at 3.0 easy rose while medium fell. We stopped at 2.0
and left measurable score on the table (exp 10c, measured on the then-current ranker, before the
mirror bonus and phrase recall existed — the figure is not reproducible against the shipped code, so
we do not quote one).

The rule then caught us on the weights we are actually submitting. §5 gives the neighbourhood scan
in full; the short version is that our re-swept optimum stands **+0.0009** above its neighbour,
which is the quantity the next paragraph calls noise, and that we therefore report it as where our
grid landed rather than as a value the rule selected. We are documenting that against our own
interest, on the live configuration rather than on a decision safely in the past. It was found by a
teammate re-deriving a number he had been handed, and it is in this report because **a rule you
suspend when it is inconvenient is not a rule.**

**Convert small gains into "how many sessions is that?"** With 200 samples one session is worth
0.0007–0.0025. A tuning result of +0.0009 is one session flipping, and is indistinguishable from
noise. We rejected three such improvements on this basis, and we applied the same threshold against
ourselves when a mechanism we liked landed inside it.

**Every assumption gets a failure simulation.** Three implementations of the withholding rule scored
*identically* on the public set; only by simulating parser failure did we find that one of them
degrades catastrophically (HitRate 0.950) while another exits safely. **Public-set parity is not
evidence of equivalence** — a lesson that generalises well past this competition.

**What we rejected, and where the evidence is.** The negative results below cost more hours than the
positive ones and did more to shape the final system, because each of them closed a whole direction
rather than a single parameter:

| Rejected | Why | Detail |
|---|---|---|
| LLM listwise re-ranking | Ceiling is parity, not improvement; 106× the wall-clock | §7 |
| Profile-based soft preferences | Permutation test 1.021×, p ≈ 0.18 — the information is not in the data | §6 |
| Dense route in the default path | Negative in the shipped configuration; asymmetric OOM downside | §4 |
| Entropy question policy | −0.0252, against an oracle ceiling of +0.00385 for the entire dimension | §3 |
| Feature-count prior | Both tested weights scored below not having it at all | `experiments.md` #10b |
| Cross-turn rejection filtering | Zero effect — sessions end before the stagnation signal can accumulate | §6, `experiments.md` #18 |
| Early-turn withholding | Worth +0.0244 on the shipped code and genuinely effective, but it is the opposite of what a storefront should do | §5, §11 |

**We stopped tuning because we proved there was nothing left to win.** §5 carries the ceiling
analysis: of the 38 sessions not ranked first, 7 are information-theoretically indistinguishable
from their twins and the other 31 are the measured price of a mechanism we chose to remove, leaving
a reachable MRR gain of **0.00075** — below our own noise threshold. We closed the tuning phase on
that result on 30 August, two days before the deadline, and spent the remainder on robustness and
deliverables. The discipline worth reporting is not the ceiling itself but what it licensed us to
stop doing: further tuning there would have bought noise and paid for it in private-set
generalisation.

---

# 11. Limitations

1. **Public-set saturation is not private-set safety.** HitRate is 1.000 on 200 public sessions; the
private 800 use different users and different targets. Our best proxy is the stress table in §8:
with the shipped configuration the curve runs 0.9466 → 0.9168 across five rewrite levels, so we
expect roughly **0.92–0.95** if paraphrasing is applied *and* the parsing layer has network access.
Without that access the same curve floors at **0.827**. We cannot narrow this further — the levels
are our own mechanical rewriter, not evidence about the private split.

2. **Our ranker is a hand-weighted linear scorer.** With behavioural data at commercial scale the
natural successor is a learned ranker — LambdaMART or gradient-boosted trees over the same features,
plus a cross-encoder over the low-confidence tail. With 200 labelled sessions, learning the weights
would mean learning the public set; hand weights plus an explicit stopping rule (§10) are the more
honest instrument at this data volume. We regard this as a **data-regime decision, not an
architectural preference**, and it is the first thing we would change given real traffic.

3. **One benchmark-shaped mechanism remains, behind a flag.** We removed the large one — early-turn
withholding — because it is the opposite of what a storefront should do (§5). Measured on the
shipped code, the two mechanisms span **0.9436 to 0.9710**: restoring withholding (`EARLY_TOPK=1`)
is worth **+0.0244**, and disabling the intent-card mirror bonus (`MIRROR_BONUS=0`) costs
**0.0031**. **HitRate is 1.000 at every point on that line**, which is the honest form of the claim
that our architecture does not depend on either of them (§9). The larger −0.0286 figure quoted for
withholding elsewhere in our logs is the like-for-like measurement taken *before* the prior weights
were re-scanned for a ten-item result list (§10); both are correct comparisons, and this one is the
one the shipped code reproduces.

4. **The `other`-only question policy is a property of this simulator, not a claim about shopping.**
§3 bounds it rather than defending it, and the generalisable alternative ships behind
`ASK_POLICY=entropy` with its cost stated. We also do not implement Buying/Browsing routing, and §3
explains why the two modes collapse here and §9 what a real deployment would need instead.

5. **The dense route ships disabled and we can say precisely what that costs.** −0.0090 on the
public set in this configuration, positive only under paraphrase, against a memory footprint that
more than doubles (§4). We keep the code and the flag rather than deleting the negative result.

6. **The parsing model is an enhancement, not a dependency.** `LLM_PARSE=1` is the default and makes
**zero calls** on unmodified phrasing; without credentials or network it trips a breaker after two
consecutive failures and falls back to rules, so the headline number is unchanged in a
network-restricted environment (§2). Its worst observed single call reached the then-45 s client
timeout and succeeded on retry, which is why the parsing layer now has its own 12 s budget against a
measured p95 of 1.0–5.6 s.

7. **Latency was measured on one machine** (Apple M5). Absolute numbers will differ; the ~106× ratio
between the offline and LLM ranking paths should not.

---

# 12. How we worked, and who did what

**The question this chapter answers:** four people and a two-and-a-half-day window — how were the
decisions in this report actually made?

**Decisions happened in writing, asynchronously, in the repository.** We ran the team on a single
file, `team/留言板.md` — a message board committed alongside the code, readable and writable by both
the humans and the AI assistants each of us worked with. Every substantive decision has a thread:
the proposal, the objections, the data someone went and measured because of the objection, and a
one-line verdict moved to an archive table when it closed. That archive is the audit trail for this
report. Two examples of it working: the decision to ship the dense route disabled was **reopened**
after a teammate produced paraphrase-stress data that contradicted the original ruling, and the
second ruling kept the same outcome for an entirely different and better reason; and an external
architecture review we solicited produced a "benchmark trick" objection that we answered not by
arguing but by building the removable-mechanism configuration now reported in §9 and §11.

**We logged the experiments we rejected next to the ones we kept.** `team/experiments.md` holds 66
numbered entries. Roughly a third are negative, and §10 is written out of them.

**We caught each other's mistakes, and the corrections are in the log.** Three that changed the
deliverable: a figure whose bars overlapped its own labels, spotted by a teammate who rendered it
instead of reading the source; a decision threshold with a gap in the middle of it, spotted by the
person who had originally proposed the threshold and then retracted it in writing; and two batches
of unit tests written in the wrong style, which were silently never collected — the first batch was
found by hand, and a guard added because of it caught the second batch within two hours. That guard,
`check_guards.py`, now fails the build if the number of defined test cases and the number of
collected test cases disagree. **Turning a lesson into an automatic check rather than a note in a
document is the pattern we would keep.**

| | Module | Contribution |
|---|---|---|
| Chen Zhilong (A) | M1 dialogue control | Full-chain prototype (0.107 → 0.861), slot state machine, value normalisation, three-layer parsing defence and the parser-accuracy metric, intent-card mirror bonus and phrase recall, stability hardening, final configuration |
| Zhou Junkai (B) | M2 retrieval | Dense route with non-displacing fusion, Recall@pool 1.000, recall regression tooling, the instrumented diagnostic that explained the route's sign change, independent verification of the numbers in this report |
| Lin Xiaoxiao (C) | M3 ranking & generation | Prior-axis discovery (0.861 → 0.935), the withholding mechanism and the measurement that later justified removing it, paraphrase stress harness and rule salvage layer, LLM three-arm controlled experiment, cost disclosure, ceiling proof, CI and guard tooling |
| Bi Yongqi (D) | M4 memory | Context distillation, profile lexicon, cross-turn signals, and the permutation test that closed the profile-signal question definitively |
| — (E) | M5 evaluation | Absent for the event; responsibilities redistributed across the team |

**In their own words** — one paragraph each, written by each author. The table alone reads as
boilerplate, and this is where a reader can see whether the collaboration was real.

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

# 13. Reproduction

Python **3.10+**. The submitted path requires **no third-party packages** — `requirements.txt`
applies only to the optional dense route (`USE_DENSE=1`), which degrades to pure BM25 when its
assets are absent. No API key and no network access are required; see the declaration in §2.

```bash
python3 scripts/prepare_catalog.py        # verify SHA-256, extract the catalogue (once)
python3 -m evaluator.local_evaluator      # 0.9466 — standard library only, ~10 s
```

The second command is the whole submission: it runs our Agent in the official harness and prints the
scored result. Everything below reproduces a specific claim in this report:

```bash
python3 scripts/check_guards.py           # red-line self-check + 30 unit tests
python3 scripts/parser_accuracy.py        # §3 — parser accuracy in isolation
python3 scripts/paraphrase_stress.py      # §8 — robustness across 5 stress levels
python3 scripts/ceiling_diagnostic.py     # §10 — remaining headroom, decomposed
python3 scripts/trace_session.py --id public_0002   # §2 — the session walked through above
```

Every default is an environment variable, listed with its shipped value in the table in §2 and
documented in `src/config.py` beside the experiment that set it. To reproduce the two comparison
configurations named in this report:

```bash
EARLY_TOPK=1   python3 -m evaluator.local_evaluator   # 0.9710 — withholding restored
MIRROR_BONUS=0 python3 -m evaluator.local_evaluator   # 0.9436 — every benchmark-shaped mechanism
                                                      #   off; HitRate stays 1.000
```

---

*Evidence for every number in this report: [`team/experiments.md`](team/experiments.md) (66 logged
experiments, including the ones we rejected), [`COST_AND_LATENCY.md`](COST_AND_LATENCY.md), and the
module handover documents under `team/`.*
