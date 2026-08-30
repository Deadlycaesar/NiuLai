# Cost, Latency and Token Disclosure

`docs/submission_rules.md` requires "a disclosure of latency, token usage, and estimated model
cost"; `docs/competition_specification.md` classes these as **feasibility** measures that do not
enter TechnicalScore. This is that disclosure.

All figures are measured on the machines named, not estimated. The working notes behind them are in
[`team/成本与延迟披露.md`](team/成本与延迟披露.md) (Chinese — team-internal); this file is the
canonical English version and the two are kept in sync.

## In one line

**The submitted configuration calls no external model: zero tokens, zero cost, no network, and the
full 200-session evaluation finishes in about 10 seconds.** Every LLM and dense-retrieval path is an
optional enhancement, disabled by default, with its cost and measured benefit listed below.

## Submitted configuration — `USE_LLM=0`, `LLM_PARSE=0`, `USE_DENSE=0`

| | Measured |
|---|---|
| Third-party dependencies | **None.** Python standard library only. `requirements.txt` applies solely to `USE_DENSE=1` |
| Network calls | **None.** The evaluator runs to completion with networking disabled |
| Token usage | **0** |
| Model cost | **0** |
| Startup | 4.1 – 6.9 s, once (loads 50,000 products, builds the SQLite FTS5 index) |
| **Resident memory (peak)** | **530 MB** (Windows peak working set) / 340 MB (macOS `ru_maxrss`). Flat after 50 sessions × 3 turns — **no leak**. We quote the more conservative figure |
| **Per-turn `respond()` latency** | **median 2.3 ms · p95 2.8 ms · max 3.5 ms** (60 samples) |
| Full 200-session evaluation | **9.7 s**, including startup |
| TechnicalScore | **0.9694** |

The specification notes that timeouts may be scored as a miss. At a 2.3 ms median that risk is
effectively zero.

## A note on the memory ceiling

`submission_rules.md` states: *"The organizer reserves the right to run your submission under CPU,
memory, timeout, and network restrictions."* — the right is reserved, **no figure is given**. We
therefore designed for "spend less" rather than for a known budget:

| Configuration | Peak RSS | Dependencies | Network |
|---|---|---|---|
| **Submitted (`USE_DENSE=0`)** | **530 MB** | none | none |
| `USE_DENSE=1` (**not enabled**) | **1191 MB** | torch + transformers + sentence-transformers | none (offline cache only) |

Of the +661 MB, the embedding matrix accounts for only 77 MB; the rest is the torch runtime itself.
An ONNX backend brings the peak to 787 MB with byte-identical scores, and we still did not enable it
— reasoning under *Optional enhancement 3*.

Worth stating plainly: **the 530 MB baseline sits on the same exposure curve.** A ceiling tight
enough to kill the 1191 MB configuration would also threaten the default one. Disabling the dense
route moves us left along that curve; it does not step off it.

## Optional enhancement 1 — LLM listwise re-ranking (`USE_LLM=1`, off)

Client: `src/ranking/llm_client.py`, pure standard-library `urllib`. Thinking explicitly disabled,
JSON mode, `temperature=0`, one retry, and any failure falls back to the rule ordering.

Sampled over 40 stratified sessions (`--n 40 --seed 2026`):

| Configuration | Score | MRR | Per-call latency | Tokens (40 sessions) | Extrapolated to 200 |
|---|---|---|---|---|---|
| Rules only (control) | **0.9507** | 0.963 | — | 0 | 10 s · ¥0 |
| `LLM_PROMPT=basic` | 0.9305 ↓ | 0.905 ↓ | ~2.2 s | 18,675 | ~16 min · 93k tokens |
| `LLM_PROMPT=evidence` (default shape) | 0.9503 | 0.963 | ~2.3 s | 20,423 | ~18 min · 102k tokens |

Three runs of the evidence arm: **0.9511 ±0.0005** — indistinguishable from the 0.9507 control.

**Cost**: ¥0 on a free tier; roughly **¥0.18** per full run at DeepSeek v4-flash off-peak rates
(¥1.5 / ¥4.5 per million tokens). Thirty runs across the whole event would not reach ¥6.

**Why it ships disabled**: enabling it costs roughly **106× the wall-clock time** (9.7 s → 18 min)
for a statistically zero gain, and it makes scores irreproducible — server-side variation persists
at `temperature=0`.

> Silent degradation is real, not hypothetical. On one repeat run the reported token count was zero
> and the score landed exactly on the rules-only baseline: every call had timed out and fallen back,
> with no error surfaced. The cause was a 20 s client timeout against a provider whose calls
> occasionally take 21.5 s. The timeout is now 45 s. **This is the clearest argument for not making
> the default path depend on an external service: it can disappear without telling you.**

## Optional enhancement 2 — LLM verbatim fragment extraction (`LLM_PARSE=1`, off)

The third layer of the parsing defence. It fires only when both strict templates and rule-based
salvage have failed, and anything the model returns must survive a **verbatim check** — normalised,
it has to be a contiguous substring of the original message, or it is discarded. Missing credentials
degrade instantly; two consecutive failures trip a circuit breaker.

Measured (experiments #33, #36): zero triggers across all 200 public sessions — by construction, not
by luck. Under the L4 stress level (colon-free paraphrase) it lifts the score from **0.8486 to
0.9551**, matching the L1 level.

> ⚠️ **These figures require a rate-limit-free endpoint.** On a free tier we measured 6 of 8 calls
> returning HTTP 429; two consecutive failures trip the breaker and the layer switches itself off
> **silently**, leaving a score identical to the rules-only path. The difference is not model
> quality — it is whether the calls connect at all.

## Optional enhancement 3 — dense retrieval (`USE_DENSE=1`, off)

bge-small-en-v1.5 (133 MB) with pre-computed embeddings for all 50,000 products; the artefact
`data/embeddings.npz` is 72 MB and the matrix occupies ~73 MB at runtime. No network calls
(`TRANSFORMERS_OFFLINE=1`, local cache only).

Measured benefit: **+0.0016** on the unmodified public set (0.9694 → 0.9710, 5 sessions improved,
0 regressed) and **+0.011 to +0.020** under paraphrase stress at levels L1–L3.

**Why it ships disabled** — the reasoning is about the shape of the downside, not the size of the
gain:

- +0.0016 on the public set sits **below our own 0.002 noise threshold**, the same threshold we used
  to reject two other candidate improvements. We could not credit it here and dismiss it there.
- Missing assets degrade gracefully to pure BM25. **An out-of-memory kill does not degrade at all.**
  With a benefit of ~0.015 against a total loss, the break-even probability of an OOM is 1.5% — and
  with no stated memory ceiling, we cannot argue we are below it.

The route stays in the codebase. It raised Recall@pool to **1.000**, and its graceful-degradation
path is exercised by the guard suite.

## Reproduction

```bash
python3 -m evaluator.local_evaluator                                  # default: 9.7 s, 0 tokens
USE_LLM=1 LLM_PROMPT=basic    python3 scripts/eval_sample.py --n 40   # re-rank, basic prompt
USE_LLM=1 LLM_PROMPT=evidence python3 scripts/eval_sample.py --n 40   # re-rank, evidence prompt
LLM_PARSE=1 python3 scripts/paraphrase_stress.py --levels L0 L4       # third parsing layer
USE_DENSE=1 python3 -m evaluator.local_evaluator                      # dense route (needs assets)
```

API credentials are read from `.env`, which is git-ignored; `scripts/check_guards.py` verifies on
every run that it is untracked and that no key is hard-coded anywhere in the tree.

Any figure for an LLM path must be produced against a paid, rate-limit-free endpoint — see the
warning under *Optional enhancement 2*.

## Where the LLM earns its place

| Used for | Measured | Verdict |
|---|---|---|
| **Ranking** | titles only −0.020; with hit evidence −0.0004 | Ceiling is parity, not improvement |
| **Understanding** | L4 stress 0.8486 → **0.9551** | Genuinely irreplaceable |

The rule scorer has already extracted everything the hit evidence contains, so a model given the
same evidence reproduces the same ordering. **The model earns its place in listening, not in
ranking** — a conclusion from three controlled experiments, not a prior.
