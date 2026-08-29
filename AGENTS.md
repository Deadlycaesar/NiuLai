# NiuLai — TechJam 2026 Track 4 对话式购物 Agent

> 本文件是给所有 AI 编码助手（Claude Code / Cursor / Codex 等）的全局约定。
> 无论你在帮谁写代码，先读这里，再读 `team/briefs/` 里你负责的那份模块说明。

## 项目一句话

在官方评测器上构建多轮对话购物 Agent：≤10 轮内把用户真正购买的商品推进 top-10。
目标：TechnicalScore（公式 = 0.50×HitRate@10 + 0.30×MRR + 0.20×Efficiency）。
**当前 main = 0.918**（baseline 0.107）。原定的 0.40+ 已远超，**提分阶段基本结束**：
公开集实际天花板约 0.99，剩余空间仅 ~0.07，且越榨越容易过拟合私有集。
新重心 = **鲁棒性（防私有集/改写翻车）+ 交付物（README / 报告 / demo 视频 / Devpost）**。

## 常用命令

```bash
python3 scripts/prepare_catalog.py        # 首次：校验 SHA256 并解压 catalog（一次即可）
python3 -m evaluator.local_evaluator      # 全量评测 200 sessions，无 LLM 时约 10 秒（M5/24G 实测 9.7s）
python3 scripts/check_guards.py            # 提交前护栏自检（红线 1-4 + 密钥扫描），10 秒
python3 scripts/eval_sample.py --n 40      # 分层抽样评测（LLM 路径太慢时用）
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
- **`message` 字段评测器根本不读**（源码第 243 行只做 `isinstance(..., str)` 类型检查）。你和模拟用户之间的
  唯一信道是 `ask_attribute` 这一个 10 选一的枚举值 ≈ 3.3 bit/轮——**没有任何"提问话术"能影响用户的回答**。
  推论：LLM 无法用于"引导用户"；`message` 的价值只在人评（Technical Execution 35% + Innovation 20%）与 demo 视频。
- **`classify_constraint()` 永远不会返回 `category` / `brand`** → 问这两个属性必然空手而归。公开集 800 条约束的
  实测分布：feature 404 / material 302 / color 60 / style 19 / size 11 / use_case 4 / **budget 0**。
- **budget 是死代码**：公开集 0/800、catalog 侧仅 0.53% 的商品会生成 budget 约束 → `state.budget` 恒为 None，
  `ranker.py` 的价格打分与 `retriever.py` 的 budget 过滤从未执行。不要在价格路上花时间。
- **排序轴 vs 先验轴（实验 8c，影响技术选型）**：语义相关性信号（BM25 / 稠密 / 交叉编码器）已被"约束逐字命中"
  这个指纹信号吃满，在打平局里无区分度（实验 7）。真正解决打平局的是**先验轴**——"哪件更可能是真人会买的"
  （rating_number 等）。**上任何语义重排器之前，先照实验 7 口径做 20 分钟可行性诊断。**

## 异步沟通：先看留言板

**开工前和收工前各读一次 [`team/留言板.md`](team/留言板.md)。**

群聊里的话 AI 助手读不到，commit message 是单向广播没法来回讨论——留言板补上中间那层：
**需要别人回应、但不值得开会的事都写那里。** 标 🟡 的是待回复。

- 有话要跟别的模块的人（或他们的 AI 助手）说 → 在留言板**末尾**追加一个帖子
- 别人 @ 了你 → 在对应帖子下面加一行回复，别改他的原话
- 只追加、不重排（`.gitattributes` 给它配了 `merge=union` 防并发冲突）
- **达成一致就归档**：把帖子从主区移走，在文末「已归档」表里留一行结论。
  主区永远只剩待办，一眼扫完；归档表是"我们如何做决定"的记录，会进最终报告。

`scripts/check_guards.py` 每次都会列出待回复的帖子并高亮"在等你"的那些，CI 也会打进
Actions 日志——**只要你推代码就会看到**，不需要谁记得去翻。

⚠️ 格式目前是 v0 草案（见 T-001），**欢迎直接改**。

## 文档地图

`team/problem-statement.md` 题目 · `team/SPEC.md` 技术方案（§2 评测机制必读）· `team/分工计划.md` 分工 · `team/调研报告.md` 选型依据 · `team/留言板.md` 异步讨论区 · `team/QUICKSTART.md` 五分钟上手 · `team/briefs/` 各模块开发说明书
