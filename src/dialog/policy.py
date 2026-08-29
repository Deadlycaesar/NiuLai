"""M1 提问策略（A 的核心地盘）。

评测器机制决定的两条公理（见 AGENTS.md）：
  1. 提问零成本（每轮可同时提问+推荐，命中即终局）→ 永远提问、永远带 top-10、永不传 null。
  2. `other` 匹配任意剩余约束、每问吐出最多 2 条 → 信息量不低于任何具体属性。
     且 classify_constraint 没有 brand/category 类 → 问 brand/category 永远问不出东西。

两个策略（ASK_POLICY 开关，供消融）：
  other_first（默认）：一直问 other，问干为止——对当前模拟器是信息增益最大化的贪心解。
  entropy：对候选集算属性取值分布熵×覆盖率，问最能"对半切"的属性——通用解，
           面向私有集句式变体和答辩叙事保留。
"""

from __future__ import annotations

import math
from collections import Counter

from src import config
from src.dialog.state import DialogState

_ENTROPY_ATTRS = ("color", "material", "budget")


def _entropy(values: list) -> float:
    counts = Counter(values)
    total = sum(counts.values())
    if total <= 1:
        return 0.0
    return -sum((n / total) * math.log2(n / total) for n in counts.values())


def _entropy_pick(state: DialogState, candidates: list[dict]) -> str:
    covered = {slot.attribute for slot in state.slots}
    best_attr, best_score = "other", 0.0
    for attr in _ENTROPY_ATTRS:
        if attr in state.exhausted or attr in covered:
            continue
        if attr == "budget":
            values = [int(c["price"] // 10) for c in candidates if c.get("price") is not None]
        else:
            values = [c.get(attr) for c in candidates if c.get(attr)]
        coverage = len(values) / max(len(candidates), 1)
        score = _entropy(values) * coverage
        if score > best_score:
            best_attr, best_score = attr, score
    return best_attr


def choose_ask(state: DialogState, candidates: list[dict]) -> str:
    """返回本轮 ask_attribute。约定：永不返回 None。"""
    if config.ASK_POLICY == "entropy" and not state.all_disclosed:
        return _entropy_pick(state, candidates)
    # other_first：问干之后继续问 other 也无害（用户答"没有更多偏好"）
    return "other"
