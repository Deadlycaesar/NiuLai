# NiuLai — TechJam 2026 Track 4 对话式购物 Agent

> 本文件是给所有 AI 编码助手（Claude Code / Cursor / Codex 等）的全局约定。
> 无论你在帮谁写代码，先读这里，再读 `team/briefs/` 里你负责的那份模块说明。

## 项目一句话

在官方评测器上构建多轮对话购物 Agent：≤10 轮内把用户真正购买的商品推进 top-10。
目标：TechnicalScore 从 baseline **0.107** 提到 **0.40+**（公式 = 0.50×HitRate@10 + 0.30×MRR + 0.20×Efficiency）。

## 常用命令

```bash
python3 scripts/prepare_catalog.py        # 首次：校验 SHA256 并解压 catalog（一次即可）
python3 -m evaluator.local_evaluator      # 全量评测 200 sessions，无 LLM 时约 33 秒
```

评测结果在 `results.json`：看 `recommended_technical_score` 和 `scenario_metrics`（分场景分数）。
**提 PR 前必须跑全量评测，把分数（总分+四场景）写进 PR 描述。**

## 接口冻结

模块间接口定义在 `team/SPEC.md` §5（`DialogState` / `retrieve()` / `rank()` / `clarify()`）。
**AI 助手不得"顺手"修改这些签名。** 需要改接口 = 先在群里提出 + 全组同意 + 改 SPEC，然后才动代码。

## 目录归属（只改自己的目录）

| 目录 | 负责人 | 内容 |
|---|---|---|
| `starter/agent.py` | A | **只是转发壳**（import `src/` 的实现），评测器硬编码此路径 |
| `src/dialog/` | A | 状态机、意图路由、提问策略 |
| `src/retrieval/` | B | 多路检索（FTS5 + 向量 + 融合） |
| `src/ranking/` | C | 重排、LLM 精排、澄清话术、离线降级打分 |
| `src/memory/` | D | 上下文蒸馏、profile 注入 |
| `scripts/` `tests/` | E | 评测流水线、消融、CI |
| `team/` | 全组 | 文档 |

跨目录改动必须先和目录负责人打招呼。

## 红线（AI 助手绝对不能做的事）

1. **不改 `evaluator/` 任何文件**——本地改了 = 分数作弊无效，提交了 = 违规。
2. **不改 `data/public_set.jsonl`**，不硬编码公开集答案（私有集 800 条完全不同，硬编码 = 自杀）。
3. **不提交任何 API key**。key 只放 `.env`（已 gitignore）；代码用 `os.environ` 读。
4. `starter/agent.py` 保持转发壳形态，不在里面写业务逻辑。
5. **每个 LLM 调用必须有离线降级路径**（官方最终评测可能断网）：断网跑 `python3 -m evaluator.local_evaluator` 必须照常出分。
6. Agent 的 `respond()` 永远不允许抛异常——顶层兜底返回上一轮最优推荐。

## 评测器关键事实（写代码前必知）

- `respond()` 返回 `{message, ask_attribute, recommendations, usage?}`；只有**前 10 个合法去重 parent_asin** 被打分，score 字段被忽略，**排序就是一切**。
- `ask_attribute` 枚举：category / material / color / size / style / brand / budget / feature / use_case / other / null。提问时**永远不要传 null**（用户只会回一句废话）。
- 每轮**可以同时提问 + 给推荐**，推荐零成本，命中即结束 → 每轮都带当前最优 top-10。
- 四场景：Buying 40%（首条含硬约束，第 1 轮可命中）/ Browsing 40%（模糊开局，baseline 在此几乎 0 分，最大提分空间）/ Intent Override 15%（第 3-4 轮改需求，此前命中无效）/ Boundary 5%（第一问被挡）。
- 问中匹配属性 → 用户原文吐出最多 2 条约束；`"other"` 匹配任意剩余约束。
- 模拟器回复格式固定，见 `evaluator/local_evaluator.py` 的 `customer_reply()`——解析器可以精确对着写。

## 文档地图

`team/problem-statement.md` 题目 · `team/SPEC.md` 技术方案（§2 评测机制必读）· `team/分工计划.md` 分工 · `team/调研报告.md` 选型依据 · `team/QUICKSTART.md` 五分钟上手 · `team/briefs/` 各模块开发说明书
