"""T4 稳定性硬化验收（A）：评测器保护圈外的两个入口 + 畸形输入。

背景（evaluator/local_evaluator.py 核实）：评测器只保护 respond()（异常 = 空响应丢一轮）；
Agent 构造和 reset() 抛异常 = 整场评测直接崩。正式评测还可能把超时/非法输出记 miss。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.dialog.agent import ShoppingAgent  # noqa: E402

_VALID_ASK = {"category", "material", "color", "size", "style", "brand",
              "budget", "feature", "use_case", "other"}

_PRODUCTS = [
    {"parent_asin": "A001", "title": "Blue Cotton Socks", "price": 9.99,
     "features": ["100% Cotton", "Machine Wash"], "categories": ["Clothing", "Socks"]},
    {"parent_asin": "A002", "title": "Leather Belt", "price": 19.99,
     "features": ["100% Leather"], "categories": ["Clothing", "Belts"]},
    {"parent_asin": "A003", "title": "Wool Scarf", "price": 14.5,
     "features": ["Warm wool blend"], "categories": ["Clothing", "Scarves"]},
]


def _write_catalog(tmp_path, corrupt=False):
    lines = [json.dumps(p) for p in _PRODUCTS]
    if corrupt:
        lines.insert(1, "{not valid json!!!")          # 坏 JSON
        lines.insert(3, json.dumps({"title": "no asin"}))  # 缺 parent_asin
        lines.append("")                                # 空行
    path = tmp_path / "catalog.jsonl"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def _assert_legal(resp, top_k=10):
    assert isinstance(resp, dict)
    assert isinstance(resp["message"], str)
    assert resp["ask_attribute"] in _VALID_ASK
    recs = resp["recommendations"]
    assert isinstance(recs, list) and len(recs) <= top_k
    for rec in recs:
        assert isinstance(rec["parent_asin"], str)


def test_corrupt_catalog_lines_skipped(tmp_path):
    agent = ShoppingAgent(_write_catalog(tmp_path, corrupt=True))
    assert len(agent.retriever.products) == len(_PRODUCTS)
    assert agent.retriever.skipped_lines == 3  # 坏 JSON + 缺 asin + 空行
    agent.reset("s", {})
    _assert_legal(agent.respond("s", "I'm looking for Socks. A key requirement is: 100% Cotton.", 1, 10))


def test_reset_never_raises(tmp_path):
    agent = ShoppingAgent(_write_catalog(tmp_path))
    for profile in (None, [], "junk", 42, {"preference_tags": None}):
        agent.reset("s1", profile)  # 不抛即过
    _assert_legal(agent.respond("s1", "I'm looking for Belts, but I'm still exploring.", 1, 10))


def test_respond_malformed_inputs(tmp_path):
    agent = ShoppingAgent(_write_catalog(tmp_path))
    agent.reset("s2", {})
    for msg in ("", "   ", None, "🧦" * 500, "x" * 200_000,
                "Actually, please ignore my earlier preference.",
                "For that, what matters is: .", "I'm looking for "):
        _assert_legal(agent.respond("s2", msg, 1, 10))


def test_respond_without_reset(tmp_path):
    agent = ShoppingAgent(_write_catalog(tmp_path))
    _assert_legal(agent.respond("ghost", "I'm looking for Scarves. A key requirement is: Warm wool blend.", 1, 10))


def test_fallback_recommends_last_ranked(tmp_path):
    agent = ShoppingAgent(_write_catalog(tmp_path))
    agent.reset("s3", {})
    first = agent.respond("s3", "I'm looking for Socks. A key requirement is: 100% Cotton.", 1, 10)
    assert first["recommendations"]
    # None 消息触发内部异常 → 兜底路径必须带上一轮的推荐而不是空手
    fallback = agent.respond("s3", None, 2, 10)
    assert [r["parent_asin"] for r in fallback["recommendations"]] == \
           [r["parent_asin"] for r in first["recommendations"]]
