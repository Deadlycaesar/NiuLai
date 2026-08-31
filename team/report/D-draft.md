# D (@BestBucky) — Chapters 6 & 9

> 交稿版 09-01。英式拼写，术语按大纲附录 C，数字全部来自附录 A（新增两处已入库，见文末「给整合人的说明」）。
> Ch6 455 词 / Ch9 正文 548 词 + 七行映射表（表是本章骨架，任务卡要求至少六行）。

---

# Chapter 6 · Safe personalisation: a negative result on a direction the brief named

**The question this chapter answers:** the brief names "safe personalization using the aggregate profile" as an innovation direction. We built it. What did it turn out to be worth, and how do we know?

**What we built.** The evaluator hands us a five-key `user_profile` at `reset()`, before the customer has said anything — the only signal available for a cold start. We parsed it into a soft-preference lexicon (`preference_tags` is a closed set of nine values, verified across all 200 public sessions) and added two cross-turn signals: a stagnation counter and a record of previously shown candidates. A context distiller compresses session state into one bounded line per turn, its turn-10 output **0.80×** its turn-3 length (exp 22) — the state converges rather than accumulating.

**The first number looked like signal.** Profile keywords occur in the target listing 1.745× more often than in a random listing (exp 22).

**It was a confound.** Target products come from real purchase records, so they are systematically the popular ones — the same skew that makes the prior axis work in Chapter 5, where targets carry 570× the median review count. Popular products have longer listings, so *any* word hits them more often. The lift was measuring listing length, not relevance.

**The permutation test.** Holding the targets fixed and shuffling only which profile pairs with which session — identical items, identical listing lengths, only the pairing destroyed — the ratio falls to **1.021×** (z = +0.93, p ≈ 0.18, 200 permutations, exp 22): a 2% effect we cannot distinguish from zero.

**Stated as information rather than implementation:** the ceiling on this feature is not set by how we wire it, weight it or gate it — it is set by information content, and this data does not carry it. That retired an entire class of follow-up work in one measurement — cold-start-only application, retrieval-only, ranking-only, weight sweeps, per-tag gating — each of which would otherwise have cost a wiring and a full evaluation to falsify alone. The time saved exceeds anything the feature could plausibly have scored.

Two same-batch negatives agree: `rating_style` does not predict the target's average rating (4.41 / 4.28 / 4.31, exp 22), and the apparent tag-to-category skews are small-count noise across 112 categories over 200 sessions.

**Where the code went.** `lexicon.py` and `signals.py` remain in the repository under 12 unit tests, deliberately disconnected from the scoring path. The one signal we did offer the ranker, `actionable_rejections`, measured as exactly zero when wired in (exp 18): with HitRate at 0.995 and MTTC at 2.23, almost every session ended before a stagnation signal could accumulate.

**Net effect: 0.0000 on TechnicalScore, by decision rather than by omission.** What generalises is the entry criterion, and it needs data this benchmark does not have — purchase sequences and browsing behaviour rather than an aggregate tag set. Chapter 9 takes that up.

---

# Chapter 9 · From benchmark to a real storefront

**The question this chapter answers:** with the evaluator taken away, which parts of this system survive, which are scaffolding, and what would replace them?

**The benchmark-shaped mechanisms unload with a flag — and one of them is already unloaded.** The shipped default runs with `EARLY_TOPK=0`: we withdrew early-turn withholding before submission, on a product judgement rather than a score one, paying −0.0286 entirely out of MRR while HitRate held at 1.000 across all five stress levels. That leaves the intent-card mirror bonus as the only mechanism in the shipped default with no real-world counterpart. Removing it costs **−0.0031** (0.946642 → 0.943581) with **HitRate unchanged at 1.000 and MTTC unchanged at 1.935** (exp 43). Measured earlier with withholding still enabled, the full unload was 0.9694 → 0.9383, again at HitRate 1.000 in both configurations (exp 30, benchmark-configuration figures — not comparable with the shipped default). The claim is not that we avoided benchmark-specific optimisation; it is that it detaches cleanly, and that coverage does not depend on it.

| Mechanism | Why it holds in this benchmark | In a real storefront | Keep / replace |
|---|---|---|---|
| Verbatim substring match | The customer's constraints are copied verbatim from the target's own listing | Real shoppers do not quote product copy | **Replace as primary.** Demote to one recall signal among several; the semantic route becomes the main path |
| Intent-card mirror bonus | The intent card is an artefact of the evaluator | No counterpart exists | **Replace** with attribute salience — a match in the title, a structured field or the first bullet weighs more than one in the eighth paragraph of a description |
| Constant `other` question | The simulator discloses up to two constraints per turn and `other` matches any of them | A real shopper asked "anything else?" every turn simply stops replying | **Replace** with expected information gain traded against a patience cost |
| Stop-on-hit | Defined by the evaluation protocol | Add-to-basket or checkout | **Keep.** The objective has the same shape — early and accurate — so the ranking policy transfers unchanged |
| Hand-weighted linear scorer | 200 labelled sessions; learning the weights would mean learning the public set | Real behavioural data at volume | **Replace** with LambdaMART or GBDT, with a cross-encoder on the low-confidence tail |
| Aggregate profile | Carries **no information** about the target (Chapter 6) | Purchase sequences and browsing behaviour exist and are genuinely predictive | **Rebuild on different data.** Aggregate tags are the wrong object; sequences are the right one, and they bring a privacy boundary with them |
| Buying / Browsing routing | The simulator collapses browsing into buying: one target, verbatim constraints, stop-on-hit | The two modes optimise different things — precision@1 versus information gain and diversity | **Add.** A continuous `intent_confidence` rather than a branch, diversity re-ranking (MMR/DPP), and expected-information-gain questioning |

The last two rows are where our own evidence is strongest and weakest respectively. On the profile row we are not speculating: the permutation test says what is missing and therefore what would have to be present. On the routing row we should be explicit that we did not build a router — `state.scenario` is populated but never read by retrieval or ranking, so buying and browsing take one identical path. Both halves of a router already exist in the repository: the prior axis is a browsing ranker, and `ASK_POLICY=entropy` is a browsing questioner. The latter costs −0.0252 here (exp 35) precisely because there is no real browsing to serve.

**Engineering budget.** 50k SKUs in SQLite FTS5 answer in 2.3 ms median per turn (p95 2.8 ms); at tens of millions this becomes an ANN index and the latency budget changes shape. The offline path holds a 530 MB resident set and starts in 4.1–6.9 s; enabling the dense route takes that to 1191 MB on torch, or 787 MB on an ONNX backend. LLM parsing runs at p95 1.0–5.6 s against 2.3 ms for rules — three orders of magnitude — which is the entire argument for invoking it only on low-confidence turns rather than every turn.

**Path to production.** Shadow traffic first, then A/B, then a learned ranker once behavioural data accumulates. One observability lesson transfers directly: measure layers, not just the end. Our end-to-end score absorbed a parser defect for days until the parser was scored on its own, at which point two real bugs surfaced within an hour. Any deployment should carry the equivalent of `parser_accuracy` as a live metric.

**Risks and compliance.** Personalisation on purchase sequences crosses a privacy boundary that aggregate tags do not, and needs consent and retention policy attached rather than assumed. Explainability also becomes a requirement rather than a nicety: here the reason a product ranked first is mechanically recoverable — which constraints matched verbatim, and what the priors contributed — and that trace is exactly what a storefront should surface as "why you are seeing this". Cold start and long-tail categories remain open: the prior axis favours popular items by construction, which is correct for conversion and wrong for discovery.

**Net effect: the transferable core is the constraint-driven pipeline, the prior axis and the layered evaluation discipline; the scaffolding is worth −0.0031 to remove (exp 43) and takes no coverage with it.**

---

## 给整合人（@LIN XIAOXIAO）的说明

1. **两处数字是我新测/新数的，已入库，可直接引用**：
   - **实验 43**（新增）：当前档下卸载 mirror bonus = **−0.0031**（0.946642 → 0.943581），HitRate 1.000 与 MTTC 1.935 **逐位不变**。
     大纲附录 A 里第 9 章原本给的是实验 30 的 0.9694 → 0.9383，那是**藏牌开**的旧档；而提交默认已经是 `EARLY_TOPK=0`，
     用旧档数会让人以为我们还留着最大的那个赛技。两个数我都写了，并各自标了口径。**建议附录 A 补上实验 43 这行。**
   - **单测数 12，不是 15**。大纲第 6 章任务卡写的「15 个单测覆盖」是当时**全套件**总数（含 evaluator 的 3 个）；
     `test_lexicon.py` + `test_signals.py` 实际是 12 个。稿子里写的 12。
2. **第 6 章的「净影响」我写成了 `0.0000，by decision rather than by omission`**——如果你觉得在一篇总分导向的报告里
   直接写 0 太扎眼，可以改措辞，但**请保留"这是决定不是遗漏"这层**，那是这章唯一的立足点。
3. **第 9 章路由那一段是照大纲 §6 的口径写的**（我们没有真 router，`state.scenario` 从未被读）。
   我核过 `ranking/`、`retrieval/`、`policy.py`、`agent.py`，与 @陈智龙 的结论一致，没有读漏。
4. 术语已按附录 C 统一（verbatim substring match / prior axis / stop-on-hit / stress level / the shipped default /
   early-turn withholding / permutation test），英式拼写，Δ 用真减号 −。
