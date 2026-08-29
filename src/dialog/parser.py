"""约束解析器：对着 evaluator/local_evaluator.py 的固定句式写（该文件只读，勿改）。

句式清单（逐字来自评测器源码）：
  开场 buying:   "I'm looking for {cat}. A key requirement is: {c}."
  开场 override: "I'm looking for {cat}. {old_value}"
  开场 browsing: "I'm looking for {cat}, but I'm still exploring."
  改需求:        "Actually, ignore my earlier preference. What I need is: {v}."
  改需求(兜底):  "Actually, please ignore my earlier preference."（评测器 behavior 无
                 message 键时的备用句——无点名约束，只触发降权）
  吐约束:        "For that, what matters is: {c1}; {c2}."
  问干了:        "I don't have an additional preference for {attr}."
  boundary 挡:   "I don't have a preference for {attr}; please use your judgment."
  null 惩罚:     "Those options are not quite right yet. Ask me about one specific attribute."
"""

from __future__ import annotations

import re

from src import config
from src.dialog.normalize import constraint_terms, normalize
from src.dialog.state import DialogState, Slot
from src.ranking import llm_client

# 与评测器 classify_constraint 保持一致的镜像分类器（不 import evaluator，避免循环依赖）
_MATERIALS = ("cotton", "polyester", "nylon", "leather", "wool", "spandex", "silk", "rayon", "fabric")
_BUDGET_RE = re.compile(r"budget around \$([0-9]+(?:\.[0-9]+)?)", re.I)


def classify_constraint(value: str) -> str:
    lowered = value.lower()
    if "budget" in lowered or re.search(r"(?:\$|<=|under)\s*\d", lowered):
        return "budget"
    if any(material in lowered for material in _MATERIALS):
        return "material"
    if any(word in lowered for word in ("color", "black", "white", "blue", "red", "pink", "green")):
        return "color"
    if any(word in lowered for word in ("size", "sizing", "width", "wide", "narrow")):
        return "size"
    if any(word in lowered for word in ("department", "style", "fit", "sleeve", "neck")):
        return "style"
    if any(word in lowered for word in ("hiking", "running", "gym", "winter", "outdoor", "work")):
        return "use_case"
    return "feature"


def _add_constraint(state: DialogState, value: str, turn: int, hard: bool = True) -> None:
    value = value.strip().rstrip(".")
    if not value or value in state.constraint_values():
        return
    attribute = classify_constraint(value)
    if attribute == "budget":
        match = _BUDGET_RE.search(value)
        if match:
            state.budget = float(match.group(1))
    state.slots.append(Slot(
        attribute=attribute, value=value, hard=hard, turn_added=turn,
        terms=constraint_terms(value),
    ))


def _promote_or_add(state: DialogState, value: str, turn: int) -> None:
    """override 点名的约束：若早前已吐露入槽（降权后为软），重新提升为 hard；否则新增硬槽。

    不能直接走 _add_constraint——它遇到重复值直接跳过，会让用户最强的信号停留在软权重
    （bug 实录见 team/A-任务清单.md T1，public_0003 复现）。
    """
    cleaned = value.strip().rstrip(".")
    for slot in state.slots:
        if slot.value == cleaned:
            slot.hard = True
            return
    _add_constraint(state, cleaned, turn, hard=True)


def update_state(state: DialogState, message: str, turn: int) -> None:
    state.history.append({"turn": turn, "user": message})
    msg = message.strip()

    # ---- 改需求（override）：旧槽位降权保留 + 点名约束提升/置入为 hard ----
    # 宽松匹配：同时覆盖标准句、无点名约束的兜底句、以及轻度措辞变体
    if msg.startswith("Actually") and "ignore my earlier preference" in msg:
        state.scenario = "override"
        state.demote_preferences()
        if "What I need is:" in msg:
            new_value = msg.split("What I need is:", 1)[1].strip()
            _promote_or_add(state, new_value, turn)
        return

    # ---- 吐约束 ----
    if msg.startswith("For that, what matters is:"):
        body = msg.split("For that, what matters is:", 1)[1].strip().rstrip(".")
        for part in body.split("; "):
            _add_constraint(state, part, turn, hard=True)
        return

    # ---- 问干了 ----
    match = re.match(r"I don't have an additional preference for (\w+)\.", msg)
    if match:
        attribute = match.group(1)
        state.exhausted.add(attribute)
        if attribute == "other":
            state.all_disclosed = True   # other 匹配任意约束，问干 = 全部拿到
        return

    # ---- boundary 挡了第一问（该属性之后仍可再问，不标记 exhausted）----
    if re.match(r"I don't have a preference for \w+; please use your judgment\.", msg):
        state.scenario = "boundary"
        return

    # ---- null 惩罚句（不应出现：我们永不发 null）----
    if msg.startswith("Those options are not quite right yet"):
        return

    # ---- 开场三种 ----
    if msg.startswith("I'm looking for "):
        rest = msg[len("I'm looking for "):]
        if rest.endswith(", but I'm still exploring."):
            state.category = rest[: -len(", but I'm still exploring.")].strip()
            state.scenario = "browsing"
            return
        if ". A key requirement is: " in rest:
            category, constraint = rest.split(". A key requirement is: ", 1)
            state.category = category.strip()
            state.scenario = "buying"
            _add_constraint(state, constraint, turn, hard=True)
            return
        # override 开场："I'm looking for {cat}. {old_value}"（old_value 是软偏好，3-4 轮后会被擦掉）
        if ". " in rest:
            category, old_value = rest.split(". ", 1)
            state.category = category.strip()
            _add_constraint(state, old_value, turn, hard=False)
        else:
            state.category = rest.strip().rstrip(".")
        return

    # ---- 兜底：未知句式走"载荷抽取"（私有集改写场景的主力路径，见下方 _salvage）----
    _salvage(state, msg, turn)


# ===========================================================================
# 载荷抽取兜底（改写鲁棒性）
# ===========================================================================
# 动机（实测，scripts/paraphrase_stress.py）：官方保留了给模拟用户加自然语言改写的权利。
# 一旦句式变化，上面那批 startswith/精确正则全部落空，整句话会被当成【一条】软约束塞进
# 槽位——而 ranker 的主信号是"约束原文作为连续子串出现在商品全文中"，一整句话永远匹配不上。
#
# 改写压力测试的分层结论（全量 200 条，evaluator 未改）：
#     L0 原样                        0.9620
#     L1 只改句式，约束原文一字不动   0.7792   ← -0.183，占全部损失的 87%
#     L2 再改短约束                  0.7585   ← -0.021
#     L3 连长规格串也重组            0.7523   ← -0.007
# 也就是说：**脆的是句式匹配，不是逐字匹配**。逐字指纹信号本身相当结实。
# 所以兜底的关键不是"理解语义"，而是"把约束片段从陌生句式里捞出来"——纯规则即可，不需要 LLM。
#
# 设计约束：本函数【只在严格模板全部落空时】才会被调用，因此对公开集（模板固定）
# 逐字节零影响。这是它可以放心上线的前提。

# 改需求信号：动词 + 时间指示词，覆盖 ignore/forget/scratch/disregard 等常见改写
_OVERRIDE_HINT = re.compile(
    r"\b(?:ignore|forget|scratch|disregard|never\s+mind)\b.{0,48}?"
    r"\b(?:earlier|before|previous(?:ly)?|already\s+said|told\s+you|first)\b",
    re.I | re.S,
)
# 改需求的"新需求"载荷：actually want / need is / what I want …
_OVERRIDE_PAYLOAD = re.compile(
    r"\b(?:what\s+I\s+(?:actually\s+)?(?:want|need)\s+is|actually\s+(?:want|need)|"
    r"instead\s+I\s+(?:want|need)|I\s+really\s+need)\b[:\s]*(?P<payload>.+)$",
    re.I | re.S,
)
# 粗品类：常见"我在找 X"的说法。停在标点或转折词处，避免把整句吞进来。
_CATEGORY_HINT = re.compile(
    r"\b(?:looking\s+for|shopping\s+(?:around\s+)?for|browsing\s+for|"
    r"in\s+the\s+market\s+for|after|hunting\s+for|want|need)\s+"
    r"(?P<cat>[^.,;:!?]{3,60}?)"
    r"(?=\s*(?:[.,;:!?—–]|$|\bbut\b|\bat\s+the\s+moment\b|\bright\s+now\b|\bthough\b))",
    re.I,
)
# 载荷分隔符：分号是评测器原生的多约束分隔；", and " 是改写后常见的连接
_PAYLOAD_SPLIT = re.compile(r";\s*|\s+and\s+also\s+|,\s+and\s+")

_JUNK_WORDS = {
    "it", "one", "something", "anything", "that", "this", "them", "those",
    "please", "thanks", "sure", "okay", "ok", "yeah", "yes", "no", "well",
    "hmm", "sorry", "really", "just", "still", "maybe", "actually",
}


def _payload_after_colon(text: str) -> str | None:
    """取最后一个冒号之后的内容。评测器的三种带载荷句式都是 'lead-in: payload' 形态，
    改写后 lead-in 变了但冒号通常还在，所以这是命中率最高的一条抽取规则。"""
    index = text.rfind(":")
    if index == -1:
        return None
    payload = text[index + 1:].strip().strip("\"'")
    return payload or None


def _is_useful(fragment: str) -> bool:
    """过滤掉进了槽位也匹配不到任何商品、反而可能误伤排序的碎片。"""
    cleaned = fragment.strip(" .,;:!?\"'—–")
    if len(cleaned) < 3:
        return False
    words = [w for w in re.findall(r"[a-z0-9%]+", cleaned.lower()) if w]
    if not words:
        return False
    # 全是口水词 → 丢弃
    return any(w not in _JUNK_WORDS for w in words)


def _add_fragments(state: DialogState, payload: str, turn: int, hard: bool) -> int:
    added = 0
    for fragment in _PAYLOAD_SPLIT.split(payload):
        fragment = fragment.strip().strip(" .,;:!?\"'—–")
        if _is_useful(fragment):
            before = len(state.slots)
            _add_constraint(state, fragment, turn, hard=hard)
            added += len(state.slots) - before
    return added


def _salvage(state: DialogState, message: str, turn: int) -> None:
    """从陌生句式里尽量捞出：改需求信号 / 粗品类 / 约束片段。"""
    # ① 改需求——语义等价于上面的严格分支，只是句式放宽
    if _OVERRIDE_HINT.search(message):
        state.scenario = "override"
        state.demote_preferences()
        promoted = 0
        match = _OVERRIDE_PAYLOAD.search(message)
        if match:
            payload = match.group("payload").strip().strip(" .\"'")
            for fragment in _PAYLOAD_SPLIT.split(payload):
                fragment = fragment.strip().strip(" .,;:!?\"'—–")
                if _is_useful(fragment):
                    _promote_or_add(state, fragment, turn)
                    promoted += 1
        if not promoted:
            # 改需求信号命中但"新需求"载荷没捞到（改写把它藏进了规则盖不住的句型）
            # → 第三层上。LLM 失败也无妨：降权已完成，语义主体保住了。
            _llm_extract(state, message, turn)
        return

    # ② 粗品类——只在还没拿到时抽取（开场轮）。品类精确命中在 ranker 里值 +2.5。
    if not state.category:
        match = _CATEGORY_HINT.search(message)
        if match:
            candidate = match.group("cat").strip().strip(" .,;:!?\"'—–")
            if _is_useful(candidate):
                state.category = candidate

    # ③ 约束片段——优先取冒号载荷，取不到则退回整句切分
    payload = _payload_after_colon(message)
    if payload and _add_fragments(state, payload, turn, hard=False):
        return
    # ③.5 第三层防线：LLM 逐字片段抽取（LLM_PARSE 开关，默认关）。
    # 只在冒号载荷这条高命中规则也落空、即将退回"整句切分"最弱路径时才触发——
    # 实验 16a 定位"脆的是片段抽取不是语义"，LLM 在这里干的就是边界检测。
    if _llm_extract(state, message, turn):
        return
    _add_fragments(state, message, turn, hard=False)


# ===========================================================================
# 第三层防线：LLM 逐字片段抽取（A，T-LLM；默认关，纯增强）
# ===========================================================================
# 设计约束（与 _salvage 同一条保证链）：
#   1. 公开集构造性零触发——严格模板命中就 return，走不到这里；
#   2. 逐字指纹不可破坏——LLM 只做"从消息里抄出片段"，每条产出强制过 verbatim
#      校验（归一化后必须是原消息的连续子串），改写/编造一律丢弃；
#   3. 离线不掉档——无 key 秒返 None；网络故障连续 2 次熔断，此后行为 = 纯规则。

_PARSE_SYSTEM = (
    "You extract shopping intent from one customer message. The message may embed "
    "verbatim product-attribute phrases (materials, specs, features, colors). "
    'Reply with json only: {"category": string|null, "override": boolean, '
    '"constraints": [string, ...]}. RULES: each constraint MUST be an exact '
    "contiguous substring copied character-for-character from the message — never "
    "rephrase, translate, or merge; at most 4 constraints; category is the product "
    "type being sought (short noun phrase from the message) or null; override is "
    "true ONLY if the customer discards their earlier stated preference."
)

_llm_parse_failures = 0  # 连续失败计数；≥2 熔断（进程生命周期内不再尝试）


def _llm_extract(state: DialogState, message: str, turn: int) -> bool:
    """返回 True = LLM 成功应答并接管本消息的抽取（包括'确认无约束'的空判定——
    此时跳过整句切分，避免垃圾碎片入槽）；False = 未启用/熔断/调用失败，规则接续。"""
    global _llm_parse_failures
    if not config.LLM_PARSE or _llm_parse_failures >= 2:
        return False
    reply = llm_client.chat_json(_PARSE_SYSTEM, message, max_tokens=200)
    if reply is None:
        _llm_parse_failures += 1
        return False
    _llm_parse_failures = 0
    norm_message = normalize(message)
    is_override = reply.get("override") is True
    if is_override:
        state.scenario = "override"
        state.demote_preferences()
    category = reply.get("category")
    if not state.category and isinstance(category, str):
        category = category.strip(" .,;:!?\"'—–")
        # 品类同样过 verbatim 校验 + 口水词过滤
        if _is_useful(category) and normalize(category) in norm_message:
            state.category = category
    constraints = reply.get("constraints")
    if isinstance(constraints, list):
        for item in constraints[:4]:
            if not isinstance(item, str):
                continue
            fragment = item.strip().strip(" .,;:!?\"'—–")
            # verbatim 校验：拒绝一切改写（指纹信号 > LLM 的语言品味）
            if not _is_useful(fragment) or normalize(fragment) not in norm_message:
                continue
            if is_override:
                _promote_or_add(state, fragment, turn)
            else:
                _add_constraint(state, fragment, turn, hard=False)
    return True
