# 五分钟上手（会上演示脚本）

> 已在 Linux + Python 3.13 实测。要求 Python ≥ 3.10，baseline 无任何第三方依赖。

## 1. 克隆并准备数据（约 1 分钟）

```bash
git clone https://github.com/Deadlycaesar/NiuLai.git
cd NiuLai
python3 scripts/prepare_catalog.py
```

预期输出：`Checksum verified.` + `Catalog extracted to .../data/catalog.jsonl`（60MB，已被 gitignore）。

## 2. 跑官方 baseline 评测（约 33 秒）

```bash
python3 -m evaluator.local_evaluator
```

## 3. 核对分数（这一步是重点）

```bash
python3 - <<'EOF'
import json
r = json.load(open('results.json'))
print('TechnicalScore =', r['recommended_technical_score'])   # 应为 0.10671，逐位一致
for k, v in r['scenario_metrics'].items():
    print(f"  {k:16s} hit={v['hit_rate_at_10']:.3f}  mttc={v['mttc']:.2f}")
EOF
```

2026-08-29 实测结果（与 `docs/baseline_results.json` 完全一致，评测器是确定性的）：

| 场景 | 占比 | HitRate@10 | MTTC |
|---|---|---|---|
| buying | 40% | 0.238 | 8.63 |
| browsing | 40% | **0.025** | 10.75 |
| intent_override | 15% | 0.133 | 10.07 |
| boundary | 5% | 0.000 | 11.00 |
| **总分 TechnicalScore** | | **0.10671** | |

## 4. 看懂这张表（会上讲这三句话）

1. **评测循环只要 33 秒**（无 LLM 时）——改一行代码半分钟就知道分数涨没涨，迭代成本极低。
2. baseline 在 **browsing（占 40%）上几乎全灭**（0.025）：它无状态、从不提问，对"我还在随便看看"无解。**我们的提分主战场在这里。**
3. baseline 从不提问、每轮只用当前这句话检索——光是"跨轮累积约束 + 每轮必带推荐 + 会提问"三件事就能大幅超过 0.107。

## 5. 领任务之后

1. 读 `AGENTS.md`（全局约定 + 红线）。
2. 读 `team/briefs/` 里自己那份模块说明书，**把它和 AGENTS.md 一起喂给你的 AI 编码助手**。
3. 从 `main` 拉分支 `feat/<模块>-<功能>`，只改自己目录，提 PR 前跑全量评测并把分数写进 PR 描述。
