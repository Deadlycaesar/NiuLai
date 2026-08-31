# REPORT.md 用的 M4 素材（D / 毕永琪 · 09-01）

> 对标 [`REPORT-M2素材.md`](REPORT-M2素材.md) 的格式：**中文分析在前供队内判断，英文可直接粘贴段落在后**。
> 本文件覆盖 M4「记忆与上下文蒸馏」的技术构成、设计依据、失效机理，以及**该模块在什么条件下会转为正收益**。
> 数字均可由 [`team/experiments.md`](experiments.md) 与 [`scripts/profile_signal_diagnostic.py`](../scripts/profile_signal_diagnostic.py) 复现。
>
> ⚠️ **引用编号注意**：`experiments.md` 目前存在撞号（#20 整行重复；#21、#22 各有两行，分属 M4 与 A）。
> 本文件引用时一律**同时给编号与内容描述**，避免读者查错行。

---

## 一、模块构成与技术选型

M4 共 150 行、三个文件、**零第三方依赖**，全部为纯规则实现：

| 文件 | 职责 | 关键技术决策 |
|---|---|---|
| `src/memory/distiller.py`（33 行） | 把 `DialogState` 压成单行结构化上下文 `state.distilled` | 模板拼接而非 LLM 摘要——满足红线「LLM 调用必须有离线降级」，且它本身就是降级态 |
| `src/memory/lexicon.py`（34 行） | `preference_tags` → 软偏好关键词表 | **闭集静态查表**。取值域由 `public_set.jsonl` 实测枚举（9 值），未知 tag 静默返回空表以适配私有集 |
| `src/memory/signals.py`（83 行） | 跨轮信号：停滞计数、被拒 slate 追踪 | **按 `session_id` 索引的模块级字典**，不修改 `DialogState` schema |

**三个刻意的否定选择**，比肯定选择更能说明设计约束：

1. **不引入 Mem0 / 向量库 / FAISS。** 这类框架解决的是「跨会话长期记忆的抽取、去重与召回」，其核心循环依赖 LLM 判定与向量检索。本赛题每个 session 由 `reset()` 独立开启、上限 10 轮、私有集 800 条使用完全不同的用户——**不存在跨会话记忆这个问题**；且正式评测可能断网，LLM 驱动的记忆整合无法优雅降级。
2. **不改 `DialogState` schema。** 采用模块级字典（与 `src/ranking/llm_client.py` 的 `_usage` + `pop_usage()` 同构，是项目已接受的写法），换来两个收益：跨目录协调成本为零；不与 A 同期进行的 `state.py` 重构（`Slot.terms` 落地）产生合并冲突。
3. **衰减由事件触发，不由轮数触发。** 除 Intent Override 外，目标商品在整场会话中不变，按轮数连续衰减旧约束会在 85% 的场景里主动削弱正确信号；而 Override 的发生时刻由评测器以固定句式明示，无需推断。

---

## 二、设计依据：三条验收标准各自的实现路径

**① 蒸馏输出长度不随轮数线性膨胀。** `distill()` 的输出长度只随**当前生效约束数**增长，而非原始历史长度；叠加 `other_first` 提问策略几轮即把评测器可吐露的约束问尽，长度天然封顶。全量 200 条实测：**第 3 轮均值 319.2 字符，末轮均值 256.3 字符，比值 0.80×——不增反减**。此项达成。

**② profile 注入改善 browsing 场景。** 设计假设是：`preference_tags` 在 `reset()` 时即可获得，早于任何用户消息，因此可作为 browsing 冷启动的软偏好，弥补第 1 轮约束为空的信息真空。实现为 `lexicon.py` 的静态词表，供检索查询扩展与排序软加权两处消费。**此项未达成，且经证明在本数据集上不可能达成**——见第三节。

**③ Reflection 信号改变下一轮排序。** brief 原文要求 EAR 式「被拒 slate 的共同属性值降权」。实现时做了一次**有依据的偏离**：本模拟器从不对展示的商品给出拒绝反馈（用户只回答属性问题或命中终局），不存在「被拒」这一事件，无法抽取「共同属性」。故改为追踪「已展示但未命中」的 `parent_asin` 集合。此项在机制层达成、在收益层为零，见 3.4。

---

## 三、为什么接入后分数变差：三层因果

### 3.1 现象（实验 #21「M4 补充诊断」）

把 `lexicon.profile_soft_terms` 接入 `retriever._query_terms`（查询扩展）与 `ranker.score`（+0.3 软权重），跑 `paraphrase_stress.py --n 60` 分层抽样对照：

| 档位 | 不接入 | 接入后 | Δ |
|---|---|---|---|
| L0（原始话术） | 0.9595 | **0.9519** | −0.0076 |
| L1（句式改写） | 0.9595 | **0.9211** | −0.0384 |
| L2（+短约束改写） | 0.9634 | **0.9018** | −0.0616 |
| L3（+长规格串重组） | 0.9375 | **0.8673** | −0.0702 |

**不仅为负，且改写越重、损失越大。**

### 3.2 机理（为什么代码正确、结果却更差）

代码本身无缺陷——它精确实现了所声称的行为。变差来自三个可指认的机制：

**(a) 检索侧：噪声候选挤占截断线。** 把 `comfortable / soft / fabric` 一类通用词并入 FTS5 的 OR 查询，会拉入大量弱相关候选，与真候选争夺 `CANDIDATE_POOL=300` 的名额。这与实验 #6a 记录的 RRF 稠密融合翻车是**同一个失败模式**（稠密查询的语义噪声把 BM25 池 40–100 位的好候选挤出截断线，Recall@100 由 0.995 跌至 0.970）。

**(b) 排序侧：弱信号与「低置信轮收窄」策略的负交互。** C-T3（实验 #11）令系统在信息不足的前两轮**只返回 1 件推荐**。该策略的收益前提是 top-1 置信度足够高；而 +0.3 的软加权一旦把错误候选顶至首位，该轮的机会成本便从「10 选 1 尚有余地」变为「独苗全押错」。**弱信号的危害被输出形态放大了一个量级**——这解释了为何 L0 就已经为负。

**(c) 改写场景下噪声的相对权重被动升高。** 改写首先摧毁的是精确信号（`state.category` 解析、约束逐字命中）。精确信号衰减后，通用词的相对权重被动上升，噪声恰在系统最脆弱时获得最大话语权。这解释了损失为何随改写强度单调放大。

### 3.3 根因（为什么任何实现都不可能成立）——实验 #22

前两次诊断（#13、#21）各自只证伪了一种接法，无法回答「换权重／换门控／只在冷启动用是否可行」。故第三次改用信息论口径，一次性关闭整类问题。

**第一步**测提升度 lift = P(profile 词命中目标商品) / P(命中随机商品) = **1.745×**（0.2552 vs 0.1463），看似存在真实信号。

**关键在于识破一个混淆**：目标商品全部取自真实购买记录，是热门商品（实验 #10a：目标有 `price` 字段者占 89.0%，全目录仅 20.8%），**其文案系统性更长更丰富，因而任何词都更容易命中**——这与「是否匹配」无关。

**第二步做置换检验**：固定同一批目标商品，仅将 profile 在样本间打乱配对（用户 j 的画像 vs 用户 i 的目标）。商品文案长度、热度、品类全部被控制住：

| 配对方式 | 平均命中率 |
|---|---|
| 真实配对 profile_i × target_i | 0.2553 |
| 随机配对 profile_j × target_i | 0.2501 |
| **比值** | **1.021×**（z = +0.93，p ≈ 0.18，200 次置换，n = 199） |

**统计上不显著。** 那个 1.745× 几乎全部是「目标商品文案更长」的假象。

**结论：`user_profile` 与「该用户购买了哪件商品」在本数据集上统计独立。** 天花板由信息量决定，不由接法决定——冷启动限定、只接检索、只接排序、扫权重、按 tag 分档等全部无需再试。脚本固化为 [`scripts/profile_signal_diagnostic.py`](../scripts/profile_signal_diagnostic.py)，对标 B 的 `dense_signal_diagnostic.py`。

### 3.4 Reflection 信号的两次结论

- **实验 #14**：朴素版（scenario 明确即拉黑历史展示项）在全量 200 条的 347 次逐轮对照中 **19 次改善 / 1 次恶化**。恶化样本为 `public_0087`（DEMO 讲解案例）：browsing 第 1 轮弱信息猜测未命中，第 2 轮拿到新约束后排序本可将其送回 rank 10，却因「第 1 轮展示过」被永久拉黑，落至 rank 11。**根因**：本模拟器不存在真实拒绝信号，「展示未命中」仅代表「当时信息不足」。修复为 `actionable_rejections(min_stagnant=2)`——仅在连续 ≥2 轮无新约束且候选池 top-5 高度重合时启用。复测 408 次对照，**5 次改善 / 0 次恶化**。
- **实验 #18**：C 将修复版实际接入 `ranker.py` 复测，**零效果**（L0 0.9620 逐位相同）。原因是该次复测时基线 HitRate 已达 0.995、MTTC 2.23，绝大多数会话在 `stagnant_turns` 累积到阈值前即已终局——**信号正确，但没有它发挥作用的场景**。（此后基线进一步升至 HitRate 1.000、MTTC 2.155，可发挥空间只会更小，该结论方向不变。）

---

## 四、置于整个项目中看：三个负结论的失效原因并不相同

本项目的中心发现是「瓶颈不在语义轴，而在先验轴」。M4 的结论是该论断的**第三条独立证据**，但**失效机理与前两条不同**，这一区分对结论的可迁移性至关重要：

| 信号 | 结论 | 失效机理 |
|---|---|---|
| 稠密语义相似度（实验 #7） | 打平局中无区分度（目标 sim 名次中位 81，排对组为 3） | **共线**——与逐字指纹信号同源，信息已被提取殆尽 |
| LLM listwise 精排（C-T9） | 喂入命中证据后收敛至 −0.0004 | **共线**——规则打分器已把同一批证据榨干，LLM 至多打平 |
| profile 软偏好（实验 #22） | 置换检验 1.021×，p ≈ 0.18 | **无信息**——变量与目标统计独立，不存在可提取的信号 |

前两者是「信息已被别处用尽」，可通过更换信息源改善；后者是「信息压根不存在」，任何工程手段都无法改善。**把二者混为一谈会导出错误的后续动作**：前者值得继续寻找新信号源，后者应当立即停止投入。

同时需要说明：M4 并非可删除的模块。`src/dialog/agent.py` 在模块顶层 `from src.memory.distiller import distill` 并在每轮无条件调用，删除 `src/memory/` 将导致 `from starter.agent import Agent` 在 import 阶段抛 `ModuleNotFoundError`——即 `scripts/check_guards.py` 专门守护的「全队零分」故障类别。**蒸馏层始终在线运行，只是其输出当前仅有一个被默认关闭的消费方（`ranker._llm_rerank`）。**

---

## 五、该模块在什么条件下会转为正收益

上述每一项失效都有明确前提；将其取反，即得到该模块的适用边界。这四条同时是**可执行的准入判据**：

**① profile 注入需要画像与目标之间存在真实条件依赖。**
本赛题的 `user_profile` 为合成数据且与目标独立（已证）。真实电商场景中购买历史与下次购买之间存在真实依赖——协同过滤之所以有效正源于此。**准入判据：先跑置换检验，真实配对/随机配对比值显著大于 1 才动工。** 该检验成本约 20 行代码、数分钟，远低于接线后跑全量 A/B 的代价，且能一次性排除整类接法。

**② 蒸馏需要上下文确实超出预算。**
本赛题会话上限 10 轮、实测 MTTC 2.155 轮，且下游排序器消费的是结构化 `Slot` 对象而非文本，压缩这一步没有真实需求。**当会话长度足以让原始历史超出 prompt 预算、或消费方是以文本为输入的 LLM 时**，蒸馏层即从「架构完整性」转为「承重结构」。本模块的输出长度已验证为有界（0.80×），可直接迁移。

**③ Reflection 需要真实的负反馈信号。**
本模拟器只有「命中终局」与「回答属性问题」两类事件，不存在「用户拒绝了这一件」。真实系统具备点击/跳过/停留时长等真负样本，届时 EAR 式的「被拒 slate 共同属性降权」才有可学之物——而这正是 brief 原始设计的形态。

**④ 弱信号需要「有可救的失败」与「可容错的输出形态」两个条件同时成立。**
当前基线 HitRate 已为 1.000，不存在可救的 miss；且 `EARLY_TOPK=1` 令早轮输出只有一个名额，弱信号一旦出错即无处藏身。**当系统仍有实质失败率、且每轮返回 top-k（k 较大）时**，同一个弱信号可以「搭便车」而不必承担独占首位的风险。停滞信号同理：`min_stagnant=2` 需要至少 3 轮才可能触发，在 MTTC 2.155 的会话分布下几乎无机会激活；**在浏览型、长会话的部署中该信号将频繁生效**。

---

## 六、方法论上的可迁移结论

M4 的三次诊断构成一个递进：#13 与 #21 各自证伪一种**实现**，#22 证伪了整个**前提**。其中的一般规则是：

> **当同一想法的第二种实现以相同方式失败时，应当停止测试实现，转而测试前提。**

以及一条更具体的统计陷阱警示：

> **在观测数据上比较「命中目标」与「命中随机对照」时，必须确认对照组在与命中率相关的所有维度上可比。** 本例中目标商品因取自真实购买记录而系统性更热门、文案更长，仅此一项即可制造 1.745× 的虚假提升度——置换检验（固定被比较对象、仅打乱配对关系）是排除该类混淆的最小成本手段。

---

# 英文可直接粘贴段落

## 素材 A：§2 架构表 M4 行（3 句）

```markdown
**M4 — memory (`src/memory/`, 150 lines, no third-party dependencies).** A template-based
distiller compresses `DialogState` into a single bounded line (`state.distilled`), a static
closed-set lexicon maps the five-key `user_profile` onto soft-preference keywords, and a
session-scoped signal store tracks stagnation and previously-shown candidates. The distiller runs
on every turn; the profile and reflection signals are measured but deliberately not wired into the
scoring path, for the reason given in §6.
```

## 素材 B：§6「我们否决了什么」的扩充（核心价值在这）

```markdown
**Profile-based personalisation: we closed the question, not just the implementation.** Two wiring
attempts failed — the lexicon rescued none of the remaining misses, and wired into retrieval and
ranking it *cost* 0.008 on the clean public set and up to 0.070 under paraphrase stress. Each test
falsified one implementation and left "try a different weight" open. So we stopped testing
implementations and tested the premise. The naive statistic looked promising: profile keywords hit
the target listing 1.745x more often than a random listing. That number is an artefact. Target
products come from real purchase records, so they are systematically more popular and carry longer
listings; any word hits them more often, regardless of relevance. Holding the products fixed and
shuffling profiles between sessions — same items, same text lengths, only the pairing destroyed —
gives 1.021x (z = +0.93, p ~ 0.18, 200 permutations). The user profile is statistically independent
of what the user bought. No weighting scheme, gating rule, or cold-start restriction can extract a
signal that is not there, which is why we stopped rather than tuned.
```

## 素材 C：§6 或 §8 —— 三个负结论的机理不同（建议单独成段）

```markdown
Our three negative results are not the same result three times. Dense similarity and LLM re-ranking
failed by *collinearity*: they are driven by the same constraint information the verbatim
fingerprint already extracts, so they add nothing where it matters (median similarity rank 81 inside
ties, versus 3 where ranking already succeeded). Profile preferences failed by *absence of
information*: the variable is independent of the target. The distinction is operational — a
collinear signal justifies looking for a different information source; an absent one justifies
stopping.
```

## 素材 D：§8 Limitations 追加一条（模块的适用边界）

```markdown
**Our memory layer is correct for a setting this benchmark does not have.** Distillation matters
when raw history exceeds the prompt budget; sessions here converge in 2.155 turns and the ranker
consumes structured slots, not text. Reflection needs a genuine negative signal; this simulator
never rejects a shown product, it only answers or converts. Personalisation needs a profile
conditioned on the target; here it is provably independent. Each precondition is ordinary in a
deployed assistant and absent in this benchmark, so we ship the layer running, measured and
disconnected from scoring rather than delete it — and we state the entry criterion we would apply
before rebuilding it elsewhere: run the permutation test first, and build the feature only if real
pairings beat shuffled ones by a significant margin.
```

## 素材 E：数字速查（全部可复现）

| 数字 | 含义 | 出处 |
|---|---|---|
| 0.80× | 蒸馏输出长度 末轮/第 3 轮（256.3 / 319.2 字符，全量 200） | 验收标准① |
| 1.745× → **1.021×** | 朴素 lift → 置换检验后（z=+0.93，p≈0.18，n=199，200 次置换） | 实验 #22 ／ `scripts/profile_signal_diagnostic.py` |
| −0.0076 / −0.0702 | 接入 lexicon 后 L0 / L3 的分数变化（`--n 60` 抽样） | 实验 #21 |
| 19↑1↓ → **5↑0↓** | Reflection 朴素版 → 停滞门控版（全量逐轮对照 347 / 408 次） | 实验 #14 |
| 零效果 | `actionable_rejections` 实际接入 ranker 的结果（L0 0.9620 逐位相同） | 实验 #18（C 复测） |
| 89.0% vs 20.8% | 目标商品 vs 全目录 有 price 字段占比（1.745× 混淆的成因） | 实验 #10a |

## 引用口径提醒（别写歪的三处）

1. **实验 #21 的分数是 `--n 60` 分层抽样**，与全量 200 条口径不可直接比较；结论看方向与单调性，不看绝对值。
2. **1.021× 不等于「profile 有 2% 的用」**。p ≈ 0.18 意味着该差异与零无法区分，正确表述是「未能拒绝独立性假设」。
3. **不要写成「M4 被移除」或「M4 未使用」**。`distill()` 每轮无条件执行，`agent.py` 顶层 import 它；删除该模块会使 `from starter.agent import Agent` 抛 `ModuleNotFoundError`。准确表述是「产出被测量并保留，但未接入打分路径」。
