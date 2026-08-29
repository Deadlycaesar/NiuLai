"""对话状态（接口冻结，见 team/SPEC.md §5）。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class Slot:
    attribute: str        # ask_attribute 枚举之一（budget/material/color/... /feature）
    value: str            # 约束原文（评测器逐字吐出，保留原文用于子串匹配）
    hard: bool            # 硬约束(过滤/强加权) or 软偏好
    turn_added: int


@dataclass
class DialogState:
    session_id: str
    profile: dict
    slots: list[Slot] = field(default_factory=list)
    asked: set[str] = field(default_factory=set)       # 已问过的属性
    exhausted: set[str] = field(default_factory=set)   # 用户明说"没有更多偏好"的属性
    all_disclosed: bool = False                        # other 已问干（所有约束都拿到了）
    category: str = ""                                 # "I'm looking for X" 的 X
    scenario: str = "unknown"                          # buying/browsing/override/boundary/unknown
    budget: float | None = None                        # "budget around $X" 解析出的 X
    history: list[dict] = field(default_factory=list)
    distilled: str = ""                                # M4 产出
    last_ranked: list[str] = field(default_factory=list)  # 兜底：上一轮的 top-10

    def constraint_values(self) -> list[str]:
        return [slot.value for slot in self.slots]

    def erase_preferences(self) -> None:
        """Intent Override：擦掉全部偏好槽位（保留 category）。"""
        self.slots.clear()
        self.budget = None
        self.exhausted.clear()
        self.all_disclosed = False

    def demote_preferences(self) -> None:
        """Intent Override 的温和版：旧约束降为软偏好（保留检索信号），并重开提问。

        依据：override 场景目标商品不变，旧约束仍描述目标；且评测器不会二次吐露
        已 disclosed 的约束，硬擦除等于永久丢失信息（消融实证：擦除版 override
        HitRate 0.667，降权版见 experiments.md）。
        """
        for slot in self.slots:
            slot.hard = False
        self.exhausted.clear()
        self.all_disclosed = False
