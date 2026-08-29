"""全局开关（正式的配置层归 M5/E，先用环境变量占位）。"""

import os

# 提问策略：other_first（默认）| entropy
ASK_POLICY = os.environ.get("ASK_POLICY", "other_first")

# 检索候选池大小
CANDIDATE_POOL = int(os.environ.get("CANDIDATE_POOL", "300"))

# 预留给 M3：是否启用 LLM 增强路径（骨架阶段恒为 0）
USE_LLM = os.environ.get("USE_LLM", "0") == "1"

# budget 约束的价格窗口（±比例）
PRICE_WINDOW = float(os.environ.get("PRICE_WINDOW", "0.3"))
