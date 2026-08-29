"""全局开关（正式的配置层归 M5/E，先用环境变量占位）。

.env 里的键值会被加载为默认值（.env 已 gitignore，绝不提交）。
"""

import os
from pathlib import Path


def _load_dotenv() -> None:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

# 提问策略：other_first（默认）| entropy
ASK_POLICY = os.environ.get("ASK_POLICY", "other_first")

# 检索候选池大小
CANDIDATE_POOL = int(os.environ.get("CANDIDATE_POOL", "300"))

# M3：是否启用 LLM 增强路径（离线降级是硬要求，默认关）
USE_LLM = os.environ.get("USE_LLM", "0") == "1"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "20"))
LLM_RERANK_POOL = int(os.environ.get("LLM_RERANK_POOL", "20"))  # 送 LLM 精排的候选数

# budget 约束的价格窗口（±比例）
PRICE_WINDOW = float(os.environ.get("PRICE_WINDOW", "0.3"))
