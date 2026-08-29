"""M2 稠密向量路（m2-spec/dense-route_spec.md §1-②③④⑦）。

启动时加载预计算的 50k 商品向量（scripts/precompute_embeddings.py 产出的 npz），
运行时用同一 bge 模型把查询文本编码成向量，矩阵点积取 top-k（spec §1-③：
向量已 L2 归一化，余弦相似度 = 点积，numpy 暴力法，不上 faiss）。

降级（spec §1-⑦，红线）：USE_DENSE=0 / npz 缺失 / 依赖缺失 / 模型权重未缓存，
任一不满足 → from_env() 返回 None，Retriever 退回纯 BM25，行为与 v1 完全一致。
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from src import config

# bge 查询侧指令前缀（spec §1-④）：查询编码时必须加，商品侧（预计算）不加
QUERY_INSTRUCTION = "Represent this sentence for searching relevant passages: "


def _warn(reason: str) -> None:
    """USE_DENSE=1 但资产缺失时显式降级——防"以为开了稠密路其实跑的纯 BM25"（留言板 T-004）。"""
    print(f"[M2] USE_DENSE=1 但稠密路未生效（{reason}），本场为纯 BM25。", file=sys.stderr)


class DenseIndex:
    def __init__(self, asins, matrix, model) -> None:
        self.asins = asins          # (N,) str 数组，与 matrix 行一一对应
        self.matrix = matrix        # (N, 384) float32，已归一化
        self.model = model          # SentenceTransformer
        self._vec_cache: dict[str, object] = {}  # 查询文本 → 向量（约束问干后逐轮不变，省重复编码）

    @classmethod
    def from_env(cls) -> "DenseIndex | None":
        """按 spec §1-⑦ 做全链路降级：任何资产缺失都返回 None，绝不抛给上层。"""
        if not config.USE_DENSE:
            return None  # 用户没开 = 静默；开了却降级才需要警告
        try:
            path = Path(config.EMBEDDINGS_PATH)
            if not path.exists():
                _warn(f"npz 缺失：{path}")
                return None
            import numpy as np
            from sentence_transformers import SentenceTransformer

            # 断网红线：只读本地缓存，绝不在运行时尝试下载（预计算脚本已拉过权重）
            os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
            data = np.load(path, allow_pickle=False)
            model = SentenceTransformer(config.EMBED_MODEL, device="cpu")
            return cls(asins=data["asins"], matrix=data["matrix"], model=model)
        except Exception as exc:
            _warn(f"{type(exc).__name__}: {exc}")
            return None

    def search(self, query_text: str, top_k: int) -> list[tuple[str, float]]:
        """返回 [(parent_asin, cosine_sim)]，按相似度降序，最多 top_k 条。"""
        if not query_text.strip():
            return []
        import numpy as np

        vector = self._vec_cache.get(query_text)
        if vector is None:
            vector = self.model.encode(
                [QUERY_INSTRUCTION + query_text],
                convert_to_numpy=True,
                normalize_embeddings=True,
            )[0].astype(np.float32)
            self._vec_cache[query_text] = vector
        sims = self.matrix @ vector
        top_k = min(top_k, len(self.asins))
        # argpartition 拿 top-k 再局部排序，避免全量 sort
        idx = np.argpartition(-sims, top_k - 1)[:top_k]
        idx = idx[np.argsort(-sims[idx])]
        return [(str(self.asins[i]), float(sims[i])) for i in idx]
