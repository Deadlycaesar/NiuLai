"""M3 澄清话术（C 的地盘）——生成给用户看的 `message` 文案。

⚠️ 先明确一件事，免得后来人误判投入：**评测器根本不读 `message`**
（`evaluator/local_evaluator.py:243` 只做 `isinstance(response.get("message"), str)` 类型检查）。
我方与模拟用户之间的唯一信道是 `ask_attribute` 一个 10 选一的枚举 ≈ 3.3 bit/轮。
所以本文件对 TechnicalScore 的贡献严格为 0。

那为什么还要好好写？因为它是**人评**的直接输入：
Technical Execution 35% + Innovation 20% 都由评委打分，而 demo 视频（分工计划 §5 归 C 主责）
录的就是这些句子。改动前的实现是 8 个模板常量，配合 `other_first` 提问策略，
会让 agent 在一场会话里一字不差地重复同一句四遍、且从不提及任何商品名——录出来是硬伤。

设计原则：
  1. 说真话——推 1 件就别说 "matches"（复数）；确实基于用户刚说的话，就复述出来。
  2. 随状态变化——第 1 轮（无证据）、刚拿到约束、已问干，三种情况说法不同。
  3. 零风险——纯字符串拼接，无 LLM、无网络、不可能抛异常（顶层仍有 agent 的兜底）。
     若将来接 LLM 生成，必须保留本文件作为降级路径（AGENTS.md 红线 5）。
"""

from __future__ import annotations

from src.dialog.state import DialogState

# 问某个具体属性时的措辞（ask_attribute 由 M1 决定，本模块只负责把它变成人话）
_ASK_PHRASE = {
    "other": "anything else that matters to you",
    "material": "a fabric or material you prefer",
    "color": "a color you have in mind",
    "size": "the size you need",
    "style": "a particular style or fit",
    "budget": "a budget you're working with",
    "feature": "a specific feature you care about",
    "use_case": "what you'll be using it for",
    "category": "the kind of item you have in mind",
    "brand": "a brand you prefer",
}

_MAX_TITLE = 60


def _short_title(candidate: dict) -> str:
    title = str(candidate.get("title") or "").strip()
    if len(title) > _MAX_TITLE:
        title = title[:_MAX_TITLE].rsplit(" ", 1)[0] + "…"
    return title


def _latest_constraints(state: DialogState, limit: int = 2) -> list[str]:
    """本轮新入槽的约束原文——用来向用户复述"我听到了什么"。"""
    if not state.slots:
        return []
    newest = max(slot.turn_added for slot in state.slots)
    values = [s.value for s in state.slots if s.turn_added == newest]
    return [v if len(v) <= 48 else v[:48].rsplit(" ", 1)[0] + "…" for v in values[:limit]]


def _last_user_message(state: DialogState) -> str:
    return str(state.history[-1].get("user") or "") if state.history else ""


def _just_overrode(state: DialogState) -> bool:
    """本轮用户是否刚改了需求。与 parser 的宽松匹配保持一致（同时覆盖标准句与兜底句）。"""
    message = _last_user_message(state)
    return message.startswith("Actually") and "ignore my earlier preference" in message


def _override_value(state: DialogState) -> str:
    """从变卦句里取出用户点名的新需求；兜底句没有点名内容时返回空串。"""
    message = _last_user_message(state)
    if "What I need is:" not in message:
        return ""
    value = message.split("What I need is:", 1)[1].strip().rstrip(".")
    return value if len(value) <= 48 else value[:48].rsplit(" ", 1)[0] + "…"


def clarify(state: DialogState, ask_attribute: str | None, top: list[dict] | None = None) -> str:
    """组装 message 文案。

    `top` 是本轮排好序的候选（M3 rank() 的返回值），可选——不传则退化为不提商品名的版本，
    保证任何调用方（含旧代码）都不会坏。
    """
    try:
        return _compose(state, ask_attribute, top or [])
    except Exception:
        # 话术永远不该成为故障源
        return "Here's what I have so far. Tell me more and I'll narrow it down."


def _compose(state: DialogState, ask_attribute: str | None, top: list[dict]) -> str:
    ask = _ASK_PHRASE.get(ask_attribute or "", _ASK_PHRASE["other"])
    category = (state.category or "").strip()
    count = len(top)
    lead_title = _short_title(top[0]) if top else ""

    # ── 开场：还没有任何约束，只知道粗品类。坦白说明这是"起点"而非"答案"。
    # 只在第 1 轮说"Let's start"——boundary 场景第 2 轮仍然无槽位，再说一次开场白就露馅了。
    if not state.slots and len(state.history) <= 1:
        opener = f"Let's start with {category}." if category else "Let's start narrowing this down."
        if lead_title:
            opener += f" The closest single match I have right now is {lead_title}."
        return f"{opener} To do better I need a bit more — is there {ask}?"

    # ── 问了但用户没给（boundary 首问被挡 / 该属性问干）：承认没拿到，换个角度再问。
    if not state.slots:
        if lead_title:
            return (
                f"No problem — I'll go with my judgement for now. "
                f"My current pick is {lead_title}. If it helps, is there {ask}?"
            )
        return f"No problem — I'll use my judgement. If anything comes to mind, is there {ask}?"

    # ── 用户刚变卦（Intent Override）：必须回应"我听到你改需求了"，否则会复读上一轮。
    # 起因：override 点名的约束通常早已入槽，`_promote_or_add` 只把它提升为 hard、
    # 不改 turn_added，于是 `_latest_constraints` 拿到的还是上一轮的内容。
    if _just_overrode(state):
        pivot = _override_value(state)
        tail = f" Is there {ask}?" if not state.all_disclosed else ""
        if pivot and lead_title:
            return f"Understood — let's prioritise {pivot} instead. That points me to {lead_title}.{tail}"
        if lead_title:
            return f"Understood, I've reset my focus. My best match now is {lead_title}.{tail}"
        return f"Understood — I've dropped my earlier assumption.{tail}"

    heard = _latest_constraints(state)

    # ── 已问干：约束全部拿到，不再假装还能问出东西。
    if state.all_disclosed:
        if count == 1 and lead_title:
            return f"Based on everything you've told me, my best match is {lead_title}."
        if count:
            return (
                f"Based on everything you've told me, here are the {count} closest matches, "
                "best first."
            )
        return "Based on everything you've told me, I couldn't find a close match yet."

    # ── 刚拿到新约束：复述出来，让用户看到自己被听懂了。
    if heard:
        echo = " and ".join(heard)
        if count == 1 and lead_title:
            return f"Got it — {echo}. That points me to {lead_title}. Is there {ask}?"
        if count:
            return (
                f"Got it — {echo}. Here are the {count} closest matches on that. "
                f"Is there {ask}?"
            )
        return f"Got it — {echo}. Is there {ask}?"

    # ── 有约束但本轮没新增（例如用户答"没有更多偏好"）：换个说法，别复读。
    if count == 1 and lead_title:
        return f"Still my strongest match is {lead_title}. Is there {ask}?"
    if count:
        return f"Here are the {count} closest matches so far. Is there {ask}?"
    return f"I haven't found a close match yet. Is there {ask}?"
