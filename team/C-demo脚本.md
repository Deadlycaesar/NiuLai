# Demo 视频脚本（C 主责 · B 协助 · 分工计划 §5）

> 实测时长 **3 分 19 秒**（465 词 @140 词/分）。观众是评委，不是队友——他们没读过我们的代码，也不欠我们耐心。
>
> ✅ **口播语言已定（T-018）：英文口播 + 英文字幕。**
> 讲解词做成**中英对照**：`EN` 是照着念的原文，**同时直接当字幕文案**（不用另写一份）；
> 中文只是给我们自己看的对照，不出现在视频里。画面上所有图表已全部英文化。
>
> 与 [DEMO.md](DEMO.md) 的区别：那份是队内开会的操作手册（跑命令、看数字）；这份是**对外叙事**。
>
> 评分权重提醒：Technical Execution 35% + Innovation 20% 都是人评，加起来 **55%**。
> TechnicalScore 只是 Technical Execution 的一个客观输入（官方 commit `3407835` 专门澄清过）。
> 所以这三分钟的目标不是把 0.9466 念出来，而是让评委相信**这个数字背后有方法**。

## 口播与字幕规范

- **语速**：英文舒适口播约 **130–150 词/分钟**。每幕标了词数，按 140 估算。
- **写法**：短句、一句一个意思、避开长从句和绕口词。**宁可多一句，不要长一句。**
- **字幕**：直接用 `EN` 原文，一行 ≤ 42 字符，按句断行。
- **数字**：全片**只口播三组** —— `81 vs 3`、`570×`、`4.3×`。其余全部靠画面。
  （@BestBucky 审阅意见：原稿 50 秒内 11 个数字，每 4.5 秒一个，观众会从"听懂"掉进"记不住"。）
- **念错就重录那一句**，别将就——英文口播的容错比中文低，而字幕会把错误固定下来。

---

## 一句话主张（全片围绕这句）

> **EN** — *Better language understanding didn't improve our ranking. It turned out to matter somewhere else entirely.*
>
> 中文对照：更懂语言并没有改善我们的排序——它的作用完全在别的地方。
>
> ⚠️ **原稿是** *"We didn't try to understand language better. We found that language wasn't the bottleneck."*
> @BestBucky 在 T-025 指出它与 REPORT §5 直接矛盾（§5：改写场景下语义是唯一能救回逐字信号的东西；
> 实验 33 L4 规则 0.8486 → 加 LLM **0.9551**，是全项目单项最大的鲁棒性收益）。
> 那句话只在**排序**这一维成立。现稿第一句准确、第二句埋钩子，**幕 5 已补还账句**。

---

## 幕 1 · 问题与基线（0:00–0:23 · 54 词）

**画面**：`AGENT_IMPL=baseline python3 scripts/trace_session.py --id public_0007`

> **EN**
> "Find the one product a shopper has in mind. Fifty thousand items. Ten turns.
> Here is the official baseline. It never asks a question.
> So the shopper says: *ask me about one specific attribute.*
> And the baseline searches for **that complaint**.
> Top results: cycling shorts. Halloween socks.
> It scores zero point one zero seven."

中文对照：从 5 万件商品里找到用户心里想的那一件，10 轮对话。这是官方基线——它从不提问，
于是用户回一句"你问我一个具体属性吧"，基线**把这句抱怨本身当搜索词**，
top-10 变成自行车裤和万圣节袜子。它得 0.107。

> ⏱ 严格 30 秒，**但不要砍掉**。@BestBucky 的意见：这是全片唯一让观众看见"失败长什么样"的地方；
> 没有那条自行车裤和万圣节袜子，**0.9466 就是一个没有标尺的数字**。30 秒买一个参照系很便宜。
>
> 🗣 `zero point one zero seven` 逐位念，比 "point one oh seven" 清楚。

---

## 幕 2 · 同一条会话，我们的版本（0:23–0:53 · 70 词）

**画面**：`python3 scripts/trace_session.py --id public_0007`

```
Turn 1  User:  I'm looking for Tees & Blouses Tunics, but I'm still exploring.
        Agent: Let's start with Tees & Blouses Tunics. The closest single match…
               is there anything else that matters to you?

Turn 2  User:  For that, what matters is: polyester; 75% Polyester, 20% Rayon, 5% Spandex.
        Agent: Got it — polyester and 75% Polyester, 20% Rayon, 5% Spandex.
               That points me to RITERA Plus Size Tops…            ✅ rank 1
```

> **EN**
> "Same session. Our agent.
> The ordinary parts we did too — notes across turns, and every turn it both asks and recommends.
> The part that matters is this one.
> We take the shopper's **exact words**, and look for them **verbatim** inside product listings.
> Because the simulated shopper's requirements are copied from the target product's own page.
> A string like *seventy-five percent polyester* appears on almost nothing else.
> It is a fingerprint."

中文对照：同一条会话，我们的 agent。常规部分我们都做了——跨轮记笔记、每轮既提问又推荐。
真正承重的是这一句：**拿用户的原话去商品详情里找一字不差的出现**。
因为模拟用户说的要求，本来就是从目标商品详情页里抄出来的。
`75% Polyester` 这种长串全目录几乎只有一件商品有——**近乎指纹**。

> ⚠️ @BestBucky 审阅意见（已采纳）：前两点"记事本""每轮既问又推"**是任何及格队伍都会做的事**，
> 不构成差异化，合并成一句带过；真正承重的是"逐字指纹"，因为幕 3 开头直接接在它上面。
> 省下的 10–15 秒够我们既不砍幕 1 也不砍幕 4②。
>
> 🗣 数字只念 `seventy-five percent polyester`，不要念整串成分表。

---

## 幕 3 · 洞察：瓶颈不在语义（0:53–1:46 · 124 词）

> 全片核心，Innovation 分的落点。**不要跳过。**

**画面 A**：终端里 rank 4–10 的打平局
**画面 B**：[`assets/prior-axis.svg`](assets/prior-axis.svg)（1920×1080 原生，全屏）

> **EN**
> "Fingerprints got us to point eight six. Then we hit a wall.
> Forty-four sessions where the target was inside the top ten — but ranked fourth to tenth.
> Every requirement matched. The scores tied.
> We tried semantic similarity. It did not help.
> **When we ranked correctly, semantic similarity put the target around third.
> Inside the ties, the same signal dropped to eighty-first.**
> Both signals are driven by the same information.
> So we changed the question. Not *which product matches this sentence* —
> but **which product a real person is more likely to have actually bought**.
> Review counts differ by **five hundred and seventy times**. Having a price, by **four point three**.
> These were sitting in the data. Nobody used them.
> That solved most of the ties."

中文对照：指纹匹配把我们带到 0.86 然后卡住——44 条会话目标进了 top-10 但排在 4 到 10 名，
所有约束都命中、分数打平、排不出先后。试了语义相似度，没用，而且诊断很干净：
**排对了的时候语义把目标排在第 3 名，排不开的打平局里同一个信号跌到第 81 名。**
语义和指纹同源。于是我们换了个问法——不问"哪件更匹配这句话"，
改问"**哪件更可能是真人真的会买的**"。评论数差 570 倍，有没有价格差 4.3 倍。
这两条信号一直躺在数据里没人用。加进去之后打平局绝大多数直接解决。

> 🗣 三处念法：`point eight six`（0.86）／`eighty-first`（第 81）／
> `five hundred and seventy times`（570×）。**全幕只口播这三组数字**，其余靠画面。

---

## 幕 4 · 两个反直觉的决定（1:46–2:43 · 133 词）

**① 我们找到一个技巧，量化了它，然后删掉了它**

**画面**：[`assets/withholding-ledger.svg`](assets/withholding-ledger.svg)（1920×1080 原生，全屏）

> **EN**
> "A hit ends the session — and locks in that turn's rank.
> So converting at turn one in seventh place is **worse** than converting at turn two in first place.
> Thirty-one sessions were stuck in exactly that trade. So we showed **one** product instead of ten
> on the early turns. It was worth almost three points.
> Then we **removed** it. Showing a shopper a single product is not a storefront.
> And removing it cost us nothing in reach — the same hit rate at every paraphrase level,
> and the agent actually got **faster**."

中文对照：命中即终局，并锁死那一轮的名次。所以"第 1 轮第 7 名"比"第 2 轮第 1 名"更差。
我们有 31 条会话正卡在这个亏损交易上，于是头几轮只推 **1 件**，值将近 3 分。
**然后我们把它删了**——只给顾客看一件商品，那不叫商店。
而且删掉没有损失任何"找得到"的能力：五个改写档命中率一档没掉，agent 反而更快了。

> 📌 **改稿依据（08-31）**：账本图一帧不用改——它从"战果"变成了"弃权的证据"。
> 实测：撤销后五档 HitRate 逐档完全不变、MTTC 2.155→1.920，代价 100% 落在 MRR。
> 原理没丢，只是搬到了检索侧（何时引入语义候选，而非何时少展示），见 REPORT §5 与实验 40。

**② 我们定了一条停止准则**

> **EN**
> "One more. While tuning, we found the score kept rising as we pushed a weight higher.
> A score that never stops rising is an **over-fitting alarm**, not a win.
> So we set a rule: keep a change only if **all three difficulty buckets improve together**.
> At weight two, all three improved. At weight three, easy went up and medium went down. We stopped."

中文对照：调参时发现某个权重一直调高、分数还在涨。**分数一直涨不见顶本身就是过拟合的警报**，
不是好事。所以定了条准则：**只取 easy/medium/hard 三个难度桶齐涨的最大值**。
权重 2 三桶齐涨，收；权重 3 时 easy 涨了但 medium 掉了，止步。

> ⚠️ @BestBucky 审阅意见（已采纳）：原稿标题"我们刻意没要更高的分"是**一句需要辩护的自夸**，
> 容易被听成"你们没优化到位"。改成"我们定了一条停止准则"后，它变成
> **一条不需要辩护的方法陈述**，还自动把"分数还在涨"从遗憾变成证据。
> 这幕是全片唯一让评委看到我们理解公私集差异的地方，**不能砍**。

---

## 幕 5 · 诚实与鲁棒（2:43–3:19 · 84 词）

> **EN**
> "Three more things, quickly.
> We tested an LLM re-ranker. It made results **worse** — and we kept that finding in the log.
> The organizers said the shopper's wording may be paraphrased.
> The public set cannot show that, so we measured it ourselves.
> **And that is where the language model earned its place** — not in ranking products,
> but in understanding a shopper who words things differently.
> And of the thirty-eight sessions we do not rank first, **seven are provably impossible** —
> identical intent cards, identical dialogue. One target has forty-six twins.
> The other thirty-one are the price of showing ten products instead of one.
> We measured that price, and we chose to pay it.
> Two hundred sessions in ten seconds. The model layer only wakes when the rules fail —
> on the public set, it never fires once. Take away the network, and the score does not move."

> ✅ **配置锁已解除（08-31）**：原句 "No dependencies. No network. No API cost." 在 `LLM_PARSE=1`
> 成为默认后不再成立，已改写。新句子更强也更准——它陈述的是一个可验证的事实：
> 公开卷上解析模型 `llm_calls = 0`、分数与纯规则逐位相同，断网时熔断退回规则路径，headline 不变。
> "离线"从产品卖点降级为对计分环境的合规适配（`docs/submission_rules.md:59-64` 允许禁网计分）。
>
> ✅ **已重算（08-31，定稿配置）**：未排第 1 = **38** 条。逐会话对照两档确认了一个漂亮的对称——
> 两档都排不到第 1 的恰好 **7** 条（`public_0020/0076/0083/0099/0144/0145/0172`，孪生不可分，与配置无关），
> 仅因撤销藏牌而掉出第 1 的恰好 **31** 条，**与本片幕 4 里那"31 条卡在亏损交易上的会话"是同一批**。
> 幕 4 说我们删掉了那个技巧，幕 5 报出删掉它的确切代价——两幕由同一个数字缝合，且可复现。

中文对照：快讲三件事。我们测了 LLM 精排，**结果是变差**，这个结论留在了实验记录里。
官方说过用户话术可能被改写，公开集测不出来，所以我们自己写了压力测试去量它。
**而语言模型的价值就在那里显现了**——不是给商品排序，是听懂一个换了说法的用户。
38 条没排第 1 的会话里，**7 条是可证明不可能的**——意图卡相同、生成的对话一字不差，
其中一条有 46 个孪生商品。**另外 31 条，正是"摆 10 件而不是 1 件"的代价——
我们量过这个价钱，然后选择付它。**
200 条会话 10 秒跑完。模型层只在规则失手时醒来——公开集上它一次都没触发过。
把网线拔掉，分数不动。

> 🗣 原稿用的 `information-theoretically impossible` 太长、不好念，
> 已换成 **`provably impossible`**——意思不减，口播顺畅。

---

## 明确不放进视频的东西

三分钟里每一秒都该留给**推分数**或**证方法**的内容。以下有价值但不进片：

- **@BestBucky 的置换检验**（profile 信号 1.021× / p≈0.18）——他自己说的：
  "不用往视频里塞，它已经在 `REPORT.md` §6 里了，而且它不推分数。
  **别为了照顾每个人的工作而牺牲叙事密度。**"
- 稠密向量路的实现细节、三层解析防线的层间结构、成本披露的完整表格——全部留给报告。

---

## 拍摄清单

| 项 | 说明 |
|---|---|
| 口播 | **英文**。先通读三遍再录；每幕单独录，念错就重录那一句 |
| 字幕 | **英文**，直接用各幕的 `EN` 原文；一行 ≤ 42 字符，按句断行 |
| 终端 | 字体调大、窗口拉宽（top-10 一行较长）；深色主题 |
| 必跑命令 | 幕 1/2 的两条 `trace_session.py`；其余用图，别在镜头前等 loading |
| 需要做的图 | ✅ 全部完成，均已渲染验收：幕 3 [`prior-axis.svg`](assets/prior-axis.svg)　幕 4① [`withholding-ledger.svg`](assets/withholding-ledger.svg) |
| **图的验收方法** | **必须整张渲染出来看，不能只看代码。** 首版就因为没看全，`6,846` 与 `570×`、`89.0%` 与 `4.3×` 两处数字重叠、底部结论超出画布右边被截断——从源码上完全看不出来。命令：`qlmanage -t -s 2400 -o <目录> <svg>` |
| 数字核对 | 录制前跑一次 `python3 -m evaluator.local_evaluator` 确认仍是 **0.9466** |
| 时长 | 见下方「时长与删减日志」。**官方对视频时长无任何规定**——`competition_specification` 关于视频只有一句 "One demonstrated multi-turn session"。3 分钟是我们自己定的目标 |
| 平台 | YouTube 公开（分工计划 §5） |

## 时长与删减日志

**官方无时长要求**：`docs/competition_specification.md` 里关于视频只有一句
"One demonstrated multi-turn session"，没有分钟数、没有格式规定。所以 3 分钟是**我们自己的目标**，
超一点不违规。真正的约束是评委的注意力——他们要看很多份。

> ⚠️ **@陈智龙 注册 Devpost 时请确认平台自身有没有时长上限**，那个才是硬约束。

**首版实测 487 词 ≈ 3 分 29 秒**，超目标 29 秒。按 @BestBucky 的原则
（不砍幕 1、不砍幕 4②）只做**同义压缩**，不删任何论点：

| 位置 | 原句 | 改为 | 省 |
|---|---|---|---|
| 幕 2 | "it keeps notes across turns" | "notes across turns" | 2 词 |
| 幕 3 | "Every stated requirement matched. The scores tied. **Nothing left to break the tie.**" | 前两句（三句说一件事） | 6 词 |
| 幕 3 | "It did not help **— and the diagnostic is clean**." | "It did not help." | 6 词 |
| 幕 3 | "**Semantic and fingerprint** signals are driven by the same information." | "**Both** signals are…" | 2 词 |
| 幕 5 | "The public set cannot reveal that, **so we built a stress harness and** measured it ourselves." | "…cannot show that, so we measured it ourselves." | 5 词 |
| 幕 5 | "identical **generated** dialogue" | "identical dialogue" | 1 词 |

**压缩后 465 词 ≈ 3 分 19 秒**，仍超自定目标 19 秒。**到此为止不再压**——
再砍就要开始删论点了，而官方并无时长限制。全部改动都是同义压缩，一个论点没删；
若录制时觉得某句太赶，上表右栏就是原句，直接还原即可。

**实测分幕时长**（@140 词/分）：

| 幕 | 词数 | 时长 | 累计 |
|---|---|---|---|
| 1 问题与基线 | 54 | 0:23 | 0:23 |
| 2 我们的版本 | 70 | 0:30 | 0:53 |
| 3 **洞察（核心）** | 124 | **0:53** | 1:46 |
| 4① 藏牌 | 70 | 0:30 | 2:16 |
| 4② 停止准则 | 63 | 0:27 | 2:43 |
| 5 诚实与鲁棒 | 84 | 0:36 | **3:19** |

幕 3 占全片 27% 的时长——**这是刻意的**，它是唯一的 Innovation 落点。

---

## 开录前：一键预检（实跑验证过，2026-08-30）

```bash
cd "/Users/lyx/Project/TikTok TechJam/NiuLai"
python3 -m evaluator.local_evaluator | grep technical_score   # 必须是 0.9466
python3 scripts/check_guards.py                                # 必须全绿
```

## 幕 1 的命令要截断，否则刷屏

基线跑满 10 轮 = **152 行输出**，录进去是一面墙。用这条只放到第 2 轮结束（**39 行，一屏刚好**）：

```bash
AGENT_IMPL=baseline python3 scripts/trace_session.py --id public_0007 | sed -n '1,/第 3 轮/p' | sed '$d'
```

画面上会看到 badcase 的完整弧线：第 1 轮返回的还像样（都是女式上衣），
第 2 轮拿"你问我一个具体属性吧"这句抱怨当搜索词后，top-10 直接崩成
**自行车裤 / 万圣节袜子 / 束腰马甲 / 鼻环** —— 讲解词里点名的那几样都在。

## 幕 2 的命令不用截断

```bash
python3 scripts/trace_session.py --id public_0007
```

我们的版本只有 **22 行**，两轮命中，天然适合上镜。

## 录制顺序建议

| 步 | 内容 | 时长 |
|---|---|---|
| 1 | 幕 1 终端（上面那条截断命令） | 0:23 |
| 2 | 幕 2 终端 | 0:30 |
| 3 | 幕 3 图 [`assets/prior-axis.svg`](assets/prior-axis.svg) 全屏 | 0:53 |
| 4 | 幕 4① 图 [`assets/withholding-ledger.svg`](assets/withholding-ledger.svg) 全屏 | 0:30 |
| 5 | 幕 4② 无画面需求，可停在上图或放 experiments.md 截图 | 0:27 |
| 6 | 幕 5 无画面需求，可回到终端跑一次全量（10 秒出分，收尾很有力） | 0:36 |

**幕 5 的画面建议**：现场跑 `python3 -m evaluator.local_evaluator`，
10 秒出分这件事本身就是"零依赖、零网络"最好的证据——比念出来有说服力。

## 录完之后

1. 传 YouTube 设为**公开**（分工计划 §5）
2. 把链接给 @陈智龙 填 README 的 `TODO(A)` 和 Devpost
3. 顺手在留言板回一句，让大家知道最后一块交付物到位了

---

## 📹 录制方案 B（已选定）：PPT + 真终端，分 3 段录

> **核心：不要一镜到底。** 分段录 → 剪辑时拼接，"切窗口"这个动作就不存在了。
> 每段可以单独重录，念错一句不用从头再来。

### 分段表

| 段 | 幕 | 画面 | 时长 | 素材 |
|---|---|---|---|---|
| **① 终端** | 幕 1 + 幕 2 | 真终端，跑两条命令 | 0:53 | 见下方命令 |
| **② 幻灯** | 片头 + 幕 3 + 幕 4① + 幕 4② | PPT 全屏放映 | 1:35 | `team/assets/png/` 四张 PNG |
| **③ 终端 + 片尾** | 幕 5 | 真终端跑全量 → 切片尾卡 | 0:36 | 现场跑评测 |

**顺序说明**：成片顺序是 `片头卡 → 段① → 幕3/幕4 → 段③`。
所以段②录两次（片头单独一小段、幕3/4 一段），或者录成一整段后在剪辑里切开。
**建议后者**——PPT 放映时按空格翻页，一气呵成，剪辑时在翻页处切一刀就行。

### 录前准备（这几条不做，八成要重录）

```
□ 关通知：控制中心 → 专注模式 → 勿扰（录到通知弹窗必重录）
□ 终端字号调到 16–18pt，窗口拉宽到一行能放下完整商品标题
□ 终端配色用深色（和 PNG 卡的 #0E1512 接近，切换时不刺眼）
□ 命令先跑一遍留在 scrollback 里，录的时候用 ↑ 调出来 —— 别在镜头前打字
□ PPT 里四张 PNG 各占一整页，不要加标题栏/页码/公司模板
□ 屏幕分辨率设成 1920×1080（否则 PNG 会被缩放，字发虚）
□ QuickTime → 新建屏幕录制 → 麦克风选内建，先录 10 秒回放试音量
```

### 段① 的两条命令（先跑一遍留在 scrollback）

```bash
# 幕 1 —— 必须截断，跑满 10 轮是 152 行，会刷屏
AGENT_IMPL=baseline python3 scripts/trace_session.py --id public_0007 | sed -n '1,/第 3 轮/p' | sed '$d'

# 幕 2 —— 不用截断，只有 22 行
python3 scripts/trace_session.py --id public_0007
```

### 段③ 的命令

```bash
python3 -m evaluator.local_evaluator
```

念幕 5 的时候让它在后台跑，**"Two hundred sessions in ten seconds" 这句话出口时正好出分** ——
这是全片说服力最强的一个瞬间，比念数字有用得多。跑完切片尾卡收尾。

### 剪辑

**iMovie 就够**（Mac 自带）：把 3 段拖进时间线，按顺序排好，段与段之间**不要加转场**
（技术 demo 加淡入淡出会显得廉价）。导出 1080p。

### 如果你想挑战一镜到底

用 **Mission Control 的桌面切换**（`⌃←` / `⌃→`）而不是 `⌘Tab`：
把终端放桌面 1、PPT 全屏放映放桌面 2，切换时是**平滑横移动画**，录出来比 `⌘Tab` 的瞬切好看得多。
但**先按分段录完一版保底**，再挑战这个。

### 录完

1. 传 YouTube，**设为公开**（分工计划 §5 要求）
2. 链接给 @陈智龙 填 README 的 `TODO(A)` 和 Devpost
3. 留言板回一句，让大家知道最后一块交付物到位

## 预答问（评委可能追问，英文作答）

- **"Always asking `other` — isn't that gaming the simulator?"**
  It is a targeted optimisation, and we disclose it. It is provably optimal against the published
  `classify_constraint()`, which can never return `category` or `brand`. A general entropy-based
  policy stays available behind a flag, with its ablation logged. And we spent more time on the
  parts that **are** general: the prior axis, and paraphrase robustness.
- **"Point nine seven on the public set — what about the private one?"**
  It will drop, and we do not pretend otherwise. That is why we tuned with the three-bucket rule
  instead of chasing the maximum, built a paraphrase stress harness, and simulated the failure of
  every assumption we depend on. We hard-coded no answers.
- **"Why not use a large model?"**
  We did, and we measured it. Given only titles it scored worse. Given the same verbatim-hit
  evidence our rule scorer sees, it converged to **parity** — because the rule scorer already
  extracts everything that evidence contains. The LLM earns its place in **understanding**
  paraphrased wording, not in ranking.
