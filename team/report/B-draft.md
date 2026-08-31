# B (@周峻恺) — Chapter 4: Retrieval

> 任务卡：[`team/报告-分章大纲.md`](../报告-分章大纲.md) §5。**直接写英文**，写完交 @LIN XIAOXIAO 整合润色。
> 动笔前扫 **附录 C 术语表**（英式拼写：optimised / behaviour / normalised）。
> 数字只从 **附录 A 口径快照表** 取，每条标实验号。目标 600 词。**03:00 前交**。
> 你还兼**全篇数字审计**（05:30–06:30 那一轮）。

## The question this chapter answers

Is the target product even inside the candidate pool — and if it always is, what is left for
semantic retrieval to do?

## 1. Retrieval stopped being the bottleneck — and we proved it

Recall@pool is **1.000**: across all 200 sessions, the product the simulated customer will
eventually buy is always inside the 300-candidate pool before any ranking happens (exp 6b).
This is not a boast; it is a premise, and several later negative results stand on it. Once the
pool provably contains the target, no downstream idea of the form *"add more candidates"* can
help — profile-based recall injection, LLM-suggested queries, and dense candidates all died on
exactly this fact. Measuring recall first is what let us spend the rest of the project on the
problems that were actually losing points.

## 2. What the keyword route actually does

The main route is SQLite FTS5 keyword search with field weighting, plus two mechanisms aimed at
the pool's edge cases. Slots with three or more tokens issue per-constraint FTS5 *phrase* queries
alongside the main OR-token pool, and BM25 ranks are normalised within each sub-pool before
merging. The phrase sub-pool exists because of one instructive failure: `public_0020`, an
ultra-cold target whose constraints were all boilerplate, could never climb into the top-300 of
the token pool — its phrase query, against a pool of almost nothing, brought it back. That was
the session that took HitRate to 1.000 for the first time (exp 22).

## 3. The dense route: one mechanism, two counterfactuals

We still built the semantic route — precomputed bge-small-en-v1.5 embeddings fused as a
non-displacing union with sentinel ranks — and then instrumented it to see what it actually does
(exp 38). It only ever adds recall; it never displaces a keyword candidate. But the same
behaviour has two counterfactual outcomes depending on where it lands. On the unmodified public
set it advances 17 sessions to an earlier hit while worsening the final rank of 11 — a net
**−0.0090** (exp 37): "one turn earlier" cannot compensate for "not rank 1". Under stress level
L2 the identical behaviour lands on sessions that would *never* have hit at all and rescues 4 of
them — a net **+0.0149**. The sign flip is not the dense route changing; it is the removal of
early-turn withholding (exp 37), which had been masking the harm channel all along. Under the old
withholding configuration the same mechanism had read +0.0016 on the public set (exp 28,
historical configuration) — the masking, measured.

## 4. We ship it off, and the reason is expected value, not magnitude

The decision to ship with `USE_DENSE=0` was not about the size of the gain but the shape of the
loss (exp 31). The route's degradation path covers missing assets and missing dependencies — a
missing embedding file falls back to pure BM25 gracefully, and we verified the whole pipeline
bit-identical with the network physically off (exp 29). It does not cover OOM: a memory-limit
kill does not degrade, it zeroes the run. Against a conditional gain of about +0.015 (paid only
if the private set is paraphrased at all) stands a loss of ≈ −1.0, so the break-even is
P(OOM) < 1.5% — and the organiser reserves memory limits without naming them. One honest
footnote (exp 31a): our 530 MB baseline already sits on the same exposure curve, since a limit
tight enough to kill the route's 787 MB ONNX peak (1,191 MB on PyTorch) would likely threaten
530 MB too. Shipping off moves the point left on that curve; it does not leave it.

## Net effect

Retrieval contributes a candidate pool that provably always contains the target, at zero marginal
runtime risk; the dense route is kept, measured from both directions, and deliberately switched
off (exp 6b, 22, 28, 29, 31, 37, 38).
