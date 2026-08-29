"""M4 上下文蒸馏 —— 骨架占位实现（D 的地盘，接口冻结、实现待换）。

当前占位 = 约束清单的模板化拼接。
D 接手后：加 profile 软偏好注入、被拒推荐的 Reflection 信号、跨轮策略提示。
"""

from __future__ import annotations

from src.dialog.state import DialogState


def distill(state: DialogState) -> str:
    parts = [f"category: {state.category}" if state.category else ""]
    parts += [f"[{s.attribute}] {s.value}" for s in state.slots]
    tags = state.profile.get("preference_tags") or []
    if tags:
        parts.append("profile tags: " + ", ".join(str(t) for t in tags[:5]))
    return " | ".join(p for p in parts if p)
