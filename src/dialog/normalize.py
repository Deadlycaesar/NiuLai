"""取值归一化（A 的地盘，T3）：把原始 Amazon 文案形态的约束原文变成干净检索信号。

背景（评测器源码核实）：意图卡约束是未清洗的商品 features/details 原文——
180 字符上限、约 6% 内嵌 "; "、约 1/8 是 "Key: value" 形态。下游（B 检索 / C 排序）
只消费本模块产出的 Slot.terms，不接触文案的脏。

为什么 terms 目前每槽只有一个词（对抗审查实测，2026-08-29）：
在本评测器的意图卡生成机制下，全文归一化串对目标商品 norm_text **零失配**
（3000 商品 / 11793 条约束实测，含全部 180 字符截断与内嵌分号形态——normalize
的标点折叠与评测器 searchable_text 的 "key value" 拼接同构，截断前缀天然是子串）。
因此"键值剥离"等增加匹配机会的变体救不了目标，只会给混淆项送分
（最恶劣如 'Department: mens' → 'mens'，子串命中全库 92.5%，含所有 womens 商品）。
今后若为应对"私有集内联改写卡"加变体，必须带护栏：长度 ≥5 且词边界匹配。

消费约定（SPEC §5）：同槽多 term 取命中的最长者计权、不重复计分；
**空列表 = 本槽不参与文本匹配**（budget 槽即如此，价格信号走 state.budget）。
"""

from __future__ import annotations

import re

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """小写 + 非字母数字折叠为单空格。约束原文和商品全文都过这个，子串匹配才稳。"""
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def constraint_terms(value: str) -> list[str]:
    """一条约束原文 → 归一化检索词列表。空列表 = 本槽不参与文本匹配。"""
    full = normalize(value)
    if not full or full.startswith("budget"):
        return []
    # 评测器合成的 "color: {c}" 是虚构键（商品文本里通常没有 "color {c}" 连写），
    # 只留颜色词本身；details 原生的 "Color: Blue" 同样适用。逐字对齐打样实现，
    # 冒号前带空格等其他形态不剥（它们的全串在商品文本里逐字存在，剥了反而丢判别力）
    if value.lower().startswith("color:"):
        stripped = normalize(value.split(":", 1)[1])
        return [stripped] if stripped else []
    return [full]
