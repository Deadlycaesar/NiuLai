"""M1 对话总控：Agent 入口（A 的地盘）。

每轮流程：解析消息更新状态 → 蒸馏 → 检索 → 排序 top-10 → 选提问属性 → 组装响应。
铁律：respond() 永不抛异常、每轮必带推荐、ask_attribute 永不为 null。
"""

from __future__ import annotations

from src.dialog import parser, policy
from src.dialog.state import DialogState
from src.memory.distiller import distill
from src.ranking.clarify import clarify
from src.ranking.ranker import rank
from src.retrieval.retriever import Retriever


class ShoppingAgent:
    def __init__(self, catalog_path: str = "data/catalog.jsonl") -> None:
        self.retriever = Retriever(catalog_path)
        self.sessions: dict[str, DialogState] = {}

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.sessions[session_id] = DialogState(
            session_id=session_id,
            profile=user_profile if isinstance(user_profile, dict) else {},
        )

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self.sessions.get(session_id)
        if state is None:
            state = DialogState(session_id=session_id, profile={})
            self.sessions[session_id] = state
        try:
            return self._respond(state, user_message, turn, top_k)
        except Exception:
            # 兜底：宁可返回上一轮的最优推荐，也绝不空转一轮
            return {
                "message": "Here are the closest matches I found.",
                "ask_attribute": "other",
                "recommendations": [{"parent_asin": pid} for pid in state.last_ranked],
                "usage": {"prompt_tokens": 0, "completion_tokens": 0},
            }

    def _respond(self, state: DialogState, user_message: str, turn: int, top_k: int) -> dict:
        parser.update_state(state, user_message, turn)
        state.distilled = distill(state)

        candidates = self.retriever.retrieve(state, user_message, k=100)
        top = rank(state, candidates, k=top_k)
        ask_attribute = policy.choose_ask(state, candidates)
        state.asked.add(ask_attribute)
        state.last_ranked = [c["parent_asin"] for c in top]

        return {
            "message": clarify(state, ask_attribute),
            "ask_attribute": ask_attribute,
            "recommendations": [
                {"parent_asin": c["parent_asin"], "score": round(1.0 / (i + 1), 4)}
                for i, c in enumerate(top)
            ],
            "usage": {"prompt_tokens": 0, "completion_tokens": 0},
        }
