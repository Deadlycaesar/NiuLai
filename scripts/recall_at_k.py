"""M2 的 KPI 脚本：测量 Recall@k —— 目标商品是否进入检索候选池。

复刻真实对话流（与线上 other_first 策略一致：开场 → 每轮问 other → parser 填槽），
每轮调用 retriever.retrieve()，记录目标商品在候选池中的最佳位置（1 起，0 = 未召回）。

用法：  python3 scripts/recall_at_k.py        （USE_DENSE=1 测稠密路）
输出：  全量/分场景的 Recall@10/20/50/100/pool（取该 session 各轮最佳位置）、
        目标平均位置、未召回清单。

注意：本脚本只读 evaluator 的模拟器函数，不修改任何官方文件。
池内顺序不影响 rank() 打分（rank 按自有公式重排整个池子），R@k 仅作诊断：
召回层对分数的硬约束是"目标在不在返回池里"（≈ R@pool）。
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # 仓库根目录

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
POOL_K = 100


def replay_session(retriever: Retriever, sample: dict, categories: dict, products: dict) -> list[int]:
    """跑完一个 session，返回每轮目标在候选池中的位置（0 = 未进池）。"""
    target = str(sample["ground_truth"]["parent_asin"])
    card, behavior = materialize_hidden_fields(sample, products)
    eff = {**sample, "intent_card": card, "behavior": behavior}
    state = DialogState(session_id="recall_probe", profile=sample["user_profile"])
    disclosed: set[str] = set()
    boundary_used = False
    override_applied = sample["scenario_type"] != "intent_override"
    msg = initial_message(eff, coarse_category(categories.get(target, [])), disclosed)

    positions: list[int] = []
    for turn in range(1, MAX_TURNS + 1):
        parser.update_state(state, msg, turn)
        candidates = retriever.retrieve(state, msg, k=POOL_K)
        pos = next((i + 1 for i, c in enumerate(candidates) if c["parent_asin"] == target), 0)
        positions.append(pos)
        if turn == MAX_TURNS:
            break
        override = behavior.get("override") or {}
        if not override_applied and turn + 1 == int(override.get("turn", 3)):
            override_applied = True
            msg = str(override.get("message", ""))
        else:
            msg, boundary_used = customer_reply(eff, "other", disclosed, boundary_used)
    return positions


def main() -> None:
    root = Path(__file__).resolve().parent.parent
    catalog_ids, categories, products = catalog_index(root / "data/catalog.jsonl")
    samples = [
        json.loads(line)
        for line in (root / "data/public_set.jsonl").open(encoding="utf-8")
        if line.strip()
    ]
    retriever = Retriever(root / "data/catalog.jsonl")

    per_scenario: dict[str, list[dict]] = defaultdict(list)
    for sample in samples:
        positions = replay_session(retriever, sample, categories, products)
        hit_positions = [p for p in positions if p > 0]
        best = min(hit_positions) if hit_positions else 0  # 0 = 全程未召回
        per_scenario[sample["scenario_type"]].append(
            {"sample_id": sample["sample_id"], "best_pos": best, "positions": positions}
        )

    cutoffs = (10, 20, 50, 100, 10**9)
    labels = ("R@10", "R@20", "R@50", "R@100", "R@pool")
    print(f"{'scenario':<16} {'n':>4} " + " ".join(f"{l:>7}" for l in labels) + f" {'avg_pos':>8}")
    all_rows = [row for rows in per_scenario.values() for row in rows]

    def report(name: str, rows: list[dict]) -> None:
        recalls = [sum(1 for r in rows if 0 < r["best_pos"] <= c) / len(rows) for c in cutoffs]
        hit_pos = [r["best_pos"] for r in rows if r["best_pos"] > 0]
        avg_pos = statistics.fmean(hit_pos) if hit_pos else 0.0
        print(f"{name:<16} {len(rows):>4} " + " ".join(f"{r:>7.3f}" for r in recalls) + f" {avg_pos:>8.1f}")

    for name, rows in sorted(per_scenario.items(), key=lambda kv: kv[0]):
        report(name, rows)
    report("TOTAL", all_rows)

    missed = [r["sample_id"] for r in all_rows if r["best_pos"] == 0]
    print(f"\n全程未召回（{len(missed)} 条）: {', '.join(missed) or '无'}")
    print("注：R@pool 含稠密路追加区（位次可超 100）；池内顺序不影响 rank() 打分，R@k 仅供诊断。")


if __name__ == "__main__":
    main()
