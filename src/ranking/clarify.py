"""M3 澄清话术 —— 骨架占位实现（C 的地盘）。当前为模板；C 可换 LLM 生成（留降级）。"""

from __future__ import annotations

from src.dialog.state import DialogState

_TEMPLATES = {
    "other": "Here are the closest matches so far. Is there anything else that matters to you?",
    "budget": "Here are some options. Do you have a budget in mind?",
    "material": "Here are some options. Any preference on material?",
    "color": "Here are some options. Any preference on color?",
    "size": "Here are some options. What size do you need?",
    "style": "Here are some options. Any style preference?",
    "use_case": "Here are some options. What occasion or use case is this for?",
    "feature": "Here are some options. Any specific feature you care about?",
}


def clarify(state: DialogState, ask_attribute: str | None) -> str:
    if ask_attribute is None:
        return "Here are the closest matches I found."
    return _TEMPLATES.get(ask_attribute, _TEMPLATES["other"])
