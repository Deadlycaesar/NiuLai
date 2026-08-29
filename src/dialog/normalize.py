"""取值归一化（A 的地盘，T3）：把原始 Amazon 文案形态的约束原文变成干净检索信号。

背景（评测器源码核实）：意图卡约束是未清洗的商品 features/details 原文——
180 字符上限、约 6% 内嵌 "; "、约 1/8 是 "Key: value" 形态。下游（B 检索 / C 排序）
只消费本模块产出的 Slot.terms，不接触文案的脏。

变体准入史（对抗审查实测，2026-08-29）：
在本评测器的意图卡生成机制下，全文归一化串对目标商品 norm_text **零失配**
（3000 商品 / 11793 条约束实测，含全部 180 字符截断与内嵌分号形态——normalize
的标点折叠与评测器 searchable_text 的 "key value" 拼接同构，截断前缀天然是子串）。
- ❌ "键值剥离"变体：救不了目标、只给混淆项送分（最恶劣如 'Department: mens' →
  'mens'，子串命中全库 92.5%，含所有 womens 商品），永不启用。
- ✅ 逗号分片变体（C-T8 迁移入本接口）：应对改写重组规格串（"75% Polyester, 20%
  Rayon" → 反序）——整串失配时各成分仍逐字存在。护栏：片段 ≥5 字符；消费端
  max-len 规则保证整串命中时分片不重复计分。C 实测与独立通道等价（±0.004 噪声带）。
新变体准入标准不变：长度 ≥5 + 有"救得了目标"的实证，缺一不发。

消费约定（SPEC §5）：同槽多 term 取命中的最长者计权、不重复计分；
**空列表 = 本槽不参与文本匹配**（budget 槽即如此，价格信号走 state.budget）。
"""

from __future__ import annotations

import re

from src import config

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")


def normalize(text: str) -> str:
    """小写 + 非字母数字折叠为单空格。约束原文和商品全文都过这个，子串匹配才稳。"""
    return _NON_ALNUM_RE.sub(" ", text.lower()).strip()


def constraint_terms(value: str) -> list[str]:
    """一条约束原文 → 归一化检索词列表（判别力降序）。空列表 = 本槽不参与文本匹配。"""
    full = normalize(value)
    if not full or full.startswith("budget"):
        return []
    # 评测器合成的 "color: {c}" 是虚构键（商品文本里通常没有 "color {c}" 连写），
    # 只留颜色词本身；details 原生的 "Color: Blue" 同样适用。逐字对齐打样实现，
    # 冒号前带空格等其他形态不剥（它们的全串在商品文本里逐字存在，剥了反而丢判别力）
    if value.lower().startswith("color:"):
        stripped = normalize(value.split(":", 1)[1])
        terms = [stripped] if stripped else []
    else:
        terms = [full]
    # 逗号分片变体（C-T8，实验 16 系；FRAGMENT_WEIGHT=0 时关闭 = 消融口径，
    # 权重数值本身不再使用——消费端 max-len 计权，整串命中时分片自然让位）
    if terms and config.FRAGMENT_WEIGHT:
        parts = [p.strip() for p in value.split(",")]
        if len(parts) >= 2:
            for part in parts:
                piece = normalize(part)
                if len(piece) >= 5 and piece not in terms:
                    terms.append(piece)
    return terms
