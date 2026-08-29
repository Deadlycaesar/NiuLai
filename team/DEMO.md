# 会议演示手册（照着跑就行）

> 会前准备：`cd NiuLai`，确认跑过 `python3 scripts/prepare_catalog.py`，终端字体调大。
> 全程 6 幕约 12 分钟。每幕 = 一条命令 + 预期输出 + 讲解词。所有数字都是确定性的，现场跑必然复现。

---

## 幕 1 · 官方基线全量跑分（33 秒）

```bash
AGENT_IMPL=baseline python3 -m evaluator.local_evaluator --output results_baseline.json
```

**预期**：`recommended_technical_score: 0.10671`，分场景 buying 0.238 / browsing 0.025 / override 0.133 / boundary 0。

**讲解词**：
- "评分公式：0.5×命中率 + 0.3×排名 + 0.2×轮数效率，10 轮上限，命中即结束。"
- "官方基线只有 0.107。注意 browsing 占 40% 的场景它几乎是 0——这就是我们的主战场。"
- "整个评测 33 秒跑完，意味着我们改一行代码半分钟就知道分数变化，迭代成本极低。"

## 幕 2 · 基线是怎么死的（badcase 回放）

```bash
AGENT_IMPL=baseline python3 scripts/trace_session.py --id public_0007
```

**预期现象**（让大家看第 1、2 轮就够）：
- 用户开场："I'm looking for Tees & Blouses Tunics, but I'm still exploring."（目标是一件 RITERA 大码上衣）
- 基线 `提问字段: None` → 模拟用户只回一句 "Those options are not quite right yet. Ask me about one specific attribute."
- **第 2 轮 badcase 高光**：基线拿这句话本身去检索，top-10 变成自行车裤、万圣节袜子、束腰马甲——彻底跑偏，10 轮不命中。

**讲解词**：
- "基线三宗罪：无状态（不记得上一轮）、从不提问（浪费了用户主动配合的机制）、只搜当前这句话（所以连用户的抱怨都拿去当查询词）。"
- "看清楚这个死法，就明白我们架构里每个模块为什么存在。"

## 幕 3 · 我们的版本全量跑分（26 秒）

```bash
python3 -m evaluator.local_evaluator
```

**预期**：`recommended_technical_score: 0.86067`，HitRate 0.98 / MRR 0.664 / MTTC 2.42；分场景 buying 0.975 / browsing 0.988 / override 0.967 / boundary 1.0。

**讲解词**：
- "0.107 → 0.861，靠三个机制：① 跨轮累积约束的状态机；② 每轮同时提问+带 top-10（提问零成本，命中即赢）；③ 约束逐字子串匹配的排序。"
- "迭代过程见 team/experiments.md：其中 override 场景从 0.667 修到 0.967，靠的是把'擦除旧约束'改成'降权保留'——评测器不会把已披露的约束吐第二遍，硬擦等于永久丢信息。这类洞察全来自读评测器源码。"

## 幕 4 · 同一条会话，我们怎么赢的

```bash
python3 scripts/trace_session.py --id public_0007
```

**预期现象**：
- 第 1 轮：品类检索给出 10 件女式上衣 + 提问 `other`
- 第 2 轮：用户吐出底牌 "For that, what matters is: polyester; **75% Polyester, 20% Rayon, 5% Spandex**." → 这串成分表是目标商品元数据的逐字片段，近乎指纹 → **第 2 轮第 1 名命中，RR=1.0**

**讲解词**：
- "为什么问 `other`？读评测器源码发现：问中属性用户一次吐 2 条约束，而 other 匹配任意剩余约束——我们做了消融，other 策略 0.861 vs 信息熵策略 0.830（表里 3a 行）。"
- "用户吐出的约束是商品元数据的逐字片段，越长越像指纹——所以排序里长约束命中权重最高。"

## 幕 5 · 接上 LLM 会更好吗？（反直觉实验）

先亮结论（team/experiments.md 4a/4b 行）：抽样 40 条，规则 0.882 → 接 DeepSeek 精排 **0.779，MRR 掉了 0.33**。然后现场看退化实例：

```bash
USE_LLM=1 python3 scripts/trace_session.py --id public_0169
```

**预期现象**：第 3 轮用户吐出 "cotton; 57% Cotton, 26% Polyester…"，规则排序里目标（Amazon Essentials 打底牛仔裤）本是**第 1 名**，LLM 重排后掉到**第 6**——它把 Levi's、Calvin Klein 等大牌按"语义像不像"排到了前面。

**讲解词**：
- "LLM 只看到标题+价格，看不到'哪条约束命中了哪个候选'这个指纹证据，于是凭品牌感觉排——精确信号被模糊判断覆盖，这就是负收益的原因。"
- "所以 USE_LLM 默认是 0，离线路径永远是主路径（正式评测可能断网）。LLM 怎么转正是 C 的核心任务，三条路线写在 experiments.md：喂命中证据 / 只在低置信时调用 / 改做约束解析。"
- "顺带汇报成本：DeepSeek v4-flash 实测 0.85 秒/调用，整个 A/B 实验花了 1 毛 4。"

## 幕 6 · 剩下的 4 个 miss（badcase → 引出分工）

不用跑命令，口述 + 给大家看这个例子（想现场看可跑 `python3 scripts/trace_session.py --id public_0087`）：

> public_0087 目标是 Goodthreads 免烫衬衫，模拟用户的底牌是：hard = **['cotton', '100% Cotton']**，soft = **['Imported', 'Button closure']**——四条全是几千件商品共有的泛化约束，预算也没进卡。**约束本身不足以指认目标**，这就是纯规则的天花板。

**讲解词 → 每人的任务**（认领后把 `team/briefs/` 自己那份 + 根目录 `AGENTS.md` 喂给自己的 AI 助手开工）：
- **B（M2 检索）**：泛化约束下要靠稠密向量把"语义邻居"捞进候选集，你的 KPI 是 Recall@100——目标不进候选集，一切归零。
- **C（M3 排序）**：接手幕 5 那个挑战——让 LLM 从负收益变正收益，主攻 MRR（权重 0.3，当前 0.664，最大提分空间）。
- **D（M4 记忆）**：badcase 里唯一没用上的信息是用户画像（preference_tags/summary）——尾部 session 就靠它兜底；另外做蒸馏防 prompt 膨胀。
- **E（M5 评测）**：把今天所有对照实验变成一键消融 + CI 护栏（evaluator 只读、key 扫描、入口壳冒烟）；experiments.md 从今天起每天两行。
- **A（M1，我）**：状态机和提问策略继续打磨，两个切换阈值和 E 一起在公开集上调。

## 附 · 预答问

- **"other 策略是不是过拟合模拟器？"**——是针对性优化，但私有集用同一份评测器代码（官方声明），机制不变；熵策略作为通用解保留在 `ASK_POLICY=entropy` 开关里，答辩讲通用框架。
- **"公开集 0.861，私有集会怎样？"**——用户和商品都不同，会有回落；但我们没有硬编码任何答案（红线），机制类收益（状态/提问/逐字匹配）应当可迁移。分场景分数是比总分更稳的观测口径。
- **"为什么不用 LangGraph/框架？"**——评测器要求单文件入口+轻依赖，当前全部 stdlib 零第三方依赖，正式评测断网也能跑。
