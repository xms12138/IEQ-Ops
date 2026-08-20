# FIGURE & TABLE MANIFEST — IEQ-Ops Dissertation

> **契约**：做实验/画图时，脚本必须把产物写到本清单指定的**精确文件名**；生成论文时，按本清单把图表插入对应 `section`。
> 图 → `Essay/documents/figures/fig-NN-slug.png`（代码生成的另存 `.svg`/源脚本）
> 表 → `Essay/documents/tables/tbl-NN-slug.csv`（数据）+ `tbl-NN-slug.md`（论文用渲染）
> 状态：`TODO`（未产出）｜`DONE`（已产出）｜`NEEDS-DATA`（等实验数据）
> 每产出一个，把该行 `status` 改成 `DONE`。

---

## 图（Figures）

| ID | 文件名 | 章节(Section) | Caption 草稿 | 数据来源 / 如何产出 | 依赖 | 状态 |
|---|---|---|---|---|---|---|
| F01 | fig-01-problem-sdc.png | 1 Intro / 2 LitReview | 问题链（不可见风险→认知负荷→幻觉→被动无记忆）与 Sense·Deploy·Communicate 框架 | 概念图，直接绘制 | — | **DONE** |
| F02 | fig-02-system-architecture.png | 3 Methodology | 3 独立 LangGraph + SpecialistSubgraph 架构总览 | 概念图，据 CLAUDE.md/graph.py | — | **DONE** |
| F03 | fig-03-deployment-photos.png | 3 Methodology (Sense) | 实体展台部署照:(a)正面(7"触摸屏kiosk通电+Grove声音传感器)、(b)背面(**3D打印棱面外壳**+六边形蜂窝散热孔+风扇导管)、(c)传感器面板(ANVISION 40mm风扇+SCD-30绿板) | 用户原图 `fig03-device-front/rear/sensor-enclosure.jpg` → `gen_photo_composites.py`(EXIF自动校正+下方换行注释) | 已有 | **DONE** |
| F04 | fig-04-sensing-pipeline.png | 3 Methodology (Sense) | MKR1010→MQTT→Mosquitto→Postgres 数据流 | 概念图 | — | **DONE** |
| F05 | fig-05-rag-pipeline.png | 3 Methodology | BM25+dense→reranker→contextual-prefix 检索流水线 | 概念图，据 rag/retrieve.py | — | **DONE** |
| F06 | fig-06-eval-protocol.png | 3 Methodology | 评估协议：条件×指标×双judge×确定性锚点 | 概念图 | — | **DONE** |
| F07 | fig-07-real-sensor-trace.png | 4 Results·Exp1 | 真实一整天读数(CO2/温湿/光/声,5通道小多图)，标注自然微事件(上午占用CO2 420→832+噪声同峰、日照弧西晒峰1579lux、温度热质量滞后峰26°C@15:15),全通道在带内 | `real-trace-2026-07-10-london.csv`(2026-07-10真实SCD-30+Grove) → `gen_exp1_sensing.py` | 已有 | **DONE** |
| F08 | fig-08-sim-vs-real.png | 4 Results·Exp1 | 部署仿真器(ambient history模式)偏移标定后 vs 真实,逐通道RMSE+r:温度r=0.81/光r=0.84抓昼夜包络,CO2 r=0.38诚实错过离散占用事件(反证热路径用显式注入场景) | `real-trace-2026-07-10-london.csv` + `sensing/ambient.py` → `gen_exp1_sensing.py` | 已有 | **DONE** |
| F09 | fig-09-closedbook-prescreen.png | 4 Results·Exp2 | 基座 closed-book 各题类准确率（示哪里裸答会错，正当化选题） n=37 | `closedbook-prescreen-20260818T074637Z.json` | 已有 | **DONE** |
| F10 | fig-10-h1-ablation.png | 4 Results·Exp2 | No-RAG vs RAG 准确率柱状图，+32pp，n=37 | `h1-rag-ablation-20260818T075118Z.json` | 已有 | **DONE** |
| F11 | fig-11-retrieval-metrics.png | 4 Results·Exp2 | recall@k / nDCG@k 五段流水线曲线（BM25/dense/hybrid/+reranker/+contextual） | `retrieval-pipeline-ablation-20260818T080651Z.json` | 已有 | **DONE** |
| F12 | fig-12-rag-pipeline-ablation.png | 4 Results·Exp2 | 各段对 recall@5 的贡献（reranker 从 hybrid 0.53→0.94 的关键跃升；+contextual 反而降到 0.75，诚实负面结果） | 同上 | 已有 | **DONE** |
| F13 | fig-13-recall-accuracy-lift.png | 4 Results·Exp3 | **Plan-level** recall-lift（OFF→ON），按 domain，n=12 | `ablate-memory-20260818T023543Z.json` | 已有 | **DONE**（仅 plan 层，见 F23 diagnosis 层） |
| F14 | fig-14-plan-sharpening-example.png | 4 Results·Exp3 | 一个真实例子：plan/goal 在 recall OFF vs ON 的对照（定性） | **REUSE**：evidence-inventory §2，`ablate-memory-*223417Z` 的 goals_off/on 原文（co2-damper, thermal-solar） | 已有 | REUSE-READY |
| F15 | fig-15-detection-coverage.png | 4 Results·Exp4 | 主动 vs 被动 检测覆盖率 + 查询预算敏感性 | 实验4 | 事件流 | **DONE** |
| F16 | fig-16-lead-time.png | 4 Results·Exp4 | 提前量分布 / 静默漏检事件数 | 实验4 | 事件流 | **DONE** |
| F17 | fig-17-raw-vs-nl.png | 4 Results·Communicate | 原始多传感器读数 vs 系统自然语言诊断/管家 + kiosk 截图:(a)常态(五通道全绿+一条CO2 incident已验证CLOSED met Δ−220.6)、(b)异常(CO2 1300红警+incident OPEN+Planning+管家答历史均温27.37°C查询)、(c)越界拒答("中国首都"→收敛回IEQ域) | 用户真机截图 `fig17-kiosk-normal/anomaly/butler-out-of-scope.jpg` → `gen_photo_composites.py`(3行竖排) | 已有 | **DONE** |
| F18 | fig-18-judge-agreement.png | 4 Results·judge效度 | inter-judge 一致性(κ=0.822) + judge-vs-确定性grader(κ=0.71-0.77)；judge-vs-human 标注为 future work | `judge-validity-20260818T075649Z.json` | 已有 | **DONE** |
| F19 | fig-19-edge-retrieval-breakdown.png | 4 Results·Deploy(边缘可行性) | Pi CPU 单次 retrieve 各段耗时(embed/dense/bm25/**rerank≈99%**) | **REUSE**：inventory §1，`ops/scripts/pi_retrieve_spike.py`/P-023 | 已有 | REUSE-READY |
| F20 | fig-20-edge-candidate-latency.png | 4 Results·Deploy(边缘可行性) | 候选池 30→5 的延迟(189s→24.4s, 线性)+退化边界 | **REUSE**：inventory §1/P-023 | 已有 | REUSE-READY |
| F21 | fig-21-closed-loop-replan.png | 3/4 闭环设计 | `co2_overcrowded` 轨迹：critic否决→replan→verifier missed×2→FAILED（单例，定性） | **REUSE**：inventory §6，DEVLOG P-024/P-027 | 已有 | REUSE-READY |
| F22 | fig-22-memory-macrolift.png | 4 Results·Exp3 | 记忆消融 macro_lift 迭代(0.25→0.75→1.0)（历史演进叙事） | **REUSE**：inventory §2，`ablate-memory-*.json` | 已有 | REUSE-READY |
| F23 | fig-23-diagnosis-level-lift.png | 4 Results·Exp3 | **T2.1** Diagnosis-level（非 plan-level）recall lift：OFF=0.00→ON=1.00(n=12) | `h2a-diagnosis-accuracy-20260818T083444Z.json` | 已有 | **DONE** |
| F24 | fig-24-memory-specificity.png | 4 Results·Exp3 | **T2.2** 4 个 novel 非复发异常的记忆污染率=1.00(4/4，诚实负面结果) | `h2a-specificity-20260818T084041Z.json` | 已有 | **DONE** |
| F25 | fig-25-closed-loop-success.png | 4 Results·Deploy/闭环 | **T3.1** 真实 MainIncidentGraph：airquality(唯一有执行器的域)全严重度区间8/8自动关单、overcrowded正确FAILED 3/3、Tier-3闸门(热/光/声,无执行器)9/9零自主动作 | `e2e-closed-loop-final-20260818T095745Z.json` | 已有 | **DONE** |
| F26 | fig-26-ieq-bench-aggregate.png | 4 Results·汇总 | **T3.2** IEQ-Bench 按 layer/capability 通过率；能力面(排除recurrence)86.7%(26/30) vs 含recurrence 90.5%(38/42)并列报告，recurrence柱标注为过程保真度指标 | `ieq-bench-aggregate-20260818T100915Z.json` | 已有 | **DONE** |

## 表（Tables）

| ID | 文件名(.csv/.md) | 章节 | 内容 | 数据来源 | 状态 |
|---|---|---|---|---|---|
| T01 | tbl-01-llm-routing | 3 Methodology | 各 LangGraph 节点的本地/云模型路由 | ops/llm_routing.md | **DONE** |
| T02 | tbl-02-ieq-bench-composition | 3 Methodology | IEQ-Bench 题量（按 level×domain），据实报 | eval/ieq_bench/tasks | **DONE** |
| T03 | tbl-03-sensor-validity | 4 Results·Exp1 | 各传感器量程 vs 预期 + 管道完整率100%(288/288) + sim-vs-real RMSE/r + **Grove ADC→物理单位标定披露** | `real-trace-2026-07-10-london.csv` → `gen_exp1_sensing.py` | **DONE** |
| T04 | tbl-04-h1-results | 4 Results·Exp2 | H1 全指标：n=37, closed-book 0.43→RAG 0.76(+32pp), McNemar p=0.0075, 3处regression定性分析 | `closedbook-prescreen-20260818T074637Z.json` + `h1-rag-ablation-20260818T075118Z.json` | **DONE** |
| T04b | tbl-04b-h1-multiseed | 4 Results·Exp2 | H1 多seed稳定性：majority-vote lift+32.5pp, McNemar p=0.0118，6/37题闭卷不稳定 | `h1-multiseed-20260818T091145Z.json` | **DONE** |
| T05 | tbl-05-h2a-results | 4 Results·Exp3 | **Plan-level** recall-lift、n=12（已明确降级为机制演示，非诊断准确率） | `ablate-memory-20260818T023543Z.json` | 已有 | **DONE** |
| T06 | tbl-06-autonomy-results | 4 Results·Exp4 | 覆盖率、提前量、静默漏检、敏感性（无LLM的调度模型） | 实验4 | **DONE** |
| T07 | tbl-07-judge-validity | 4 Results·judge效度 | inter-judge κ=0.822, judge-vs-确定性grader κ=0.71-0.77; judge-vs-human 标注 future work | `judge-validity-20260818T075649Z.json` | **DONE** |
| T08 | tbl-08-limitations | 5 Discussion | 局限与威胁表:13行按 internal/external/construct/statistical 分类,含 sim≠真楼、n小、in-sample标定、novel污染未修、三头条缺表、单corpus、contextual回退等,每行标"约束哪个claim+如何诚实处置" | 手写 | **DONE** |
| T09 | tbl-09-edge-feasibility | 4 Results·Deploy | 内存峰值(3.8–4.0GiB 零swap)、提速杠杆逐个证伪、退化边界 | **REUSE**：inventory §1/P-001/P-023 | REUSE-READY |
| T10 | tbl-10-corpus-corrections | 3/4 (H1 题库依据) | 真WELL v2 阈值修正 vs 广传误区：CO2 900/750(非1000)、thermal 21–25、light 320lux、acoustic 50dBA(1pt)/45(3pt)分档 | **REUSE**：inventory §7/P-019/P-013-016 | REUSE-READY |
| T11 | tbl-11-routing-validation | 3 Methodology | 节点级路由验证(grade/generate/rewrite/critic/planner 全达标) + 成本包络 | **REUSE**：inventory §3，`ablate-check-*.json`/`ops/llm_routing.md` | REUSE-READY |
| T12 | tbl-12-react-negative | 4 Results·架构消融 / 5 Discussion | **T3.3(reframe)** 架构消融:多智能体 vs 单agent ReAct(同模型同工具同critic)。thermal+40/lighting+60/co2 0；acoustic n=5噪声不下结论；命题降级为"输出可靠性"非"推理优越"，声明3个混淆项(无域执行器/6步预算/系统臂带recall)。附旧"+10pp不稳定"作次要教训 | `ieq-bench-aggregate-20260818T100915Z.json` (l3_e2e.rows) + `compare-*.json` | **DONE** |
| T13 | tbl-13-episodic-recall | 4 Results·Exp3 | **T2.3** 真实embedding检索recall@1=0.5/@3=1.00, MRR=0.722, 同域混淆6/12 | `episodic-recall-20260818T072850Z.json` | **DONE** |
| T14 | tbl-14-retrieval-pipeline | 4 Results·Exp2 | **T1.1/1.2** 5段流水线 recall@k/MRR/nDCG，reranker关键跃升 + contextual负面结果 | `retrieval-pipeline-ablation-20260818T080651Z.json` | **DONE** |
| T15 | tbl-15-h2a-diagnosis-accuracy | 4 Results·Exp3 | **T2.1** 端到端诊断准确率(非仅plan)：off=0.00→on=1.00(n=12)，含grader语义bug修复记录 | `h2a-diagnosis-accuracy-20260818T083444Z.json` | **DONE** |
| T16 | tbl-16-h2a-specificity | 4 Results·Exp3 | **T2.2** novel异常记忆污染率=1.00(4/4)：通用安全诊断被替换成借来的错误具体因 | `h2a-specificity-20260818T084041Z.json` | **DONE** |
| T17 | tbl-17-e2e-closed-loop | 4 Results·闭环 | **T3.1** 真实MainIncidentGraph：airquality 8/8自动关单(唯一有执行器的域)、overcrowded FAILED=1.00(3/3)、Tier-3闸门=1.00(9/9)，含3个方法论bug发现修复记录(阈值扫描值/工单去重/verifier_verdict提取)，"verified"结论已用Postgres直查交叉核验 | `e2e-closed-loop-final-20260818T095745Z.json` | **DONE** |
| T18 | tbl-18-ieq-bench-aggregate | 4 Results·汇总 | **T3.2** 能力面(排除recurrence)26/30=86.7%为首选数字；含recurrence 38/42=90.5%并列报告(recurrence是process-fidelity指标，见tbl-15/16)；L2 rewrite=0旧夹具bug如实标注 | `ieq-bench-aggregate-20260818T100915Z.json` | **DONE** |

---

## 产图规范（保证图表读起来是一套系统）
- 统一配色/字号/dpi（≥150dpi，矢量优先 svg）；柱状图误差棒必带；坐标轴范围/单位/图例齐全（评分细则明确点名「axis ranges」）。
- 每张图配一句 self-contained caption（能脱离正文读懂）。
- 画任何图前先读 dataviz skill 再动手。
- 表同时出 `.csv`（可复现原始数）与 `.md`（论文渲染）。
