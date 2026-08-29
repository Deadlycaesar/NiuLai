"""M2 诊断实验：稠密相似度对排序层有没有区分度？

问题：命中但排名靠后（rank 4-10，指纹打平局）和 miss 的 session 里，
目标商品的 dense_sim 是否在候选池中系统性靠前？
- 是 → route_scores（dense_sim 交给 C 的排序公式）有数据支撑
- 否 → 稠密信号对排序无帮助，此路线到此为止

方法：回放对话（与 recall_at_k 同口径），在命中轮/第 10 轮取候选池，
按 dense_sim 重新排名，记录目标的 sim 名次。按最终排名分组对比。

用法：USE_DENSE=1 python3 scripts/dense_signal_diagnostic.py
（依赖 results_merged.json 里的逐 session 结果做分组）
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from evaluator.local_evaluator import (
    catalog_index,
    coarse_category,
    customer_reply,
    initial_message,
    materialize_hidden_fields,
)
from src.dialog import parser
from src.dialog.state import DialogState
from src.retrieval.retriever import Retriever

MAX_TURNS = 10


def probe_turn(retriever: Retriever, sample: dict, categories: dict, products: dict,
               probe_at: int) -> int | None:
    """回放到 probe_at 轮，返回目标在该轮候选池中按 dense_sim 的名次（None = 不在池里）。"""
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    eff = {**sample, "intent_card": card, "behavior": behavior}
    state = DialogState(session_id="probe", profile=sample["user_profile"])
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    msg = initial_message(eff, coarse_category(categories.get(target, [])), disclosed)

    for turn in range(1, MAX_TURNS + 1):
        parser.update_state(state, msg, turn)
        candidates = retriever.retrieve(state, msg, k=100)
        if turn == probe_at:
            query = retriever._dense_query(state)
            sims = dict(retriever.dense.search(query, 500)) if retriever.dense else {}
            # 池内按 dense_sim 降序排名（无 sim 的候选排最后）
            ranked = sorted(
                (c["parent_asin"] for c in candidates),
                key=lambda a: sims.get(a, -1.0),
                reverse=True,
            )
            return ranked.index(target) + 1 if target in ranked else None
        override = behavior.get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            msg = str(override.get("message", ""))
        else:
            msg, boundary_used = customer_reply(eff, "other", disclosed, boundary_used)
    return None


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    catalog_ids, categories, products = catalog_index(root / "data/catalog.jsonl")
    samples = [
        json.loads(line)
        for line in (root / "data/public_set.jsonl").open(encoding="utf-8")
        if line.strip()
    ]
    results = {s["sample_id"]: s for s in json.loads((root / "results_merged.json").read_text(encoding="utf-8"))["sessions"]}
    retriever = Retriever(root / "data/catalog.jsonl")
    assert retriever.dense is not None, "需要 USE_DENSE=1"

    groups: dict[str, list[int]] = defaultdict(list)
    for sample in samples:
        sid = sample["sample_id"]
        r = results[sid]
        probe_at = r["first_hit_turn"] or MAX_TURNS
        if not r["hit"]:
            group = "miss"
        elif r["best_rank"] == 1:
            group = "rank1"
        elif r["best_rank"] <= 3:
            group = "rank2-3"
        else:
            group = "rank4-10"
        sim_rank = probe_turn(retriever, sample, categories, products, probe_at)
        if sim_rank is not None:
            groups[group].append(sim_rank)
        else:
            groups[group + "（未进池）"].append(0)

    print(f"{'分组':<14} {'n':>4} {'sim名次中位':>10} {'sim名次均值':>10} {'sim≤3占比':>9}")
    for name in ("rank1", "rank2-3", "rank4-10", "miss"):
        vals = groups.get(name, [])
        if not vals:
            continue
        top3 = sum(1 for v in vals if v <= 3) / len(vals)
        print(f"{name:<14} {len(vals):>4} {statistics.median(vals):>10.0f} {statistics.fmean(vals):>10.1f} {top3:>9.0%}")


if __name__ == "__main__":
    main()
