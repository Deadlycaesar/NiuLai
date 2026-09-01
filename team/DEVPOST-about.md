# Devpost「About the project」草稿

> D（毕永琪）起草 · 09-01 · **给 @陈智龙 填表用**（T-005 归档：表单 A 本人填、文案由 AI 备草稿）
>
> Devpost 该字段要求覆盖四件事：**what inspired you / what you learned / how you built it / challenges you faced**，
> 支持 Markdown 与 LaTeX。下面 **`---` 之间的部分**可整段粘贴，约 900 词。
>
> **素材来源（每段都可回溯，不是新写的说法）**：
> | 段落 | 来源 |
> |---|---|
> | Inspiration | `REPORT.md` §1「What we read first」三条发现 |
> | How we built it | `REPORT.md` §2 架构 / §3 解析 / §4 召回 / §5 排序 |
> | Challenges | §3 改写压力档、§7 LLM 两次负结果、§6 我的置换检验、§11 局限 |
> | What we learned | §10 方法论（停止准则 / 噪声阈值 / 失败模拟）、§12 各人自述 |
> | LaTeX | 官方公式取自 `docs/evaluation_config.json`；0.743 / 0.980 两笔账已复算 |
>
> ⚠️ **填表前请核两处**：① 仓库是否已转公开（留言板提过还是 private）；② 分数若有变动以 `results.json` 为准。

---

## NiuLai — a conversational shopping agent that argues with its own results

A shopper says *"I'm looking for tunics, but I'm still exploring."* Ten turns later the agent has to
have put the one product they actually bought — out of 50,000 — at the top of a list. Our submitted
system does that for **200 of 200 public sessions**, at **TechnicalScore 0.9466** against the
official baseline of 0.107, using the Python standard library only, offline, in 9.7 seconds.

The score is the least interesting thing about it. What we would rather be judged on is the set of
things we measured, disproved, and removed.

## Inspiration

We nearly started by writing prompts. Instead we spent the first forty minutes reading the
evaluator's source, and three facts there overrode the plan we walked in with.

**The simulated customer never reads our prose.** It consumes a single `ask_attribute` value from a
ten-item enum; the `message` string is only type-checked. Our entire channel to the customer is
roughly $\log_2 10 \approx 3.3$ bits per turn. No amount of prompt craft can change what the
customer says next — so we optimised our copy for human readers and said so, rather than presenting
it as a modelling achievement.

**The customer quotes the product.** The constraints they utter are verbatim fragments of the target
item's own catalogue text, which makes verbatim substring matching close to a fingerprint. That one
property drove almost every later decision.

**A hit ends the session and locks in that turn's rank.** The official composite is

$$\text{TechnicalScore} = 0.50\,\text{HitRate@10} + 0.30\,\text{MRR} + 0.20\,\text{Efficiency},
\qquad \text{Efficiency} = \mathrm{clip}\!\left(\frac{11 - \text{MTTC}}{10},\,0,\,1\right)$$

so converting *early* at a mediocre rank is a trade the metric punishes:

$$\underbrace{0.5 + 0.3\cdot\tfrac{1}{7} + 0.2\cdot\tfrac{10}{10}}_{\text{turn 1, rank 7}} = 0.743
\quad<\quad
\underbrace{0.5 + 0.3\cdot 1 + 0.2\cdot\tfrac{9}{10}}_{\text{turn 2, rank 1}} = 0.980$$

We found 31 sessions sitting in exactly that losing trade. None of these three facts is inferable
from the problem statement; all three are visible in the source.

## How we built it

A single constraint-driven pipeline, deliberately not branched by intent: parse the customer's turn
into slots → retrieve candidates → score them → ask the one question with the highest expected
yield, while always returning a full slate.

- **Parsing has three layers.** Strict templates first; then a rule-based salvage layer that pulls
  constraint fragments out of unfamiliar phrasing; then, only when both fail, an LLM that extracts
  verbatim spans. A candidate extraction is accepted only if the catalogue actually contains it —
  we validate against the data, not against a grammar.
- **Retrieval** is BM25 over SQLite FTS5 with per-constraint phrase recall. We built a dense
  embedding route too, measured it honestly, and ship it disabled.
- **Ranking** scores two independent axes. The *relevance axis* asks which product matches the
  sentence. The *prior axis* asks which product a real person would actually have bought — targets
  come from genuine purchase records, so they carry $570\times$ the median review count and are
  $4.3\times$ more likely to have a price field. Nobody had used those two columns. Adding them was
  the single largest gain in the project.

Everything ships behind flags, the default path makes zero network calls, and the headline number is
bit-identical with the network removed.

## Challenges

**The public set cannot show you what breaks on the private one.** The organisers reserve the right
to paraphrase the simulated customer, and our whole pipeline rested on verbatim matching. So we
built a five-level paraphrase stress harness and found the damage was not where we assumed: it was
*sentence-pattern* matching that shattered, not verbatim matching. The three-layer parser is the
answer to that, and it recovers most of the loss.

**Our own metrics hid a defect.** An end-to-end score absorbs upstream failures silently. Only after
scoring the parser *in isolation* did two real bugs surface — within an hour of that metric
existing.

**The most interesting failure was a personalisation feature that looked like it worked.** The brief
names "safe personalization using the aggregate profile" as an innovation direction, so we built it.
Profile keywords hit the target listing $1.745\times$ more often than a random listing — apparently
real signal. It was an artefact: targets are popular products, popular products have longer
listings, and *any* word hits them more often. Holding the items fixed and shuffling only which
profile pairs with which session, the ratio collapses to

$$1.021\times,\qquad z = +0.93,\qquad p \approx 0.18 \quad (200\ \text{permutations})$$

The profile is statistically independent of what the customer bought. We shipped the module running
and measured, but disconnected from scoring, and wrote down why.

## What we learned

**When the second implementation of an idea fails the same way, stop testing implementations and
test the premise.** Two wirings of the personalisation feature each falsified one design and left
"try a different weight" open. One permutation test closed the entire class. That single measurement
saved more hours than the feature could plausibly have scored.

**A rising score is not automatically a win.** One weight kept improving the score as we pushed it
higher — which is what over-fitting looks like, not what success looks like. We adopted a stopping
rule (keep a change only if all three difficulty buckets improve together), a noise threshold
($0.002$, about one session flipping), and a habit of simulating failure rather than trusting parity
on the public set. We rejected several "improvements" under those rules and left measurable points
on the table.

**We removed our largest benchmark-shaped mechanism on purpose.** Withholding recommendations in
early turns was worth $0.0244$, and it is not how a shopping assistant should behave. We shipped
without it. What remains that is benchmark-specific detaches for $-0.0031$, with hit rate and turn
count unchanged.

Sixty-six logged experiments are in the repository, including every one that failed.
