# Track 4 — Shopping Copilot: AI Conversational Search and Recommendations

> 精简自《[Early Bird Access] TikTok TechJam 2026 Tracks & Problem Statements》，只保留 Track 4 相关内容。
> 官方 Webinar 回放：[#4 Shopping Copilot 录像](https://bytedance.larkoffice.com/wiki/JlBHwciINiC3RCkfJ6xcuCGZnzb)

## 一句话任务

基于官方提供的 Amazon 商品数据集，构建一个**多轮对话式购物 Agent**：理解用户意图（买 vs 逛）、多路检索 + LLM 排序、在尽量少的对话轮数内把用户真正购买的那件商品推到推荐列表顶部。**纯后端评测，不做 UI。**

## 四大核心支柱（系统必须体现）

### I. 核心架构：意图路由 + 混合检索管线
- **双轨路由（Dual-Track Routing）**：实时判断用户意图——高意图的 **Buying** 走高精度过滤轨道（锁定硬约束，如尺码/价格/品类）；开放式的 **Browsing** 走多样化稠密检索轨道（跨品类场景匹配）。
- **管线基座**：内存内数据流，**多路检索（关键词 + 类目 + 向量相似度）→ LLM 语义排序**。

### II. 对话策略：多轮场景演化
- **动态状态机（Dynamic State Machine）**：对话状态跟踪器，处理**信息累积**（增量填槽）和**意图突变**（槽位擦除与重写）。
- **主动引导（Proactive Guidance）**：当候选池过载（用户需求过于宽泛）时立即截断检索，主动生成结构化澄清问题，引导用户收敛。

### III. 自我进化：动态上下文编程
- **运行时自适应**：利用对话历史做**个性化上下文蒸馏**，持续更新短期会话状态与长期用户画像。
- **自适应编排**：通过动态 Context Programming 在运行时重编排工作流、对齐策略，让 Agent 迭代优化自己的引导逻辑。

### IV. 评测指标（以数据集中最终购买记录为 ground truth）
| 指标 | 含义 |
|---|---|
| **Coverage — Hit Rate@K** | 检索阶段能否召回目标商品 |
| **Precision — MRR / Top-K Hit Rate** | LLM 排序能否把购买商品推到列表最顶部 |
| **Efficiency — MTTC**（Mean Turns to Conversion） | 越少轮数引导到正确商品越好，重奖高效、惩罚无效对话 |

## 约束与范围

**In scope（要做的）**
- 高敏感度意图检测，把流量切分为 Buying / Browsing 两轨
- 异构检索路由（权重、动态截断、槽位随时间衰减）
- 运行时自适应记忆层（个性化上下文蒸馏）
- 面向 LLM 排序阶段的 prompt 策略 / 本地打分逻辑调优，压缩决策路径

**Out of scope（不要做的）**
- ❌ UI/UX（纯后端 API + headless pipeline 评测）
- ❌ 训练或全参微调基座 LLM
- ❌ 外部重型向量数据库集群（必须**全内存**运行）
- ❌ 多模态（仅限文本目录、结构化元数据、文本对话）

**硬性限制**
- ⚠️ **每个 session 最多 10 轮**，超轮强制终止且**零分**
- ⚠️ 商品目录只读，禁止结构改动或注入 mock ASIN

**可以假设**
- 输入是预清洗文本（不用管拼写错误/ASR 噪声）
- 目录、价格、类目树在赛期内静态
- 单用户隔离会话，无需考虑并发

## 官方提供的资源

**数据**
- 冻结目录：Amazon Reviews 2023 `Clothing_Shoes_and_Jewelry` 类目的 **50,000 个商品**
- **200 条带标注的公开开发 session**（本地测试迭代用）
- 800 条私有 session 用于最终评测（与公开集用户、目标商品均不重叠）
- 目录与评测 session 均由官方冻结打包，**无需下载或重建上游完整 Amazon Reviews 2023 数据集**

**代码与工具**
- 一个弱 **BM25 baseline Agent**（Python）
- 确定性本地评测器：Hit Rate@10、MRR、MTTC、Efficiency、综合 **TechnicalScore**
- 公开的 Python Agent 接口 + 机器可读 API contract
- 评测配置、可复现 baseline 结果、数据文档、提交规则、目录 SHA256 校验
- kit 明确支持的技术路线：关键词检索、规则方法、稠密检索、混合检索、重排序、本地模型、外部模型 API

**链接**
- 参赛仓库：https://github.com/TechJam2026/techjam-conversational-search
- Participant Kit Release：https://github.com/TechJam2026/techjam-conversational-search/releases/tag/participant-kit
- 数据源文档：https://amazon-reviews-2023.github.io/

**注意**：官方不提供托管模型、API key、模型 token 或第三方 API 额度；付费 LLM 非必需。可以用外部模型 API，但 key 自理且**严禁提交进仓库**。可以魔改或替换 baseline Agent，但必须继续用官方评测器。

## 交付物（Devpost 提交）

1. **书面项目描述**：如何解决问题、开发工具、用到的 API、库/框架、数据集
2. **公开 GitHub 仓库**：结构清晰有注释的代码 + README（项目概述、安装步骤、结果复现步骤、局限性反思、**成员分工**——团队参赛必填）
3. **Demo 视频**：端到端演示，YouTube 公开链接，链接需写进 Devpost 描述（后端赛道可用 API 调用 / 推理示例 / 结果分析走查代替前端演示）；**不得包含未授权的第三方商标或版权内容**（当心背景音乐）

## 评分标准

| 维度 | 权重 | 要点 |
|---|---|---|
| Technical Execution | **35%** | 工程质量、架构、demo 稳定可复现 |
| Innovation & Problem Insight | **20%** | 思路原创性、对问题本质的把握 |
| Impact & Relevance | **20%** | 对真实用户/业务的价值 |
| Feasibility & Practicality | **15%** | 超越原型的可落地性、资源使用合理 |
| Presentation & Communication | **10%** | 决赛现场表达（讲清楚故事、答辩深度） |

---

*注：仓库附件夹中的 `kuairand-starter-kit.zip`、`*_transformer_benchmark*.py` 属于 Track 2/3 的资料，与本赛道无关。*
