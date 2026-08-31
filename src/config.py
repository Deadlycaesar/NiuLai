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

# M1：LLM 兜底解析（第三层防线：严格模板 → 规则载荷抽取 → LLM 逐字片段抽取）。
# 只在前两层落空、salvage 即将退回"整句切分"最弱路径时触发；LLM 产出强制过
# verbatim 校验（归一化后必须是原消息子串），确保不破坏逐字指纹信号。
# 08-31 起默认【开】(实验 41)：L0 构造性零触发——公开卷 llm_calls=0、分数逐位不变，
# 只在规则失手时介入；改写档增益 L2 +0.036 / L3 +0.060 / L4 +0.098，且 L3/L4 的 HitRate 回到 1.000。
# 无 key/断网时两次失败即熔断，退回纯规则路径（分数等于本层不存在）。
# 官方计分环境可能禁网（docs/submission_rules.md:59-64），提交须声明本层为"增强模式"而非依赖。
LLM_PARSE = os.environ.get("LLM_PARSE", "1") == "1"
LLM_BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.deepseek.com")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
LLM_API_KEY = os.environ.get("DEEPSEEK_API_KEY", "")
# 45 而非 20：实测 GLM-4.7-Flash 免费额度单次调用可达 21.5s，20s 超时会导致
# 整轮实验静默降级到规则路径（C-T9（实验 25a）第 2 次复跑 tokens=0 即此故障）。
LLM_TIMEOUT = float(os.environ.get("LLM_TIMEOUT", "45"))
# 解析层专用超时（08-31）：45s 是为排序侧 GLM-4.7-Flash 免费额度定的（实测可达 21.5s），
# 但解析层调用小得多——实测 mean 0.72~1.18s / p95 1.0~5.6s。沿用 45s 会让最坏单轮达
# 2×45=90s，而官方保留"超时记 miss"的权利（docs/submission_rules.md:100-101 的 timeout 限制）。
# 取 12s：覆盖 p95 两倍余量，最坏单轮压到 2×12=24s；超时后重试一次，两次都失败即熔断退回规则路径
#（代价仅为该条消息走较弱的规则解析，远小于一次会话级 miss）。
LLM_PARSE_TIMEOUT = float(os.environ.get("LLM_PARSE_TIMEOUT", "12"))
LLM_RERANK_POOL = int(os.environ.get("LLM_RERANK_POOL", "20"))  # 送 LLM 精排的候选数
# M3：LLM 精排的 prompt 形态（C-T9 对照实验）。
#   basic    = 只喂标题+价格、上下文用 state.distilled（实验 4b/4c 的原版，已知负收益）
#   evidence = 喂完整约束清单 + 逐候选的"命中了哪几条约束"证据
# 目的：分离实验 4b 负收益的两个未分离原因——① LLM 看不到命中证据 ② 上下文太差。
# 默认 evidence 而非 basic：basic 实测是**负收益**（-0.020），evidence 才是持平。
# 万一有人开了 USE_LLM，不该让他拿到已知有害的那一版。
LLM_PROMPT = os.environ.get("LLM_PROMPT", "evidence")

# M3：热度先验权重（0 = 关闭）。依据：目标取自真实购买记录，真实购买集中在热门商品。
# 停止准则（实验 10c）：取"三个难度桶齐涨"的最大值。w=2.0 时 easy/medium/hard 全涨；
# w=3.0 时 easy 继续涨但 medium 掉（.825→.812）= 开始学公开集采样特征，故止步 2.0。
# 08-31 重扫（实验 43 仲裁）：撤销藏牌后满 10 件全部计入 MRR，最优点从 2.0 漂到 2.75。
# ⚠️ 09-01 邻域复核（C，T-028；A 独立复算逐位一致）：**这个峰只有一格宽，不要当成停止准则的产物**。
#   2.7=0.945267 / [2.75=0.946642] / 2.8=0.945717 / 3.0=0.944379 —— 对 2.8 只赢 +0.00092，
#   正好等于我们自己"一条会话 = 噪声"的阈值；压力档 L1-L3 均值 3.0 反而略优（+0.0002）。
#   结论：2.5-3.0 是同一个系统（跨度 0.0035），保留 2.75 是因为交付物已全线对齐该口径，不是因为它更优。
# HAS_PRICE=0.95 不同，这个可以主张：对 1.0 高 0.0025（0.946642 vs 0.944158），在阈值之上。
#   （原注释里"medium 因单条会话回退 -0.00038"作废——0.00038 本身就在噪声带内，拿它当判据是反向使用规则。）
POP_WEIGHT = float(os.environ.get("POP_WEIGHT", "2.75"))

# M3：has_price 先验权重（0 = 关闭）。依据：目标商品 89.0% 有 price 字段，全目录仅 20.8%。
# 与热度独立——低热度子集里全目录 has_price 20.2% 而目标 86.3%（差 66 个百分点）。
HAS_PRICE_WEIGHT = float(os.environ.get("HAS_PRICE_WEIGHT", "0.95"))

# M3：features 条数先验（实验 10b 已证伪：0.5 → 0.9176、1.0 → 0.9127，均低于不加）。保留开关供复现。
FEATURE_COUNT_WEIGHT = float(os.environ.get("FEATURE_COUNT_WEIGHT", "0"))

# M3：低置信轮的推荐条数上限（0 = 关闭，始终给满 10 条）。
# 依据：命中即终局，第 1 轮以第 7 名命中会把烂名次锁死（MRR 记 1/7）；
# 若第 1 轮少给几条、第 2 轮拿到约束后以第 1 名命中，单条会话净赚 0.237 分。
# 08-31 决定从默认档【移除】(实验 37)：机制真实且可观（TOPK=1 相对 0 值 +0.0286），
# 但"每轮只推 1 件"是反用户的展示行为，与 Impact/Feasibility 评审维度冲突。
# 撤销实测：五档 HitRate 逐档完全不变、MTTC 反而更快（2.155→1.920），代价 100% 落在 MRR。
# 同一原理（命中即终局下，早早以烂名次命中比晚一轮以第 1 名命中更亏）在检索侧的等价物见实验 40。
EARLY_TOPK = int(os.environ.get("EARLY_TOPK", "0"))
# 应用 EARLY_TOPK 的轮次上限。停止准则（实验 11a）：TURNS=2 三桶齐涨且 miss 不变；
# TURNS=3 时 easy hit 掉 .988→.975、medium hit 掉 1.000→.989、miss 1→3 = 拐点。
EARLY_TURNS = int(os.environ.get("EARLY_TURNS", "3"))

# M3：收窄的触发条件。
#   hybrid（默认）= 槽位不足【且】未超轮次上限。兼顾自适应与安全出口。
#   turns  = 只看轮次；slots = 只看槽位数（⚠️ 私有集解析失败时会永远收窄，实测可崩到 0.9318）。
# 公开集上 hybrid / turns / slots(MIN_SLOTS=4) 三者同为 0.9620，选 hybrid 是为私有集鲁棒性。
EARLY_MODE = os.environ.get("EARLY_MODE", "hybrid")
EARLY_MIN_SLOTS = int(os.environ.get("EARLY_MIN_SLOTS", "4"))  # slots 模式：槽位少于此数就收窄

# M3：先验权重是否随证据增多而衰减（0 = 恒定权重）。
# 动机：第 1 轮（尤其 browsing）没有任何约束证据，排序只能靠先验；拿到约束后证据应当压过先验。
# 衰减式：effective_weight = W / (1 + PRIOR_DECAY * 命中的约束条数)
PRIOR_DECAY = float(os.environ.get("PRIOR_DECAY", "0"))
# M3：收窄轮（第 1-2 轮）的先验倍率。这几轮只推 1 件、且几乎没有约束证据，
# 排序几乎完全由先验决定——单独给它一个倍率，与后续轮解耦。
EARLY_PRIOR_BOOST = float(os.environ.get("EARLY_PRIOR_BOOST", "1.0"))

# M1：长约束的逗号分片变体开关（0 = 关闭 = 消融口径，只匹配整串）。
# 动机：改写会重组逗号分隔的规格串（"75% Polyester, 20% Rayon" → 反序），整串匹配失效，
# 但各成分仍逐字存在于商品全文里。已从 ranker 的独立加分通道迁入 constraint_terms
#（Slot.terms 接口，片段 ≥5 字符护栏；消费端 max-len 计权，权重数值本身不再使用）。
FRAGMENT_WEIGHT = float(os.environ.get("FRAGMENT_WEIGHT", "0.8"))

# M3：意图卡镜像一致性 bonus（0 = 关闭）。依据（实验 22）：评测器意图卡由候选自身
# 元数据确定性生成、77.6% 全局唯一——"槽位值命中候选自身的镜像卡条目"是比裸子串
# 更强的一致性证据。权重 ≥1.0 恒定收敛（真二元判别器，同 has_price 形态）。
MIRROR_BONUS = float(os.environ.get("MIRROR_BONUS", "1.0"))

# M2：逐约束短语召回路（0 = 关闭）。依据（实验 22）：OR-token 大池会把"全样板约束 +
# 超冷门"目标挤出 top-300（public_0020 唯一 miss 的死因）；≥3 token 槽位值的 FTS5
# 短语查询子池极小、目标必进池。追加候选的 BM25 名次分记 0（子池归一化，与之捆绑）。
PHRASE_RECALL = os.environ.get("PHRASE_RECALL", "1") == "1"
PHRASE_TOP_K = int(os.environ.get("PHRASE_TOP_K", "50"))

# budget 约束的价格窗口（±比例）
PRICE_WINDOW = float(os.environ.get("PRICE_WINDOW", "0.3"))

# M2 稠密路：USE_DENSE=1 且资产齐全才启用，任一条件不满足自动降级纯 BM25（spec §1-⑦）
USE_DENSE = os.environ.get("USE_DENSE", "0") == "1"
EMBED_MODEL = os.environ.get("EMBED_MODEL", "BAAI/bge-small-en-v1.5")
EMBEDDINGS_PATH = os.environ.get("EMBEDDINGS_PATH", "data/embeddings.npz")
DENSE_TOP_K = int(os.environ.get("DENSE_TOP_K", "100"))
# 实验 O10：查询编码后端。torch（默认，sentence-transformers）/ onnx（onnx-runtime，内存峰值低 ~660MB）
DENSE_BACKEND = os.environ.get("DENSE_BACKEND", "torch")
EMBED_ONNX_DIR = os.environ.get("EMBED_ONNX_DIR", "data/onnx_model")
RRF_K = int(os.environ.get("RRF_K", "60"))
