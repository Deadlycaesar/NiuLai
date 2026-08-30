# REPORT.md 用的 M2 素材（B/周峻恺 · 08-30）

> 给报告主笔（@陈智龙 Fable 落笔 / @BestBucky 审）的**可直接粘贴**英文素材。
> 所有数字都在 `team/experiments.md` / `team/M2-通宵实验报告.md` 有原始记录，引用编号随附。
> 按 T-004 两种结局各备了一版措辞——**拍板前请用"维持取 0"版**。

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
> reaches retrieval — the fix there is Layer 3 (LLM extraction), not embeddings.

（这就是 T-020 里 @陈智龙 点名要的实验，阈值是"0.005 量级就值得重开 T-004"——实测是 2-4 倍。）

## 素材 C：§8 Limitations 的诚实句（按 T-004 结局二选一）

**若维持取 0（当前状态）：**

> The dense route ships disabled. Its public-set gain (+0.0016) is below our noise floor, and its
> memory cost (787 MB peak with the ONNX backend) buys robustness against a failure mode the
> public set cannot exhibit. We judged the trade not worth a new runtime dependency in the
> submitted default; both backends remain one environment flag away.

**若重开取 1 + onnx：**

> The dense route is enabled via an ONNX Runtime backend (32 MB quantised bge-small-en-v1.5),
> chosen over PyTorch specifically to keep peak memory at 787 MB instead of 1,191 MB — the
> submission rules reserve memory limits without naming them, so we engineered for the
> conservative case. Its value is not the public-set score (+0.0016) but the paraphrase-stress
> gains (+0.011 to +0.020, §4).

## 素材 D：数字速查（全部复核过，可直接引用）

| 数字 | 出处 |
|---|---|
| Recall@pool 1.000（目标永远在候选池） | 实验 6b / #22 |
| 打平局里目标 dense_sim 名次中位 81；排对时中位 3 | 实验 7（幕 3 的 "81 vs 3"） |
| dense-on 公开集 0.9694 → 0.9710（+0.0016，5↑0↓ 全是 MTTC 提前） | 实验 #28 |
| 断网全链路逐位一致（0.9694 / 0.9710） | 实验 #29 |
| RSS：纯 BM25 530MB / torch 1191MB / onnx 787MB | T-014 楼内 + 实验报告 O10 |
| 压力档 dense 增益 +0.011 / +0.020 / +0.016 / +0.000（L1-L4） | T-020 回帖 |
| onnx 向量 parity：余弦 1.0000（fp32）/ 0.982（int8），分数逐位一致 | O10 |
| 资产：npz 72MB（SHA256 e1268017…cbf06be）/ onnx int8 32MB | M2 交接文档 v2 |

## 引用口径提醒（别写歪的三处）

1. 实验 7 证伪的是"**当前查询配方下** dense_sim 解打平局"，不是"稠密无用"——O1 证明查询配方
   改了也没用，但报告措辞请留"在当前机制下"的限定。
2. dense 的收益表述请始终带两个口径：**公开集 +0.0016（低于噪声阈）/ 改写档 +0.011~0.020**。
   只写前者显得可有可无，只写后者是夸大。
3. "召回保险"指的是**私有集商品换血时**的冗余召回路径，公开集上它救回的 public_0020 是
   短语召回路的功劳（实验 22，A 落的），别记在 dense 头上。
