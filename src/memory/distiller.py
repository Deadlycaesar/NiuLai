"""M4 上下文蒸馏 —— 约束清单 + profile 软偏好 + 跨轮信号的模板化拼接（D 的地盘）。

规则优先，零外部依赖。输出长度只随"当前生效约束数"增长——other_first 策略
几轮就把评测器能吐的约束问干，天然封顶，不随原始轮数线性膨胀（验收标准①）。
"""

from __future__ import annotations

from src.dialog.state import DialogState
from src.memory import lexicon, signals


def distill(state: DialogState) -> str:
    signals.update(state)

    parts = [f"category: {state.category}" if state.category else ""]
    parts += [f"[{s.attribute}] {s.value}" for s in state.slots]

    tags = state.profile.get("preference_tags") or []
    if tags:
        parts.append("profile tags: " + ", ".join(str(t) for t in tags[:5]))
    soft_terms = lexicon.profile_soft_terms(state.profile)
    if soft_terms:
        parts.append("profile hints: " + ", ".join(soft_terms))

    stagnant = signals.stagnant_turns(state.session_id)
    if stagnant:
        parts.append(f"stagnant_turns: {stagnant}")
    rejected = signals.rejected_asins(state.session_id)
    if rejected:
        parts.append(f"rejected_count: {len(rejected)}")

    return " | ".join(p for p in parts if p)
