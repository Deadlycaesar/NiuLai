"""M4 诊断：`user_profile` 与"这个用户买了哪件"之间到底有没有统计关联？
（实验 22 的脚本；对标 B 的 scripts/dense_signal_diagnostic.py 之于实验 7）

用法：python3 scripts/profile_signal_diagnostic.py

为什么需要这个脚本：此前判断 profile 有没有用，靠的是"接进 retriever/ranker
跑一遍看分数"（实验 13/21），一次只能证伪一种接法，永远回答不了"换个权重/
换个门控/只在冷启动用行不行"。本脚本改用信息论口径，一次性给整类问题定论。

方法与那个致命混淆：
  朴素做法是比 P(profile词命中目标) / P(profile词命中随机商品) —— 实测 1.745x，
  看着有信号。但这是假象：目标商品都是热门商品（实验 10a：有 price 者占 89%
  vs 全目录 20.8%），文案更长更丰富，【任何】词都更容易命中，与"匹配"无关。

  故改用置换检验消除混淆——对同一批目标商品，比较
    A) 真实配对：用户 i 的 profile vs 用户 i 的目标
    B) 随机配对：用户 j 的 profile vs 用户 i 的目标（j≠i）
  商品完全相同、只换 profile，文案长度/热度/品类全部被控制住。

  A ≈ B  → profile 与"买了哪件"无关，1.745x 全是文案长度的假象
  A >> B → 配对本身有信息，值得接进排序

实测结论（2026-08-30，公开集 199 条有效样本）：
  真实 0.2553 vs 随机 0.2501 = 1.021x，z=+0.93，p≈0.18（200 次置换）—— 不显著。
  → profile 文本信号的天花板由信息量决定，不由接法决定；任何策略都提取不出来。
"""
from __future__ import annotations

import json
import random
import statistics
import sys
from pathlib import Path

ROOT = Path(r"D:\Documents\Study\Projects\TikTok Heckjam")
sys.path.insert(0, str(ROOT))

from evaluator.local_evaluator import load_jsonl  # noqa: E402
from src.memory.lexicon import profile_soft_terms  # noqa: E402
from src.dialog.normalize import normalize  # noqa: E402

samples = load_jsonl(str(ROOT / "data/public_set.jsonl"))
targets = {str(s["ground_truth"]["parent_asin"]) for s in samples}
FIELDS = ("title", "features", "details", "description", "categories", "store")


def text_of(p: dict) -> str:
    parts = []
    for f in FIELDS:
        v = p.get(f)
        if isinstance(v, dict):
            parts.extend(f"{k} {i}" for k, i in v.items())
        elif isinstance(v, list):
            parts.extend(str(i) for i in v)
        elif v is not None:
            parts.append(str(v))
    return normalize(" ".join(parts))


target_text: dict[str, str] = {}
with (ROOT / "data/catalog.jsonl").open(encoding="utf-8") as fh:
    for line in fh:
        try:
            p = json.loads(line)
        except Exception:
            continue
        asin = str(p.get("parent_asin", ""))
        if asin in targets:
            target_text[asin] = text_of(p)

pairs = []
for s in samples:
    terms = profile_soft_terms(s["user_profile"])
    tgt = target_text.get(str(s["ground_truth"]["parent_asin"]))
    if tgt and terms:
        pairs.append((terms, tgt))

print(f"有效样本 {len(pairs)} 条\n")


def match_frac(terms, text) -> float:
    return sum(1 for t in terms if t in text) / len(terms)


# A) 真实配对
real = [match_frac(terms, tgt) for terms, tgt in pairs]

# B) 随机配对：同一批目标，profile 打乱
rng = random.Random(2026)
shuffled_scores = []
for _ in range(50):  # 50 次置换取均值，压随机波动
    idx = list(range(len(pairs)))
    rng.shuffle(idx)
    for i, j in enumerate(idx):
        if i == j:
            continue
        shuffled_scores.append(match_frac(pairs[j][0], pairs[i][1]))

print("=== 置换检验（控制商品文案长度/热度）===")
print(f"真实配对  profile_i vs target_i ：均值 {statistics.mean(real):.4f}  中位 {statistics.median(real):.4f}  n={len(real)}")
print(f"随机配对  profile_j vs target_i ：均值 {statistics.mean(shuffled_scores):.4f}  中位 {statistics.median(shuffled_scores):.4f}  n={len(shuffled_scores)}")
ratio = statistics.mean(real) / statistics.mean(shuffled_scores)
print(f"\n真实/随机 = {ratio:.4f}x")

# 简单显著性：真实均值是否落在置换分布的极端
perm_means = []
for _ in range(200):
    idx = list(range(len(pairs)))
    rng.shuffle(idx)
    vals = [match_frac(pairs[j][0], pairs[i][1]) for i, j in enumerate(idx) if i != j]
    perm_means.append(statistics.mean(vals))
real_mean = statistics.mean(real)
better = sum(1 for m in perm_means if m >= real_mean)
print(f"200 次置换里，随机配对均值 >= 真实配对均值 的次数：{better}/200  (p≈{better/200:.3f})")
print(f"置换分布 均值={statistics.mean(perm_means):.4f} 标准差={statistics.pstdev(perm_means):.4f}")
if statistics.pstdev(perm_means) > 0:
    z = (real_mean - statistics.mean(perm_means)) / statistics.pstdev(perm_means)
    print(f"真实配对的 z 分数 = {z:+.2f}")
