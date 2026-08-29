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

# M3：热度先验权重（0 = 关闭）。依据：目标取自真实购买记录，真实购买集中在热门商品。
# ⚠️ 分数随该值单调上升到 w=6，是过拟合信号——保守取 1~2，调高前先看 hard 分项。
POP_WEIGHT = float(os.environ.get("POP_WEIGHT", "1.5"))

# budget 约束的价格窗口（±比例）
PRICE_WINDOW = float(os.environ.get("PRICE_WINDOW", "0.3"))

# M2 稠密路：USE_DENSE=1 且资产齐全才启用，任一条件不满足自动降级纯 BM25（spec §1-⑦）
USE_DENSE = os.environ.get("USE_DENSE", "0") == "1"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH", "data/embeddings.npz")
DENSE_TOP_K = int(os.environ.get("DENSE_TOP_K", "100"))
RRF_K = int(os.environ.get("RRF_K", "60"))
