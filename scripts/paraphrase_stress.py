"""改写压力测试：量化"私有集话术被改写"这个风险到底值多少分。

背景（这是全项目最大的未量化风险）：
官方 docs/competition_specification.md 原文——
    "The simulator policy decides what information to reveal.
     If natural-language paraphrasing is added by the organizer, it cannot decide correctness."
也就是说私有集的模拟用户**可能不再说本地评测器里那八句硬编码模板**。
而我方全链路建立在逐字匹配上：parser 用 `startswith` 认句式、ranker 用原文子串命中商品全文。
一旦改写，这两层同时失效——但公开集永远测不出来，因为公开集的模板是写死的。

做法（不改 evaluator 一个字节，红线 1）：
    import 官方的 evaluate()，传入一个**包装过的 Agent**。
    包装层在把 user_message 交给真 Agent 之前先做改写。
    评测器内部的意图卡、disclosed 集合、命中判定全部不受影响——
    这正好对应"组织方改写了模拟用户的输出文本，但底层策略不变"。

四个档位（逐层剥离我方依赖的信号）：
    L0  原样             —— 基准
    L1  句式改写         —— 模板措辞变了，约束原文逐字保留 → 只打击 parser 的句式匹配
    L2  L1 + 短约束改写  —— 短约束（"Pull On closure"）被换成自然说法，
                            长规格串（"75% Polyester, 20% Rayon…"）保留 → 再打击部分逐字命中
    L3  L1 + 全约束改写  —— 长规格串也被重组 → 逐字命中基本全失效

⚠️ 诚实声明：这些是**确定性的机械改写**，不是真的 LLM 改写。它的价值不在于精确预测
私有集分数，而在于**分层隔离故障点**——L1 掉多少 = 句式匹配值多少分；
L2/L3 额外掉多少 = 逐字命中值多少分。这两个数字才是排优先级的依据。

用法：
    python3 scripts/paraphrase_stress.py                 # 跑全部四档
    python3 scripts/paraphrase_stress.py --levels L0 L1  # 只跑指定档
    python3 scripts/paraphrase_stress.py --n 60          # 抽样加速
"""

from __future__ import annotations

import argparse
import json
import random
import re
import statistics
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from evaluator.local_evaluator import catalog_index, evaluate, load_jsonl  # noqa: E402
from starter.agent import Agent  # noqa: E402

# ---------------------------------------------------------------- 句式改写（L1+）
# 每条 = (识别原模板的正则, 改写模板)。约束原文用 \g<name> 原样搬运，逐字不动。
_PHRASING = [
    # 开场 · browsing
    (re.compile(r"^I'm looking for (?P<cat>.+), but I'm still exploring\.$"),
     "So I'm shopping around for {cat} at the moment — haven't settled on anything yet."),
    # 开场 · buying
    (re.compile(r"^I'm looking for (?P<cat>.+?)\. A key requirement is: (?P<c>.+)\.$"),
     "I'm after {cat}. The one thing I really need: {c}"),
    # 改需求 · 标准句
    (re.compile(r"^Actually, ignore my earlier preference\. What I need is: (?P<v>.+)\.$"),
     "Hold on — scratch what I said earlier. What I actually want is {v}"),
    # 改需求 · 兜底句
    (re.compile(r"^Actually, please ignore my earlier preference\.$"),
     "Hold on, forget what I told you before."),
    # 吐约束
    (re.compile(r"^For that, what matters is: (?P<body>.+)\.$"),
     "On that front, here's what counts for me: {body}"),
    # 问干了
    (re.compile(r"^I don't have an additional preference for (?P<a>\w+)\.$"),
     "Nothing else springs to mind on {a}, sorry."),
    # boundary 挡第一问
    (re.compile(r"^I don't have a preference for (?P<a>\w+); please use your judgment\.$"),
     "No strong feelings about {a} — I'll leave that one to you."),
    # null 惩罚句
    (re.compile(r"^Those options are not quite right yet\. Ask me about one specific attribute\.$"),
     "Hmm, none of those feel right. Could you ask me about one thing in particular?"),
    # 开场 · override（放最后：模式最宽，避免抢在前面几条之前匹配）
    (re.compile(r"^I'm looking for (?P<cat>.+?)\. (?P<rest>.+)$"),
     "I'm after {cat}. {rest}"),
]

# ---------------------------------------------------------------- L4：无冒号自然改写
# 与 L1 同为"约束原文逐字保留"，但去掉所有冒号、把载荷埋进句子中段——专打第二层防线
# （salvage）赖以生存的冒号载荷规则，隔离测量第三层防线（LLM_PARSE 逐字片段抽取）。
# 正则与 _PHRASING 逐条对应，只换模板。
_PHRASING_L4 = [
    (_PHRASING[0][0],
     "So I've been shopping around for {cat} lately, nothing set in stone yet."),
    (_PHRASING[1][0],
     "I'm after {cat} and honestly the dealbreaker for me is {c} more than anything else."),
    (_PHRASING[2][0],
     "Hold on — scratch what I said earlier, {v} is the thing that actually matters to me."),
    (_PHRASING[3][0],
     "Hold on, forget what I told you before."),
    (_PHRASING[4][0],
     "On that front I'd say {body} pretty much covers what counts for me."),
    (_PHRASING[5][0],
     "Nothing else springs to mind on {a}, sorry."),
    (_PHRASING[6][0],
     "No strong feelings about {a} — I'll leave that one to you."),
    (_PHRASING[7][0],
     "Hmm, none of those feel right. Could you ask me about one thing in particular?"),
    (_PHRASING[8][0],
     "I'm after {cat} and {rest}"),
]

# ---------------------------------------------------------------- 约束值改写（L2/L3）
_SPEC_RE = re.compile(r"\d")          # 含数字 = 规格串（成分表/尺寸），LLM 改写时通常原样保留
_SHORT_LIMIT = 25

_VALUE_REWRITES = [
    (re.compile(r"^(?P<x>.+) closure$", re.I), "it fastens with a {x}"),
    (re.compile(r"^Imported$", re.I), "it's an imported one"),
    (re.compile(r"^Machine Wash$", re.I), "I want to be able to machine wash it"),
    (re.compile(r"^(?P<x>cotton|polyester|nylon|leather|wool|silk|rayon|spandex|fabric)$", re.I),
     "something made of {x}"),
    (re.compile(r"^color:\s*(?P<x>\w+)$", re.I), "the colour should be {x}"),
    (re.compile(r"^budget around \$(?P<x>[\d.]+)$", re.I), "I'd like to stay around {x} dollars"),
]


def _rewrite_value(value: str, aggressive: bool) -> str:
    """把一条约束原文换成自然说法。逐字片段被破坏 = ranker 的指纹信号失效。"""
    for pattern, template in _VALUE_REWRITES:
        match = pattern.match(value.strip())
        if match:
            return template.format(**match.groupdict())
    if not aggressive:
        # L2：长规格串（含数字）保留原文，模拟 LLM 通常不动成分表的行为
        if len(value) > _SHORT_LIMIT or _SPEC_RE.search(value):
            return value
    # L3：规格串也重组——逗号分隔项打乱顺序并改连接词
    parts = [p.strip() for p in value.split(",") if p.strip()]
    if len(parts) > 1:
        return "with " + ", ".join(reversed(parts))
    return f"something like {value}"


def _rewrite_body(body: str, aggressive: bool) -> str:
    """吐约束句的载荷是 '; ' 拼接的多条约束。"""
    return ", and ".join(_rewrite_value(p, aggressive) for p in body.split("; "))


def paraphrase(message: str, level: str) -> str:
    if level == "L0":
        return message
    text = message.strip()
    for pattern, template in (_PHRASING_L4 if level == "L4" else _PHRASING):
        match = pattern.match(text)
        if not match:
            continue
        fields = dict(match.groupdict())
        if level in ("L2", "L3"):
            aggressive = level == "L3"
            if "body" in fields:
                fields["body"] = _rewrite_body(fields["body"], aggressive)
            for key in ("c", "v", "rest"):
                if key in fields and fields[key]:
                    fields[key] = _rewrite_value(fields[key].rstrip("."), aggressive)
        return template.format(**fields)
    return text  # 未识别的句式原样透传


class ParaphrasingAgent:
    """包装真 Agent：只改它看到的 user_message，其余全部透传。"""

    def __init__(self, inner, level: str) -> None:
        self.inner = inner
        self.level = level

    def reset(self, session_id: str, user_profile: dict) -> None:
        self.inner.reset(session_id, user_profile)

    def respond(self, session_id: str, user_message: str, turn: int, top_k: int) -> dict:
        return self.inner.respond(session_id, paraphrase(user_message, self.level), turn, top_k)


def stratified(rows: list[dict], n: int, seed: int) -> list[dict]:
    if n <= 0 or n >= len(rows):
        return rows
    buckets: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        buckets[row["scenario_type"]].append(row)
    picked: list[dict] = []
    for name, items in sorted(buckets.items()):
        take = max(1, round(n * len(items) / len(rows)))
        picked += random.Random(f"{seed}:{name}").sample(items, min(take, len(items)))
    picked.sort(key=lambda r: r["sample_id"])
    return picked[:n]


def main() -> None:
    parser = argparse.ArgumentParser(description="改写压力测试")
    parser.add_argument("--catalog", default="data/catalog.jsonl")
    parser.add_argument("--dataset", default="data/public_set.jsonl")
    parser.add_argument("--levels", nargs="+", default=["L0", "L1", "L2", "L3"])
    parser.add_argument("--n", type=int, default=0, help="抽样条数，0 = 全量 200")
    parser.add_argument("--seed", type=int, default=2026)
    parser.add_argument("--show", action="store_true", help="打印各档改写样例后退出")
    args = parser.parse_args()

    if args.show:
        examples = [
            "I'm looking for Tees & Blouses Tunics, but I'm still exploring.",
            "I'm looking for Accessories Belts. A key requirement is: leather.",
            "For that, what matters is: polyester; 75% Polyester, 20% Rayon, 5% Spandex.",
            "Actually, ignore my earlier preference. What I need is: 100% Leather.",
            "I don't have a preference for other; please use your judgment.",
        ]
        for text in examples:
            print(f"\n原句  {text}")
            for level in ("L1", "L2", "L3", "L4"):
                print(f"  {level}  {paraphrase(text, level)}")
        return

    samples = stratified(load_jsonl(args.dataset), args.n, args.seed)
    catalog_ids, categories, products = catalog_index(args.catalog)
    print(f"改写压力测试 · {len(samples)} 条会话 · evaluator 未做任何修改\n")

    base = None
    print("%-5s %10s %10s %8s %8s   %s" % ("档位", "Score", "HitRate", "MRR", "MTTC", "相对 L0"))
    print("-" * 74)
    for level in args.levels:
        agent = ParaphrasingAgent(Agent(args.catalog), level)
        result = evaluate(agent, samples, catalog_ids, categories, products)
        score = result["recommended_technical_score"]
        if base is None:
            base = score
        delta = "" if level == args.levels[0] else "%+.4f  (%.0f%%)" % (score - base, 100 * score / base)
        print("%-5s %10.4f %10.3f %8.3f %8.2f   %s" % (
            level, score, result["hit_rate_at_10"], result["mrr"], result["mttc"], delta))

    print("\n档位含义：L1 只改句式（约束原文逐字保留）／ L2 再改短约束 ／ L3 连长规格串也重组")
    print("        ／ L4 无冒号自然改写（约束逐字保留但载荷埋进句中——测 LLM_PARSE 第三层防线）")
    print("注：机械改写，非真 LLM 改写。价值在于分层隔离故障点，不在于精确预测私有集分数。")


if __name__ == "__main__":
    main()
