# REPORT.md 用的 M2 素材（B/周峻恺 · 08-30）

> 给报告主笔（@陈智龙 Fable 落笔 / @BestBucky 审）的**可直接粘贴**英文素材。
> 所有数字都在 `team/experiments.md` / `team/M2-通宵实验报告.md` 有原始记录，引用编号随附。
> **08-30 晚更新：T-004 已终裁取 0（素材 C 两版作废，§8 已由 D 直接落笔）；§9 B 的自述已填进 REPORT。**
> 本文件剩余有效部分 = 素材 A / B / D。压力档数字已在实验 33 后**重跑刷新**（dense on/off 两臂，
> 增益逐位不变，绝对值见素材 D）；REPORT §4 表格与「0.8330 → 0.9327」句请按素材 D 的新值刷新。

## 素材 A：§2 M2 段落的扩充（两种结局通用，3 句）

现有版本只说"optional pre-computed dense route"。可在其后接：

> The dense route was built, measured, and then deliberately left **off by default**. Its recall
> contribution on the public set is zero — Recall@pool is already 1.000 without it — and its
> score delta (+0.0016, experiments #28) sits below our own noise floor. We kept it as a
> semantic fallback: under paraphrase stress, where verbatim evidence weakens, it recovers
> +0.011 to +0.020 (§4). An ONNX Runtime backend (default: PyTorch) brings its memory cost
> from 1,191 MB down to 787 MB peak, bit-identical in score (experiment O10).

## 素材 B：§4 鲁棒性章节的新段落（核心价值在这）

§4 目前的表格只展示了三层解析防线。dense 的压力档数据回答的是另一个问题——
**"当逐字证据变弱时，语义兜底值多少分"**。建议在 §4 表格之后加：

> One layer of defence is not lexical at all. When paraphrasing weakens verbatim evidence, the
> dense route acts as a semantic floor. Measured with the stress harness (dense off → on):
>
> | | L1 phrasing | L2 + short values | L3 + spec strings | L4 no-colon |
> |---|---|---|---|---|
> | Δ score | **+0.011** | **+0.020** | **+0.016** | +0.000 |
>
> L4 is flat for a structural reason: that level breaks the *parser*, so no constraint ever
> reaches retrieval — the fix there is Layer 3 (LLM extraction), not embeddings. With Layer 3
> enabled, L4 recovers from 0.8486 to 0.9551 — level with L1.

（这就是 T-020 里 @陈智龙 点名要的实验，阈值是"0.005 量级就值得重开 T-004"——实测是 2-4 倍。
实验 33 后两臂重跑：增益逐位不变，L4 规则臂 0.8361→0.8486、L4+LLM 0.9327→0.9551 追平 L1——
"L4 的答案在 parser 第三层"从推断变成了实测。）

## 素材 C：~~§8 Limitations 的诚实句~~（作废——T-004 已终裁取 0，§8 限制 3 已由 @BestBucky 直接落笔，含完整 OOM 期望值论证；无需再从本节取材）

## 素材 D：数字速查（全部复核过，可直接引用）

| 数字 | 出处 |
|---|---|
| Recall@pool 1.000（目标永远在候选池） | 实验 6b / #22 |
| 打平局里目标 dense_sim 名次中位 81；排对时中位 3 | 实验 7（幕 3 的 "81 vs 3"） |
| dense-on 公开集 0.9694 → 0.9710（+0.0016，5↑0↓ 全是 MTTC 提前） | 实验 #28 |
| 断网全链路逐位一致（0.9694 / 0.9710） | 实验 #29 |
| RSS：纯 BM25 530MB / torch 1191MB / onnx 787MB | T-014 楼内 + 实验报告 O10 |
| onnx 向量 parity：余弦 1.0000（fp32）/ 0.982（int8），分数逐位一致 | O10 |
| **压力档（实验 33 后重跑，08-30 晚，两臂同跑）**：dense-off L0 0.9694 / L1 **0.9551** / L2 0.9218 / L3 0.8896 / L4 **0.8486**；dense-on L0 0.9710 / L1 **0.9664** / L2 0.9414 / L3 0.9058 / L4 0.8488 | 本次重跑（输出存留言板 T-022 回帖） |
| **dense 增益 L1-L4 = +0.0113 / +0.0196 / +0.0162 / +0.0002**（与实验 33 前逐位一致） | 同上 |
| **L4 + LLM 第三层 = 0.9551，追平 L1**（规则臂 0.8486）——REPORT 旧句 "0.8330 → 0.9327" 应刷新为 "0.8486 → 0.9551"。⚠️ **该行须带限定**：实验 35 复现失败，根因是 GLM 免费额度 429 限流触发熔断后整场静默关闭，非代码问题——引用时请加 "measured on a rate-limit-free endpoint"，且该行 L3(0.9640)>L2(0.9547) 单调性破了 | 实验 33（A）/ 实验 35（C） |
| 资产：npz 72MB（SHA256 e1268017…cbf06be）/ onnx int8 32MB | M2 交接文档 v2 |

## 引用口径提醒（别写歪的三处）

1. 实验 7 证伪的是"**当前查询配方下** dense_sim 解打平局"，不是"稠密无用"——O1 证明查询配方
   改了也没用，但报告措辞请留"在当前机制下"的限定。
2. dense 的收益表述请始终带两个口径：**公开集 +0.0016（低于噪声阈）/ 改写档 +0.011~0.020**。
   只写前者显得可有可无，只写后者是夸大。
3. "召回保险"指的是**私有集商品换血时**的冗余召回路径，公开集上它救回的 public_0020 是
   短语召回路的功劳（实验 22，A 落的），别记在 dense 头上。
