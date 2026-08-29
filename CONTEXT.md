# NiuLai — Shopping Copilot

TikTok TechJam 2026 Track 4 对话式购物搜索 agent。本文件是全组通用语言表(glossary):同一个概念全组用同一个词。实现细节不进这里。

## 评测世界

**意图卡 (Intent Card)**:
评测器为每个目标商品生成的隐藏约束清单(最多 2 硬约束 + 2 软偏好),模拟用户逐轮吐露的唯一信息源。
_Avoid_: 需求卡、标注

**模拟用户 (Simulator)**:
评测器内置的模板复读机——8 句硬编码模板、按样本 ID 确定性播种、零 LLM。同一样本每次跑必得同一对话。

**粗品类 (Coarse Category)**:
商品 categories 尾部两段(剔除 clothing 大类)的拼接;开场句 "I'm looking for X" 里的 X 就是它。

**逐字命中 (Verbatim Hit)**:
约束原文(归一化后)作为连续子串出现在商品可检索全文中。当前排序的主判别信号——因此槽位 value 永远保留评测器原文,不做改写。

**问干 (Exhausted)**:
意图卡约束已全部吐露的状态;继续问只会得到 "I don't have an additional preference"。

## 对话状态

**槽位 (Slot)**:
从用户话语解析出的一条约束:属性 + 原文 value + 硬/软 + 入槽轮次。意图卡侧叫"约束",进入我方状态后叫"槽位"。

**硬约束 / 软偏好 (Hard / Soft)**:
硬 = 过滤或强加权;软 = 仅加权。对应意图卡的 hard_constraints / soft_preferences 之分。

**降权保留 (Demote-preserve)**:
Intent Override 时把旧槽位从硬降为软而非删除——评测器不会二次吐露已披露的约束,删除等于永久丢信息。
_Avoid_: 擦槽、硬擦除(这是被消融实验淘汰的旧方案)

**取值归一化 (Value Normalization)**:
A 的职责边界:把原始 Amazon 文案形态的槽位原文加工成干净检索信号(内嵌分号切分、"Key: value" 剥离、词表归类),下游模块直接消费,不接触文案的脏。

**句式风险 / 取值风险 (Phrasing Risk / Value Risk)**:
私有集相对公开集的两类漂移。句式风险 = 模板文本变化,有界的尾部风险;取值风险 = 约束取值随商品池变化,必然发生,是鲁棒性工作的主靶。

## 流程

**打样 (Prototype Pass)**:
先由一人把全链路打穿的最小可跑实现;各模块占位 stub 等负责人替换升级。

**合龙 (Merge Point)**:
每日定时的集成点:全员代码入 main,跑全量评测,结果记入 team/experiments.md。

**入口壳 (Starter Shell)**:
`starter/agent.py`——官方评测器硬编码 import 的唯一入口,只做转发不写逻辑,A 维护,坏了全队零分。
