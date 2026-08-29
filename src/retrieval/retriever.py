"""M2 多路检索 —— 骨架占位实现（B 的地盘，接口冻结、实现待换）。

当前占位 = 官方 baseline 的 FTS5-BM25 + 约束子串核验 + budget 过滤。
B 接手后：升级字段加权、加稠密向量路 + RRF 融合、结构化过滤完整版。
`retrieve()` 的签名和 Candidate 字段是 A↔B 接口（SPEC §5），改动需全组同意。

Candidate 字段说明（A 的信息增益策略依赖 color/material/price 等结构化字段算熵）：
  parent_asin, title, price(float|None), color(str|None), material(str|None),
  norm_text(归一化全文，用于约束子串匹配), bm25_rank(int, 越小越好), match_count(int),
  rating_number(int, 评论数) / feature_count(int, features 条数)——M3 的先验轴打分用
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

from src import config
from src.dialog.state import DialogState
from src.retrieval.dense import DenseIndex

# 与评测器一致的正则（镜像自 evaluator/local_evaluator.py，勿 import 以免循环依赖）
_MATERIAL_RE = re.compile(r"\b(cotton|polyester|nylon|leather|wool|spandex|silk|rayon|fabric)\b", re.I)
_COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
_SEARCH_FIELDS = ("title", "features", "details", "description", "categories", "store")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_STOPWORDS = {
    "the", "a", "an", "and", "or", "for", "with", "of", "to", "in", "on", "is", "are",
    "i", "im", "my", "looking", "still", "exploring", "but", "what", "need", "that",
    "matters", "requirement", "key",
}


def _searchable_text(product: dict) -> str:
    parts: list[str] = []
    for field in _SEARCH_FIELDS:
        value = product.get(field)
        if isinstance(value, dict):
            parts.extend(f"{key} {item}" for key, item in value.items())
        elif isinstance(value, list):
            parts.extend(str(item) for item in value)
        elif value is not None:
            parts.append(str(value))
    return " ".join(parts).strip()


def normalize(text: str) -> str:
    """小写 + 非字母数字折叠为单空格。约束原文和商品全文都过这个，子串匹配才稳。"""
    return re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()


def constraint_match_token(value: str) -> str:
    """把一条约束原文变成用于子串匹配的归一化串。'color: blue' 只匹配颜色词本身。"""
    lowered = value.lower()
    if lowered.startswith("color:"):
        return normalize(lowered.split(":", 1)[1])
    return normalize(value)


def coarse_category(values: list[str]) -> str:
    """镜像评测器的粗品类算法：categories 最后两段非泛化部分（开场句的 X 就是它）。"""
    excluded = {"clothing", "clothing shoes & jewelry", "clothing, shoes & jewelry"}
    cleaned: list[str] = []
    for value in values:
        for part in str(value).split(","):
            part = part.strip()
            if part and part.lower() not in excluded:
                cleaned.append(part)
    return " ".join(cleaned[-2:]) if cleaned else "clothing item"


class Retriever:
    def __init__(self, catalog_path: str = "data/catalog.jsonl") -> None:
        self.products: dict[str, dict] = {}
        connection = sqlite3.connect(":memory:")
        connection.execute(
            "CREATE VIRTUAL TABLE products USING fts5("
            "parent_asin UNINDEXED, title, categories, features, details, store, description, "
            "tokenize='unicode61 remove_diacritics 2')"
        )
        rows = []
        with Path(catalog_path).open(encoding="utf-8") as handle:
            for line in handle:
                product = json.loads(line)
                parent_asin = str(product["parent_asin"])
                text = _searchable_text(product)
                price = product.get("price")
                try:
                    price = float(price) if price not in (None, "") else None
                except (TypeError, ValueError):
                    price = None
                material = _MATERIAL_RE.search(text)
                color = _COLOR_RE.search(text)
                self.products[parent_asin] = {
                    "parent_asin": parent_asin,
                    "title": str(product.get("title") or ""),
                    "price": price,
                    "material": material.group(1).lower() if material else None,
                    "color": color.group(1).lower() if color else None,
                    "norm_text": normalize(text),
                    "rating_number": int(product.get("rating_number") or 0),
                    "feature_count": len(product.get("features") or []),
                    "coarse_cat": normalize(coarse_category(product.get("categories") or [])),
                }
                rows.append((
                    parent_asin,
                    str(product.get("title") or ""),
                    " ".join(str(v) for v in (product.get("categories") or [])),
                    " ".join(str(v) for v in (product.get("features") or [])),
                    " ".join(f"{k} {v}" for k, v in (product.get("details") or {}).items())
                    if isinstance(product.get("details"), dict) else "",
                    str(product.get("store") or ""),
                    " ".join(str(v) for v in (product.get("description") or []))
                    if isinstance(product.get("description"), list) else str(product.get("description") or ""),
                ))
        connection.executemany("INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?)", rows)
        connection.commit()
        self.connection = connection
        # 稠密路（spec §1-⑦）：USE_DENSE=0 或资产缺失时为 None，自动降级纯 BM25
        self.dense = DenseIndex.from_env()

    # ---- 查询构建：槽位原文 + 品类 + 当前消息的去停用词 term ----
    def _query_terms(self, state: DialogState, message: str) -> list[str]:
        text = " ".join([*state.constraint_values(), state.category, message])
        terms: list[str] = []
        for token in _TOKEN_RE.findall(text.lower()):
            if len(token) > 1 and token not in _STOPWORDS and token not in terms:
                terms.append(token)
        return terms[:40]

    # ---- 稠密路查询（spec §1-④ v1）：槽位约束原文（除 budget）+ 品类 ----
    def _dense_query(self, state: DialogState) -> str:
        parts = [v for v in state.constraint_values() if not v.lower().startswith("budget")]
        if state.category:
            parts.append(state.category)
        return " ".join(parts)

    # ---- 多路融合（spec §1-⑤）：非置换式并集 —— BM25 顺序原样保留，稠密路独有候选追加在后。
    # 消融记录：RRF(k=60) 平权融合实测负收益（Recall@100 0.995→0.970，avg_pos 25.6→30.2）——
    # 稠密查询含 "Imported"/礼物话术等语义噪声，噪声候选把 BM25 池 40-100 位的好候选挤出截断线。
    # 且 retrieve() 返回顺序不影响下游打分（rank() 用自有公式重排），融合只需保证"捞全"。
    def _fuse_dense(self, state: DialogState, candidates: list[dict], match_tokens: list[str]) -> list[dict]:
        dense_hits = self.dense.search(self._dense_query(state), config.DENSE_TOP_K)
        have = {c["parent_asin"] for c in candidates}
        # 有预算约束时，稠密补充的候选同样受价格窗约束（镜像 budget 硬过滤的意图）
        low = state.budget * (1 - config.PRICE_WINDOW) if state.budget is not None else None
        high = state.budget * (1 + config.PRICE_WINDOW) if state.budget is not None else None
        for asin, _sim in dense_hits:
            if asin in have or asin not in self.products:
                continue
            info = self.products[asin]
            if low is not None and (info["price"] is None or not (low <= info["price"] <= high)):
                continue
            # 稠密路独有候选：补齐 Candidate 字段，bm25_rank 给哨兵值（不打乱 BM25 名次语义）
            matched = sum(1 for t in match_tokens if t in info["norm_text"])
            candidates.append({**info, "bm25_rank": config.CANDIDATE_POOL, "match_count": matched})
            have.add(asin)
        return candidates

    def retrieve(self, state: DialogState, message: str, k: int = 100) -> list[dict]:
        terms = self._query_terms(state, message)
        if not terms:
            return []
        query = " OR ".join(f'"{term}"' for term in terms)
        cursor = self.connection.execute(
            "SELECT parent_asin, bm25(products, 0.0, 6.0, 4.0, 2.5, 2.5, 1.5, 1.0) AS score "
            "FROM products WHERE products MATCH ? ORDER BY score LIMIT ?",
            (query, config.CANDIDATE_POOL),
        )
        match_tokens = [constraint_match_token(v) for v in state.constraint_values()]
        match_tokens = [t for t in match_tokens if t and not t.startswith("budget")]
        candidates: list[dict] = []
        for rank, (parent_asin, _score) in enumerate(cursor.fetchall()):
            info = self.products[parent_asin]
            matched = sum(1 for token in match_tokens if token in info["norm_text"])
            candidates.append({**info, "bm25_rank": rank, "match_count": matched})

        # budget 硬过滤（±PRICE_WINDOW），过滤后不足 k 个则放宽为软加权
        if state.budget is not None:
            low = state.budget * (1 - config.PRICE_WINDOW)
            high = state.budget * (1 + config.PRICE_WINDOW)
            filtered = [c for c in candidates if c["price"] is not None and low <= c["price"] <= high]
            if len(filtered) >= min(k, 10):
                candidates = filtered
        if len(candidates) > max(k, 10):
            candidates = candidates[: max(k, 10)]

        # 稠密路补充召回（spec §1-⑤；self.dense 为 None 时跳过，纯 BM25 与 v1 一致）。
        # 放在截断【之后】追加：BM25 top-k 一个不动，稠密独有候选附在队尾，保证不被截掉。
        if self.dense is not None:
            candidates = self._fuse_dense(state, candidates, match_tokens)
        return candidates
