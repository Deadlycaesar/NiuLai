"""M1 对话总控：Agent 入口（A 的地盘）。

每轮流程：解析消息更新状态 → 蒸馏 → 检索 → 排序 top-10 → 选提问属性 → 组装响应。
铁律：respond() 永不抛异常、每轮必带推荐、ask_attribute 永不为 null。
"""

from __future__ import annotations

from src.dialog import parser, policy
from src.dialog.state import DialogState
from src.memory.distiller import distill
from src.ranking import llm_client
from src.ranking.clarify import clarify
from src.ranking.ranker import rank
from src.retrieval.retriever import Retriever


class ShoppingAgent:
    def __init__(self, catalog_path: str = "data/catalog.jsonl") -> None:
        self.retriever = Retriever(catalog_path)
        self.sessions: dict[str, DialogState] = {}
        # 解析器的目录逐字校验器（实验 33）：抽出的片段须在某件商品文本里逐字存在
        parser.set_catalog_verifier(self.retriever.phrase_exists)

    def reset(self, session_id: str, user_profile: dict) -> None:
        # ⚠️ 评测器只保护 respond()；reset() 抛异常 = 整场评测直接崩（不是记 miss）。
        # 本方法与构造函数一样，必须绝对不抛（T4，见 team/A-任务清单.md）。
        try:
            profile = user_profile if isinstance(user_profile, dict) else {}
            self.sessions[session_id] = DialogState(session_id=session_id, profile=profile)
        except Exception:
            self.sessions[session_id] = DialogState(session_id=str(session_id), profile={})

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        state = self.sessions.get(session_id)
        if state is None:
            state = DialogState(session_id=session_id, profile={})
            self.sessions[session_id] = state
        try:
            return self._respond(state, user_message, turn, top_k)
        except Exception:
            # 兜底：宁可返回上一轮的最优推荐，也绝不空转一轮。
            # usage 仍须结算（C 的计量口径）：异常轮已产生的 LLM token 不能漏到下一轮
            try:
                usage = llm_client.pop_usage()
            except Exception:
                usage = {"prompt_tokens": 0, "completion_tokens": 0}
            return {
                "message": "Here are the closest matches I found.",
                "ask_attribute": "other",
                "recommendations": [{"parent_asin": pid} for pid in state.last_ranked],
                "usage": usage,
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
            "message": clarify(state, ask_attribute, top),
            "ask_attribute": ask_attribute,
            "recommendations": [
                {"parent_asin": c["parent_asin"], "score": round(1.0 / (i + 1), 4)}
                for i, c in enumerate(top)
            ],
            "usage": llm_client.pop_usage(),
        }
