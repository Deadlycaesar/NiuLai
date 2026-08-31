# M4 · 记忆与上下文蒸馏 — 模块报告 / Memory and Context Distillation — Module Report

> 毕永琪（D） · 2026-09-01 · NiuLai / TikTok TechJam 2026 Track 4
>
> 本文是 M4 模块的完整报告，中英文对照。供 [`REPORT.md`](../REPORT.md) 统稿取用，
> 亦可作为独立附录提交。可直接粘贴的精简段落见 [`REPORT-M4素材.md`](REPORT-M4素材.md)。
>
> 全部数字可由 [`team/experiments.md`](experiments.md)、
> [`scripts/profile_signal_diagnostic.py`](../scripts/profile_signal_diagnostic.py) 复现。
> 引用实验编号时请注意 `experiments.md` 现存撞号（#20 重复、#21/#22 各两行），本文一并给出内容描述。

---

# 中文版

## 1. 模块定位与交付形态

M4 负责题目四大支柱中的第三条——「自我进化：动态上下文编程」，具体交付三件事：把逐轮增长的对话压缩为紧凑的结构化上下文；将官方提供的 `user_profile` 转化为冷启动软偏好；为决策层提供跨轮策略信号。

最终交付为 `src/memory/` 下的三个文件，共 150 行，**零第三方依赖，全部为纯规则实现**。其中蒸馏层在生产路径上**每轮无条件执行**；profile 注入与 Reflection 信号则**经完整测量后确定不接入打分路径**——这一决定的依据构成本报告的主体。

## 2. 设计依据：三项约束决定了全部技术选型

M4 的每一个技术选择都可回溯至三项外部约束，而非偏好：

**约束一：正式评测可能断网。** 提交规则保留了在无网络环境下运行的权利，项目红线要求每个 LLM 调用都具备离线降级路径。因此蒸馏采用模板拼接而非 LLM 摘要——它不是降级方案的备份，它本身就是降级态，不存在需要兜底的在线路径。

**约束二：不存在跨会话记忆问题。** 评测器为每个 session 调用一次 `reset()`，会话上限 10 轮，且私有集 800 条使用与公开集完全不重叠的用户与目标商品。这意味着 Mem0、向量数据库、FAISS 一类框架所解决的核心问题——跨会话的长期记忆抽取、去重与召回——在本任务中并不存在。引入它们只会带来一条依赖 LLM 判定与向量检索的运行时链路，与约束一直接冲突。故全部排除。

**约束三：状态层正在被并行重构。** M4 开发期间，M1 负责人正在重构 `src/dialog/state.py`（归一化收归、`Slot` 新增 `terms` 字段）。若 M4 同时申请修改 `DialogState` schema，将产生跨目录协调成本与合并冲突。故跨轮信号改用按 `session_id` 索引的模块级字典存储——这与 `src/ranking/llm_client.py` 中 `_usage` + `pop_usage()` 的写法同构，是项目已接受的模式，代价是牺牲一点封装性，收益是协调成本归零。

此外还有一项来自任务机制的设计判断：**约束的衰减应由事件触发，而非由轮数触发**。除 Intent Override 场景外，目标商品在整场会话中不变；若按轮数对旧约束连续衰减，将在其余 85% 的场景中主动削弱正确信号。而 Override 的发生时刻由评测器以固定句式明确宣告，无需推断——因此正确的设计是监听该事件并做一次离散的状态跳变，而非模拟人类记忆的连续遗忘曲线。

## 3. 实现

| 文件 | 行数 | 职责 |
|---|---|---|
| `distiller.py` | 33 | 将 `DialogState` 压缩为单行结构化上下文 `state.distilled` |
| `lexicon.py` | 34 | `preference_tags` → 软偏好关键词的静态闭集查表 |
| `signals.py` | 83 | 跨轮信号：停滞轮数计数、已展示未命中候选追踪 |

`lexicon.py` 的取值域来自对 `public_set.jsonl` 全部 200 条样本的实测枚举：`preference_tags` 是九值闭集（fit 163 / material 154 / comfort 144 / style 101 / durability 47 / performance 26 / warmth 18 / weather 12 / general shopping 1）。同一轮分析还确认 `summary` 字段是 `preference_tags` 与 `rating_style` 的模板拼接、`average_prior_rating` 与 `rating_style` 一一对应、`purchase_frequency` 在公开集恒定——五键中仅 `preference_tags` 携带独立信息，故只解析该字段。对未在表中的 tag，函数静默返回空列表，以适配私有集可能出现的新取值。

`signals.py` 中的 Reflection 门控值得单独说明。评测器仅在 `override_applied=True` 时检查命中，而 Intent Override 场景在触发句出现前 `state.scenario` 保持 `"unknown"`。若不加区分地把「已展示未命中」计入负样本，将把尚未被检验过的候选永久拉黑。故追踪逻辑以 `prev_scenario != "unknown"` 为门控，确保只在评测器确实已经检查过命中的轮次之后才累计。

## 4. 实测结果

**蒸馏层：达标。** 全量 200 条实测，`state.distilled` 在第 3 轮的平均长度为 319.2 字符，末轮为 256.3 字符，比值 **0.80×**——不增反减。原因是输出长度只随当前生效约束数增长，而 `other_first` 提问策略在数轮内即把评测器可吐露的约束问尽，长度天然封顶。

**profile 注入：负收益。** 将 `lexicon.profile_soft_terms` 接入检索查询扩展与排序软加权后，在分层抽样（`--n 60`）的改写压力测试下：

| 档位 | 不接入 | 接入后 | Δ |
|---|---|---|---|
| L0（原始话术） | 0.9595 | 0.9519 | −0.0076 |
| L1（句式改写） | 0.9595 | 0.9211 | −0.0384 |
| L2（+短约束改写） | 0.9634 | 0.9018 | −0.0616 |
| L3（+长规格串重组） | 0.9375 | 0.8673 | −0.0702 |

不仅为负，且改写越重、损失越大。

**Reflection 信号：机制有效，收益为零。** 朴素实现在全量 200 条的 347 次逐轮对照中获得 19 次改善、1 次恶化；恶化样本 `public_0087` 暴露出机制缺陷（详见 5.2）。加入停滞门控后复测 408 次对照，改为 **5 次改善、0 次恶化**。但当 M3 负责人将修复版实际接入排序器复测时，结果为**零效果**（L0 0.9620 逐位相同）——彼时基线 HitRate 已达 0.995、MTTC 2.23，绝大多数会话在停滞计数达到阈值前即已终局。

## 5. 失效分析：三层因果

### 5.1 现象层

profile 注入在所有档位均为负收益，且损失随改写强度单调放大。

### 5.2 机理层：为什么代码正确而结果更差

实现本身无缺陷——它精确执行了所声称的行为。负收益来自三个可指认的机制：

**检索侧：噪声候选挤占截断线。** 将 `comfortable`、`soft`、`fabric` 一类通用词并入 FTS5 的 OR 查询，会拉入大量弱相关候选，与真候选争夺 `CANDIDATE_POOL = 300` 的名额。这与本项目此前记录的稠密路 RRF 融合翻车是同一个失败模式：当时语义噪声把 BM25 池中 40–100 位的好候选挤出截断线，Recall@100 由 0.995 跌至 0.970。

**排序侧：弱信号与低置信轮收窄策略的负交互。** M3 的收窄策略令系统在信息不足的前两轮只返回 1 件推荐，其收益前提是首位候选的置信度足够高。而每命中一个通用词加 0.3 分的软加权，一旦把错误候选顶至首位，该轮的机会成本便从「十选一尚有余地」变为「独苗全押错」。**弱信号的危害被输出形态放大了一个量级**——这解释了为何在未改写的 L0 档已经为负。

**改写场景：噪声的相对权重被动升高。** 改写首先摧毁的是精确信号（品类解析、约束逐字命中）。精确信号衰减后，通用词的相对话语权被动上升，噪声恰在系统最脆弱时取得最大影响力。这解释了损失为何随改写强度单调放大。

同一类机制也解释了 Reflection 的初版缺陷。朴素实现将「已展示但未命中」等同于「用户已拒绝」，但本模拟器从不对展示的商品给出反馈——它只回答属性问题或命中终局。`public_0087` 即是反例：browsing 场景第 1 轮基于极少信息的猜测未命中，第 2 轮拿到新约束后排序本可将目标送回第 10 位，却因「第 1 轮展示过」被永久拉黑，落至第 11 位。修复方式是承认「未命中」只意味着「当时信息不足」，因此仅在排序确实停滞（连续 ≥2 轮无新约束且候选池 top-5 高度重合）时才启用过滤。

### 5.3 根因层：为什么任何实现都不可能成立

前述两次诊断各自只证伪了一种接法，无法回答「换权重、换门控、只在冷启动使用是否可行」。因此第三次改用信息论口径，一次性关闭整类问题。

第一步测量提升度：profile 关键词命中目标商品的概率为 0.2552，命中随机商品为 0.1463，**lift = 1.745×**。表面上存在真实信号。

**但这个数字是一个假象。** 目标商品全部取自真实购买记录，因而系统性地更热门——本项目另一项诊断已测得目标商品含 `price` 字段者占 89.0%，而全目录仅 20.8%。热门商品的详情页更长、文案更丰富，因此**任何**词命中它们的概率都更高，与是否语义匹配无关。

第二步以置换检验消除该混淆：固定同一批目标商品，仅在样本之间打乱 profile 的配对关系（用户 j 的画像对用户 i 的目标）。商品文案长度、热度、品类全部被控制：

| 配对方式 | 平均命中率 |
|---|---|
| 真实配对 profile_i × target_i | 0.2553 |
| 随机配对 profile_j × target_i | 0.2501 |
| **比值** | **1.021×**（z = +0.93，p ≈ 0.18，200 次置换，n = 199） |

差异统计上不显著。**`user_profile` 与「该用户购买了哪件商品」在本数据集上相互独立**；1.745× 几乎全部来自商品文案长度的系统性差异。

这一结论的意义在于它关闭的不是一个实现，而是一整类实现：**信号的天花板由信息量决定，而非由接入方式决定**。冷启动限定、仅接检索、仅接排序、权重扫描、按 tag 分档加权——这些方案无需再逐一尝试，因为数据中不存在可供提取的信号。诊断脚本已固化为 `scripts/profile_signal_diagnostic.py`。

### 5.4 与项目其他负结论的关系

本项目的中心发现是「瓶颈不在语义轴，而在先验轴」。M4 的结论是该论断的第三条独立证据，**但失效机理与前两条不同**，这一区分具有操作意义：

| 信号 | 失效机理 | 应采取的后续动作 |
|---|---|---|
| 稠密语义相似度 | **共线**——与逐字指纹信号同源，信息已被提取殆尽（打平局中目标相似度名次中位 81，而排序正确组为 3） | 继续寻找异质的信息源 |
| LLM listwise 精排 | **共线**——喂入命中证据后收敛至 −0.0004，规则打分器已把同一批证据榨干 | 继续寻找异质的信息源 |
| profile 软偏好 | **无信息**——变量与目标统计独立 | 停止投入 |

前两者是「信息已被别处用尽」，后者是「信息压根不存在」。将二者并列为同一类结论会导出错误的后续动作。

### 5.5 模块保留的理由

需要明确的是，M4 并非可删除的模块。`src/dialog/agent.py` 在模块顶层导入 `distill` 并在每轮无条件调用；删除 `src/memory/` 将使 `from starter.agent import Agent` 在导入阶段抛出 `ModuleNotFoundError`——这正是项目护栏脚本 `scripts/check_guards.py` 专门守护的「全队零分」故障类别。准确的表述是：**蒸馏层始终在线运行且已验证有界，profile 与 Reflection 信号被测量并保留，但未接入打分路径。**

## 6. 适用边界：该模块在什么条件下会转为正收益

上述每一项失效都有明确前提。将前提取反，即得到该模块的适用边界；这四条同时可作为在其他系统中重建该模块前的准入判据。

**其一，profile 注入要求画像与目标之间存在真实的条件依赖。** 本赛题的 `user_profile` 为合成数据且与目标独立，这一点已被证明。真实电商场景中，购买历史与下次购买之间存在真实依赖——协同过滤之所以成立正源于此。可执行的准入判据是：**先跑置换检验，仅当真实配对显著优于随机配对时才动工**。该检验约二十行代码、数分钟即可完成，成本远低于接线后跑全量 A/B，且能一次性排除整类接法。

**其二，蒸馏要求上下文确实超出预算。** 本赛题会话上限 10 轮、实测平均 2.155 轮收敛，且下游排序器消费的是结构化的 `Slot` 对象而非文本，压缩这一步没有真实需求。当会话长度足以使原始历史超出 prompt 预算，或当消费方是以文本为输入的模型时，蒸馏层即从「架构完整性」转为「承重结构」。本模块的输出长度已验证有界（0.80×），可直接迁移。

**其三，Reflection 要求存在真实的负反馈信号。** 本模拟器只有「命中终局」与「回答属性问题」两类事件，不存在「用户拒绝了这一件」。真实系统具备点击、跳过、停留时长等真负样本，届时「被拒集合的共同属性降权」这一原始设计才有可学之物。

**其四，弱信号要求「存在可救的失败」与「输出形态可容错」两个条件同时成立。** 当前基线 HitRate 已为 1.000，不存在可救的 miss；且收窄策略令早轮输出只有一个名额，弱信号一旦出错即无处藏身。当系统仍有实质失败率、且每轮返回较大的 top-k 时，同一个弱信号可以搭便车，而不必承担独占首位的风险。停滞信号同理：其触发需要至少三轮，而在平均 2.155 轮收敛的会话分布下几乎没有机会激活；在浏览型、长会话的部署中该信号将频繁生效。

## 7. 方法论结论

M4 的三次诊断构成一个递进：前两次各自证伪一种实现，第三次证伪了整个前提。由此得到两条可迁移的规则。

其一，**当同一想法的第二种实现以相同方式失败时，应当停止测试实现，转而测试前提**。逐个测试接法的代价是线性的且没有终点；测试前提的代价固定，且结论覆盖整个方案空间。

其二，**在观测数据上比较「命中目标」与「命中随机对照」时，必须确认对照组在所有与命中率相关的维度上可比**。本例中目标商品因取自真实购买记录而系统性更热门、文案更长，仅此一项即足以制造 1.745× 的虚假提升度。置换检验——固定被比较对象、仅打乱配对关系——是排除该类混淆的最小成本手段。

---

# English

## 1. Scope and deliverable

M4 owns the third of the challenge's four pillars — *self-evolution: dynamic context programming*. Concretely it delivers three things: compression of a turn-by-turn growing dialogue into compact structured context; conversion of the supplied `user_profile` into a cold-start soft preference; and cross-turn strategy signals for the decision layer.

The delivered module is three files under `src/memory/`, 150 lines in total, **with no third-party dependencies and no LLM calls**. The distillation layer runs unconditionally on every turn in the production path. The profile injection and reflection signals were **measured in full and deliberately left disconnected from the scoring path** — the evidence for that decision is the substance of this report.

## 2. Design rationale: three constraints determined every technical choice

Every choice in M4 traces back to an external constraint rather than a preference.

**Constraint 1: the official evaluation may run without network access.** The submission rules reserve that right, and our project red line requires every LLM call to have an offline fallback. Distillation therefore uses template composition rather than LLM summarisation — not as a backup to an online path, but as the only path. There is nothing to fall back from.

**Constraint 2: there is no cross-session memory problem here.** The evaluator calls `reset()` once per session, sessions are capped at ten turns, and the private set of 800 uses users and targets that do not overlap with the public set at all. The core problem that Mem0, vector databases and FAISS exist to solve — extracting, de-duplicating and recalling long-term memory across sessions — does not occur in this task. Adopting any of them would add a runtime path depending on LLM adjudication and vector search, in direct conflict with Constraint 1. All were ruled out.

**Constraint 3: the state layer was being refactored concurrently.** While M4 was being built, the M1 owner was restructuring `src/dialog/state.py` (consolidating normalisation, adding `Slot.terms`). Requesting a `DialogState` schema change at the same time would have created coordination cost and merge conflicts. Cross-turn signals therefore live in a module-level dictionary keyed by `session_id` — structurally identical to the `_usage` / `pop_usage()` pattern already accepted in `src/ranking/llm_client.py`. The cost is a little encapsulation; the benefit is zero coordination overhead.

One further judgement follows from the task mechanics: **constraint decay should be event-triggered, not turn-triggered.** Outside the Intent Override scenario the target product never changes, so decaying old constraints with elapsed turns would actively weaken the correct signal in the remaining 85% of sessions. And the moment of override is announced by the evaluator in a fixed template, so it never has to be inferred. The correct design is to listen for that event and perform one discrete state transition — not to emulate a human forgetting curve.

## 3. Implementation

| File | Lines | Responsibility |
|---|---|---|
| `distiller.py` | 33 | Compresses `DialogState` into a single bounded line, `state.distilled` |
| `lexicon.py` | 34 | Static closed-set lookup from `preference_tags` to soft-preference keywords |
| `signals.py` | 83 | Cross-turn signals: stagnation counter, previously-shown-candidate tracking |

The domain of `lexicon.py` came from enumerating all 200 public samples: `preference_tags` is a closed set of nine values (fit 163 / material 154 / comfort 144 / style 101 / durability 47 / performance 26 / warmth 18 / weather 12 / general shopping 1). The same analysis established that `summary` is a template composed from `preference_tags` and `rating_style`, that `average_prior_rating` maps one-to-one onto `rating_style`, and that `purchase_frequency` is constant across the public set. Of the five keys only `preference_tags` carries independent information, so only that key is parsed. Tags outside the table return an empty list silently, which is what the private set requires.

The reflection gate in `signals.py` deserves a note. The evaluator only checks for a hit when `override_applied` is true, and in the Intent Override scenario `state.scenario` remains `"unknown"` until the trigger utterance arrives. Counting "shown but not hit" as a negative without that distinction would permanently blacklist candidates the evaluator had not yet examined. The tracking logic is therefore gated on `prev_scenario != "unknown"`, so accumulation begins only after a turn the evaluator genuinely scored.

## 4. Measured results

**Distillation: requirement met.** Across the full 200 sessions, `state.distilled` averages 319.2 characters at turn 3 and 256.3 characters at the final turn — a ratio of **0.80×**, shrinking rather than growing. Output length scales with the number of *active constraints*, not with history length, and the `other`-first questioning policy exhausts the constraints the evaluator is willing to disclose within a few turns, so the length plateaus by construction.

**Profile injection: negative.** Wiring `lexicon.profile_soft_terms` into retrieval query expansion and into ranking as a soft weight, measured on a stratified sample (`--n 60`) across paraphrase stress levels:

| Level | Without | With | Δ |
|---|---|---|---|
| L0 (verbatim templates) | 0.9595 | 0.9519 | −0.0076 |
| L1 (phrasing rewritten) | 0.9595 | 0.9211 | −0.0384 |
| L2 (+ short constraints rewritten) | 0.9634 | 0.9018 | −0.0616 |
| L3 (+ long spec strings recomposed) | 0.9375 | 0.8673 | −0.0702 |

Not merely negative: the heavier the paraphrasing, the larger the loss.

**Reflection: mechanism sound, benefit zero.** The naive implementation produced 19 improvements against 1 regression across 347 turn-by-turn comparisons on the full set; the single regression (`public_0087`) exposed a design flaw described in §5.2. After adding a stagnation gate, a re-run over 408 comparisons gave **5 improvements and 0 regressions**. When the M3 owner then wired the fixed version into the ranker for real, the result was **no effect at all** (L0 0.9620, byte-identical). At that point the baseline stood at HitRate 0.995 and MTTC 2.23: almost every session terminates before the stagnation counter can reach its threshold.

## 5. Failure analysis: three levels of causation

### 5.1 Observation

Profile injection was negative at every stress level, and the loss grew monotonically with paraphrase severity.

### 5.2 Mechanism: why correct code produced worse results

The implementation is not defective; it does exactly what it claims. The loss comes from three identifiable mechanisms.

**Retrieval: noise candidates crowd the cut-off.** Folding generic terms such as `comfortable`, `soft` and `fabric` into the FTS5 OR query pulls in weakly related candidates that compete for the `CANDIDATE_POOL = 300` budget. This is the same failure mode this project had already recorded when RRF-fusing the dense route: semantic noise pushed good BM25 candidates from positions 40–100 past the cut-off, and Recall@100 fell from 0.995 to 0.970.

**Ranking: a weak signal interacts badly with low-confidence withholding.** The M3 withholding strategy returns exactly one product during the first two low-information turns, and its payoff depends on the top candidate being confident. A soft weight of +0.3 per matched generic term that promotes the wrong candidate turns the cost of that turn from "one of ten slots wasted" into "the only bet placed, and lost". **The output shape amplifies the harm of a weak signal by an order of magnitude** — which is why the regression appears even at L0, before any paraphrasing.

**Under paraphrase: the relative weight of noise rises passively.** Paraphrasing destroys the precise signals first — category parsing and verbatim constraint matching. As those decay, generic terms gain relative influence, so the noise acquires its greatest voice exactly when the system is most fragile. That is why the loss scales monotonically with stress level.

The same family of reasoning explains the initial reflection defect. The naive version equated "shown but not hit" with "rejected by the user", but this simulator never comments on a shown product — it either answers an attribute question or converts. `public_0087` is the counter-example: in a browsing session the turn-1 guess, made on almost no information, missed; by turn 2 the newly disclosed constraint would have returned the target to rank 10, but it had already been permanently blacklisted for having been shown, and fell to rank 11. The fix was to accept that a miss means only "not enough information yet", and to enable filtering solely when ranking has genuinely stalled — at least two consecutive turns with no new constraint and a near-identical candidate top-5.

### 5.3 Root cause: why no implementation could have worked

Each of the two diagnostics above falsified one wiring and left "try a different weight, gate or scope" open. The third diagnostic therefore changed register, from engineering to information, and closed the whole class at once.

The first measurement was a lift: profile keywords occur in the target listing with probability 0.2552 and in a random listing with probability 0.1463 — **a lift of 1.745×**. On its face, real signal.

**That number is an artefact.** Target products are drawn from genuine purchase records and are therefore systematically more popular; a separate diagnostic in this project measured that 89.0% of targets carry a `price` field against 20.8% of the catalogue. Popular products have longer, richer listings, so *any* word hits them more often, independent of relevance.

The second measurement removed the confound by permutation: holding the same target products fixed and shuffling only the pairing between profiles and sessions (user *j*'s profile against user *i*'s target). Listing length, popularity and category are all held constant.

| Pairing | Mean match rate |
|---|---|
| True pairing, profile_i × target_i | 0.2553 |
| Shuffled pairing, profile_j × target_i | 0.2501 |
| **Ratio** | **1.021×** (z = +0.93, p ≈ 0.18, 200 permutations, n = 199) |

The difference is not significant. **The user profile is statistically independent of what that user bought**, and the 1.745× lift was almost entirely a listing-length artefact.

What matters about this result is that it closes a class rather than an instance: **the ceiling on this signal is set by its information content, not by how it is wired.** Cold-start-only application, retrieval-only, ranking-only, weight sweeps, per-tag gating — none of these need to be tried, because there is no signal in the data to extract. The diagnostic is preserved as `scripts/profile_signal_diagnostic.py`.

### 5.4 Relation to the project's other negative results

This project's central finding is that the bottleneck lies on the prior axis rather than the relevance axis. M4's result is the third independent piece of evidence for it — **but its failure mechanism differs from the other two, and the distinction is operational**:

| Signal | Mechanism of failure | Correct next action |
|---|---|---|
| Dense semantic similarity | **Collinear** — same information as the verbatim fingerprint, already extracted (median similarity rank of the target is 81 inside ties, versus 3 where ranking already succeeded) | Look for a heterogeneous information source |
| LLM listwise re-ranking | **Collinear** — converges to −0.0004 once given the hit evidence; the rule scorer had already exhausted that evidence | Look for a heterogeneous information source |
| Profile soft preferences | **No information** — the variable is independent of the target | Stop investing |

The first two mean "this information is already being used elsewhere"; the third means "this information does not exist". Presenting them as one kind of result would license the wrong follow-up.

### 5.5 Why the module is retained

M4 is not a removable component. `src/dialog/agent.py` imports `distill` at module level and calls it unconditionally on every turn; deleting `src/memory/` would make `from starter.agent import Agent` raise `ModuleNotFoundError` at import time — precisely the whole-team-zero failure class that our guard script `scripts/check_guards.py` exists to prevent. The accurate description is: **the distillation layer runs continuously and is verified bounded; the profile and reflection signals are measured and retained, but not connected to scoring.**

## 6. Applicability: the conditions under which this module pays off

Each failure above has a precondition. Inverting those preconditions yields the module's applicability envelope, and equally a set of entry criteria for rebuilding it in another system.

**First, profile injection requires a genuine conditional dependence between profile and target.** In this benchmark the `user_profile` is synthetic and provably independent of the target. In a deployed commerce setting, purchase history and the next purchase *are* dependent — that dependence is exactly why collaborative filtering works. The executable entry criterion is: **run the permutation test first, and build the feature only if true pairings beat shuffled ones by a significant margin.** The test is roughly twenty lines and a few minutes, far cheaper than wiring the feature and running a full A/B, and it rules out an entire class of wirings at once.

**Second, distillation requires that the context genuinely exceeds its budget.** Here sessions are capped at ten turns, converge in 2.155 on average, and the downstream ranker consumes structured `Slot` objects rather than text, so there is no compression pressure to relieve. Once sessions are long enough for raw history to exceed a prompt budget, or once the consumer is a text-input model, the distillation layer changes from architectural completeness into load-bearing structure. Its output is already verified bounded (0.80×) and transfers directly.

**Third, reflection requires a genuine negative signal.** This simulator emits only two events — conversion, and an answer to an attribute question. It never rejects a shown product. Real systems have clicks, skips and dwell time, which are true negatives; only then does the original design — down-weighting attributes shared by a rejected slate — have anything to learn from.

**Fourth, a weak signal requires both a remaining failure rate and a fault-tolerant output shape.** The current baseline is at HitRate 1.000, so there is no miss left to rescue; and the withholding strategy leaves exactly one slot in early turns, so a weak signal that errs has nowhere to hide. Where a system still fails materially and returns a reasonably large top-k each turn, the same weak signal can ride along without having to carry the top position alone. The stagnation signal is subject to the same logic: it needs at least three turns to trigger, and at a mean of 2.155 turns to conversion it almost never gets the chance — whereas in a browsing-heavy deployment with longer sessions it would fire routinely.

## 7. Methodological conclusion

M4's three diagnostics form an escalation: the first two each falsified one implementation, the third falsified the premise. Two transferable rules follow.

First, **when the second implementation of an idea fails in the same way, stop testing implementations and test the premise.** Testing wirings one at a time costs linearly and has no natural end; testing the premise costs once and its conclusion covers the entire design space.

Second, **when comparing hit rates against a target with hit rates against a random control, verify that the control is comparable on every dimension correlated with hit rate.** Here the targets, being drawn from real purchase records, are systematically more popular and carry longer listings — that single property was enough to manufacture a 1.745× spurious lift. A permutation test, which holds the compared objects fixed and destroys only the pairing, is the cheapest available way to eliminate that class of confound.
