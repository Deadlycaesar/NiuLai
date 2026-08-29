"""M2 稠密路 · Step 1：预计算 50k 商品 embedding（一键可重算，可复现性要求）。

配方（m2-spec/dense-route_spec.md §1-①，调研报告 §2.4 的 ESCI 亚军配方）：
    "{brand}, {title}, {color} [SEP] {bullets}"
brand 取 details 里的 Brand 键，缺失回退 store；color 用与 retriever 一致的正则提取；
bullets = features 列表。文本超过 bge 的 512 token 窗口由模型自动截断。

产物：data/embeddings.npz（已 gitignore，分发方式 B/E 另议）
    asins: (50000,) str 数组 —— 行顺序
    matrix: (50000, 384) float32，已 L2 归一化（余弦 = 点积）

用法：  python3 scripts/precompute_embeddings.py
环境：  需要 sentence-transformers；大陆拉模型用 HF_ENDPOINT=https://hf-mirror.com
"""

from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根目录

from src import config

_COLOR_RE = re.compile(r"\b(black|white|blue|red|pink|green|brown|gray|grey|purple|yellow|orange)\b", re.I)
_BATCH_SIZE = 256


def _extract_brand(product: dict) -> str:
    details = product.get("details")
    if isinstance(details, dict):
        for key, value in details.items():
            if "brand" in str(key).lower() and value not in (None, ""):
                return str(value)
    return str(product.get("store") or "")


def build_product_text(product: dict) -> str:
    """spec §1-① 配方：brand, title, color [SEP] bullets。"""
    brand = _extract_brand(product)
    title = str(product.get("title") or "")
    corpus = " ".join(
        [title]
        + [str(v) for v in (product.get("features") or [])]
        + ([f"{k} {v}" for k, v in product["details"].items()] if isinstance(product.get("details"), dict) else [])
    )
    color_match = _COLOR_RE.search(corpus)
    color = color_match.group(1).lower() if color_match else ""
    bullets = " ".join(str(v) for v in (product.get("features") or [])[:5])
    head = ", ".join(part for part in (brand, title, color) if part)
    return f"{head} [SEP] {bullets}".strip()


def main() -> None:
    import numpy as np
    from sentence_transformers import SentenceTransformer

    root = Path(__file__).resolve().parent.parent
    catalog_path = root / "data/catalog.jsonl"
    out_path = Path(config.EMBEDDINGS_PATH)
    if not out_path.is_absolute():
        out_path = root / out_path

    asins: list[str] = []
    texts: list[str] = []
    with catalog_path.open(encoding="utf-8") as handle:
        for line in handle:
            product = json.loads(line)
            asins.append(str(product["parent_asin"]))
            texts.append(build_product_text(product))
    print(f"加载 {len(asins)} 个商品，开始编码（模型 {config.EMBED_MODEL}）……")

    import torch
    device = "cuda" if torch.cuda.is_available() else "cpu"
    model = SentenceTransformer(config.EMBED_MODEL, device=device)
    print(f"编码设备：{device}")
    start = time.time()
    matrix = model.encode(
        texts,
        batch_size=_BATCH_SIZE,
        show_progress_bar=True,
        convert_to_numpy=True,
        normalize_embeddings=True,  # spec §1-③：归一化后余弦 = 点积
    ).astype(np.float32)
    elapsed = time.time() - start
    print(f"编码完成：{matrix.shape}，耗时 {elapsed:.0f}s")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(out_path, asins=np.array(asins), matrix=matrix)
    size_mb = out_path.stat().st_size / 1e6
    print(f"已写出 {out_path}（{size_mb:.0f}MB）")

    # 回读校验
    loaded = np.load(out_path, allow_pickle=False)
    assert loaded["matrix"].shape == (len(asins), matrix.shape[1])
    assert (loaded["asins"] == np.array(asins)).all()
    print("回读校验通过：行数/维度/顺序一致")


if __name__ == "__main__":
    main()
