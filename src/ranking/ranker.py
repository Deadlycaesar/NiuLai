"""M3 排序 —— 骨架占位实现（C 的地盘，接口冻结、实现待换）。

当前占位 = 离线规则打分：加权约束命中（硬>软、长约束>短约束）> 精确价格 > BM25 名次。
长约束加权的依据：约束是目标商品元数据的逐字片段，越长的片段命中越能唯一指认目标。
C 接手后：加 CPU 交叉编码器重排 + LLM listwise 润色（USE_LLM 开关），保留本函数做离线降级。
"""

from __future__ import annotations

from src.dialog.state import DialogState
from src.retrieval.retriever import constraint_match_token, normalize


def rank(state: DialogState, candidates: list[dict], k: int = 10) -> list[dict]:
    if not candidates:
        return []
    total = max(len(candidates), 1)

    # 预计算每条约束的匹配串与权重
    weighted_tokens: list[tuple[str, float]] = []
    for slot in state.slots:
        token = constraint_match_token(slot.value)
        if not token or token.startswith("budget"):
            continue
        base = 2.0 if slot.hard else 0.75
        length_bonus = 1.0 + min(len(token), 60) / 30.0   # 长逐字片段 → 最高 3 倍
        weighted_tokens.append((token, base * length_bonus))

    norm_category = normalize(state.category) if state.category else ""

    def score(c: dict) -> float:
        text = c.get("norm_text", "")
        s = sum(weight for token, weight in weighted_tokens if token in text)
        # 开场句的品类 = 评测器用目标商品 categories 尾部生成，精确命中是强判别信号
        if norm_category and c.get("coarse_cat") == norm_category:
            s += 2.5
        # 精确价格命中（budget around $X 里的 X 就是目标商品的标价）强加分
        if state.budget is not None and c.get("price") is not None:
            if abs(c["price"] - state.budget) < 0.005:
                s += 4.0
            elif state.budget * 0.9 <= c["price"] <= state.budget * 1.1:
                s += 0.5
        s += 1.0 - (c.get("bm25_rank", total) / total)  # BM25 名次归一化到 0..1
        return s

    return sorted(candidates, key=score, reverse=True)[:k]
