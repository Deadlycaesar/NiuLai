"""分层抽样评测（M5/E 的活，E 缺席期间由全组共同维护）。

为什么需要它：纯规则路径跑全量 200 条只要 ~10 秒，**默认就该跑全量**。
但 LLM 路径每次调用约 0.85 秒，全量要十几分钟且要花钱——那时才用这个脚本。

关键点是**分层**：四个场景的比例（buying/browsing/override/boundary = 40/40/15/5）
必须在抽样里保持，否则方差大到没法跟别的实验比较。同一个 --n 和 --seed
永远抽出同一批样本，所以 A/B 对照必须用同一组参数。

    python3 scripts/eval_sample.py --n 40                    # 规则路径抽样
    USE_LLM=1 python3 scripts/eval_sample.py --n 40          # LLM 路径抽样（与上一行可直接对比）
    python3 scripts/eval_sample.py --n 40 --repeat 3         # 跑 3 次取均值（LLM 不可复现时必用）
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "data" / "public_set.jsonl"


def stratified_sample(rows: list[dict], n: int, seed: int) -> list[dict]:
    """按 scenario_type 的原始比例抽样；每层内用固定种子随机，保证可复现。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row["scenario_type"]].append(row)

    total = len(rows)
    picked: list[dict] = []
    # 先按比例取整数部分，再把余额按"小数部分大的优先"补齐，避免小场景被抹成 0
    remainders: list[tuple[float, str]] = []
    for name, items in sorted(buckets.items()):
        exact = n * len(items) / total
        take = int(exact)
        picked += random.Random(f"{seed}:{name}").sample(items, min(take, len(items)))
        remainders.append((exact - take, name))
    for _, name in sorted(remainders, reverse=True):
        if len(picked) >= n:
            break
        pool = [r for r in buckets[name] if r not in picked]
        if pool:
            picked.append(random.Random(f"{seed}:{name}:fill").choice(pool))
    picked.sort(key=lambda r: r["sample_id"])
    return picked[:n]


def run_once(samples: list[dict]) -> dict:
    with tempfile.NamedTemporaryFile("w", suffix=".jsonl", delete=False, encoding="utf-8") as tmp:
        for row in samples:
            tmp.write(json.dumps(row, ensure_ascii=False) + "\n")
        dataset = tmp.name
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
        output = tmp.name
    result = subprocess.run(
        [sys.executable, "-m", "evaluator.local_evaluator", "--dataset", dataset, "--output", output],
        capture_output=True, text=True, cwd=ROOT,
    )
    if result.returncode != 0:
        raise SystemExit((result.stderr or "评测器执行失败").strip())
    return json.load(open(output, encoding="utf-8"))


def main() -> None:
    parser = argparse.ArgumentParser(description="分层抽样评测（LLM 路径太慢时用）")
    parser.add_argument("--n", type=int, default=40, help="抽样条数（默认 40）")
    parser.add_argument("--seed", type=int, default=2026, help="抽样种子——A/B 对照必须用同一个")
    parser.add_argument("--repeat", type=int, default=1, help="重复跑几次取均值（LLM 不可复现时用）")
    args = parser.parse_args()

    rows = [json.loads(line) for line in DATASET.open(encoding="utf-8") if line.strip()]
    samples = stratified_sample(rows, args.n, args.seed)

    mix = defaultdict(int)
    for row in samples:
        mix[row["scenario_type"]] += 1
    print(f"抽样 {len(samples)}/{len(rows)} 条  seed={args.seed}  场景分布: {dict(sorted(mix.items()))}")

    scores, mrrs, hits, tokens = [], [], [], []
    for i in range(args.repeat):
        result = run_once(samples)
        scores.append(result["recommended_technical_score"])
        mrrs.append(result["mrr"])
        hits.append(result["hit_rate_at_10"])
        tokens.append(result["reported_token_usage"]["total_tokens"])
        tag = f"  第 {i + 1} 次" if args.repeat > 1 else ""
        print(f"  score={scores[-1]:.4f}  hit={hits[-1]:.3f}  mrr={mrrs[-1]:.3f}  "
              f"mttc={result['mttc']:.2f}  tokens={tokens[-1]}{tag}")

    if args.repeat > 1:
        print(f"\n{args.repeat} 次均值: score={statistics.fmean(scores):.4f} "
              f"(±{statistics.pstdev(scores):.4f})  hit={statistics.fmean(hits):.3f}  "
              f"mrr={statistics.fmean(mrrs):.3f}")
        if statistics.pstdev(scores) > 0.005:
            print("⚠️  多次跑分方差 >0.005——该配置不可复现，记 experiments.md 时必须写明均值与次数。")
    print("\n提示：抽样分数与全量分数不可直接比较，只能和同 --n/--seed 的另一次抽样比。")


if __name__ == "__main__":
    main()
