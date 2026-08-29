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

from src.dialog.state import DialogState, Slot

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
    state.slots.append(Slot(attribute=attribute, value=value, hard=hard, turn_added=turn))


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

    # ---- 兜底：未知句式按自由文本入软槽（私有集可能有变体）----
    _add_constraint(state, msg, turn, hard=False)
