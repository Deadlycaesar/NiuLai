"""入口壳：官方评测器硬编码 `from starter.agent import Agent`，此文件只做转发。

业务实现全部在 src/ 下（见 AGENTS.md 目录归属）。不要在这里写任何逻辑。

演示/消融用开关：AGENT_IMPL=baseline 切回官方 weak-BM25 基线（src/baselines/weak_bm25.py），
默认为我们的实现。例：
  AGENT_IMPL=baseline python3 -m evaluator.local_evaluator --output results_baseline.json
"""

import os

if os.environ.get("AGENT_IMPL") == "baseline":
    from src.baselines.weak_bm25 import Agent
else:
    from src.dialog.agent import ShoppingAgent as Agent

__all__ = ["Agent"]
