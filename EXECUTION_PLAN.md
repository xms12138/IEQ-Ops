# EXECUTION_PLAN.md

IEQ-Ops 的权威实施进度清单。`CLAUDE.md` 引用本文件作为分阶段任务来源。

**约定:** `[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成。每个 Phase 以其 **验收 gate** 作为推进门槛,不达标不进下一阶段。窗口是目标、可调;但 Phase 6 的 8 周和 ~09-12 的代码冻结点受论文证据保护,不能被开发拖延吃掉。

起算日:2026-05-25 · 提交:2026-12。

---

## 时间线倒推

两条成功标准是时间硬约束:"自主运行 ≥ 4 周" + "Week 8 vs Week 1 记忆固化改善"(后者需在线连跑 ≥ 8 周)。倒推出开发窗口(Phase 0–5)= 现在到 ~9 月中,约 14–15 周。

| Phase | 内容 | 目标窗口 | 性质 |
|---|---|---|---|
| 0 | 地基 + 风险归档 | 05-26 → 06-06 (~1.5w) | 开发 |
| 1 | 首条垂直闭环(模拟器 + 单 domain 桩) | 06-08 → 06-21 (2w) | 开发 |
| 2 | Agentic RAG 做实 + Planner 完整 DAG | 06-22 → 07-12 (3w) | 开发 |
| 3 | 三层记忆 + 周反思 | 07-13 → 07-31 (2.5w) | 开发 |
| 4 | IEQ-Bench 评测体系 + baseline | 08-03 → 08-21 (3w) | 开发 |
| 5 | 对话 + 前端 + 硬件落地 + 上线稳定化 | 08-24 → 09-11 (3w) | 开发 |
| **冻结** | **代码冻结 ~09-12** | | |
| 6 | 上线自主长跑 ≥8 周(Week1 vs Week8) | 09-14 → 11-08 | 运行 |
| 7 | 论文 + IEQ-Bench 开源 + repo 打磨 | 10 月中起,与 6 后段重叠 → 12-15 | 写作 |

---

## Phase 0 — 地基与风险归档

**目标:** 仓库能 `uv run`、三件套基础设施起飞、路由地基落盘。

- [x] 工程化:`pyproject.toml`(uv) · `ruff format`+`ruff check` · `mypy --strict` on `core/` · `structlog` JSON 日志(`core/logging.py`) · `pydantic-settings`(`core/config.py`) + `.env.example`
- [~] `docker-compose.yml`:Postgres + Qdrant + LangFuse 起飞 — 文件写好、YAML 合法(3 服务);**待装 Docker 后实测 `docker compose up`**(本机 WSL2 未装 Docker)
- [x] `TECH_STACK.md`:把散落在 CLAUDE.md/llm_routing.md 的选型抽出来定稿 — 选型总表 + 关键决策 + 6GB 显存共存 spike 待办小节(策略候选已记,实测待跑)
- [x] `README.md` 骨架
- [ ] **A4.5 归档**:把已完成的能力实验(题库 + 跑分 + 能力边界表)落盘到 `eval/capability_profile/`,让 `llm_routing.md` 的引用有实体、论文可直接引。**不重做。**
- [ ] **6GB 显存共存 spike**:确认 Qwen3-8B + BGE-M3 + bge-reranker-v2-m3 能否在 RTX 3060 6GB 同时常驻,定下加载策略(常驻/分时/CPU offload),写进 `TECH_STACK.md`
- [x] `core/state.py`:全局 Pydantic State — `MainIncidentState` + locked schema(`AnomalyRecord` #10 / `ExpectedOutcome` #13,`extra="forbid"`)
- [~] `core/checkpointer.py`:Postgres checkpoint — `open_checkpointer()` + `setup_checkpointer()` 封装 `PostgresSaver`;**待 Postgres 起后实测 setup + 跨重启恢复**(Phase 1 风险点 #1)
- [x] `core/router.py`:实现 `llm_routing.md` 的节点→模型映射 + fallback 链(V3 超时→Flash→Tier3 incident) — 11 节点 tier 映射 + override A/B 编码 + `RouterExhausted`;真实 API 调用待 Phase 1 集成验证

**验收:** `docker compose up` 起 3 服务;`core/` 过 `mypy --strict`;`eval/capability_profile/` 有 A4.5 实体;显存策略已定稿。

---

## Phase 1 — 首条垂直闭环(模拟器驱动,单 domain 桩)

**目标:** `MainIncidentGraph` 在模拟器上端到端跑通一个 CO2 incident,状态持久化、15 分钟挂起能**跨重启**恢复。

- [ ] `sensing/simulator/`:physics-based CO2 模型(先只喂 AirQuality 这一条线)
- [ ] `mcp-sensor-server`:FastMCP,先直读模拟器(暂不接 InfluxDB)
- [ ] `mcp-ticket-server`:FastMCP,incident CRUD on Postgres
- [ ] `MonitorAgent.scan`:本地 Qwen3-8B,schema 锁死 `{anomaly,sensor,value,rule_violated}`(硬约束 #10)→ 建 incident
- [ ] 极简 `PlannerAgent`:先出单子任务,**不做**完整 DAG(DeepSeek-V3)
- [ ] `AirQualityExpert` 桩:暂不做 5 节点 RAG,直接返回带 `expected_outcome` schema 的诊断
- [ ] `autonomy_gate`:三级 Tier 评估,Tier3 走 `interrupt()` 持久化。判定可先简单,**结构必须在**(硬约束 #2)
- [ ] `mcp-actuator-server`:FastMCP,假执行器(dev 模式打日志不动真设备)
- [ ] `VerifierAgent.check`:本地,读 `expected_outcome` schema 做数值比对
- [ ] `core/graph.py`:串 `monitor→memory_retrieve(占位)→planner→dispatch→airquality→critic(占位)→autonomy_gate→action→(15min suspend)→verifier`
- [ ] 🔴 **验证 15 分钟 checkpoint suspend 跨重启恢复**:杀进程再起,incident 从 suspend 点续上。全架构最大技术风险。

**验收:** 模拟器灌一个 CO2 超标 → 自动建单 → 计划 → 诊断 → Tier 判定 → 假执行 → 15 分钟后验证关单;LangFuse 看到完整 trace。

---

## Phase 2 — Agentic RAG 做实 + Planner 完整 DAG

**目标:** `SpecialistSubgraph` 五节点真跑(四 domain 共享一个编译实例);Planner 出真正的 ReWOO DAG。

- [ ] `rag/ingest.py`:ASHRAE/WELL/EN/WHO PDF → chunk → contextual prefix(V4-Flash + KV cache)→ BGE-M3 嵌入入 Qdrant
- [ ] `rag/retrieve.py`:BM25 + BGE-M3 双路召回 + bge-reranker-v2-m3 精排
- [ ] `mcp-rag-server`:FastMCP 包 `retrieve.py`,**绝不含 LLM**(硬约束 #9)
- [ ] `agents/specialists/builder.py`:五节点 `decompose`(V4-Flash)/`retrieve`(无LLM)/`grade`(V4-Flash 强制)/`rewrite`(本地,watched)/`generate`(V4-Flash 强制);domain 参数化;**module-load 时 compile 一次**(禁止 per-incident 重编译)
- [ ] 四个 wrapper `airquality/thermal/lighting/acoustic.py`:薄包装,只传 domain
- [ ] 🔴 **subgraph 状态隔离**:`SpecialistState` 独立 schema,只 `subtask` 进、`final_diagnosis` 出;`retrieved_chunks`/`grade_history`/`rewrite_count` 不进父 checkpoint。验证父 checkpoint 不含 RAG 中间态。
- [ ] `generate` 输出强制 `expected_outcome:{target_metric,target_value,target_time_min}`,Pydantic 卡(硬约束 #13)
- [ ] `CriticAgent.validate`:claim 分类(数值/直引→本地;归纳/多事实→V4-Flash 升级)
- [ ] `PlannerAgent` 升级:完整 Plan-and-Execute + ReWOO DAG;`#{subtask_id}.{field}` 占位符 + `hydrate_placeholders` 节点;无依赖子任务并行;rewrite 重试 ≤3

**验收:** 一个需多子任务 + RAG 的复杂 incident 跑通;grade 失败触发 rewrite;ReWOO 占位符正确 hydrate;父 checkpoint 不含 RAG 中间态。

---

## Phase 3 — 三层记忆 + 周反思

**目标:** 系统开始"变聪明",记忆闭环成立(Week8>Week1 的机制基础)。

- [ ] `memory/episodic.py`:Qdrant 存已结案 incident 轨迹 + `retrieve_similar()`——被 planner 节点 **inline 调用,不是 LangGraph 节点**
- [ ] `memory/semantic.py`(building facts JSON+向量) · `memory/procedural.py`(SOP 模板+触发条件)
- [ ] **memory 写入只走 `memory/` 模块函数 + 审计日志**,agent 不直接写(硬约束 #3)
- [ ] `ReflectionGraph`:每周日 03:00 cron,读 episodic 写 semantic+procedural;Reflector **V3 强制**(硬约束 #12);**按 incident type 分块**(四类各一次 + 汇总)防 OOM 128K 窗口
- [ ] procedural SOP 写 `pending_sops` 队列 → **人工签核才激活**(防幻觉 SOP 污染)
- [ ] 把 Phase 1 的 `memory_retrieve` 占位换成真 episodic 召回

**验收:** 结案 incident 落 episodic;手动触发一次 reflection 产出 semantic facts + pending SOP;新 incident 能召回相似旧案并影响 planner。

---

## Phase 4 — IEQ-Bench 评测体系 + baseline

**目标:** 无数字不立论(成功标准:≥75% 任务成功、领先 GPT-4o+ReAct ≥10pp)。

- [ ] `eval/ieq_bench/`:200 任务,覆盖各 agent / 各 domain / 各节点能力
- [ ] `eval/judge.py`:GPT-4o + Claude Sonnet 4.6 双裁判;prompt **强制** "only compare to expected, do not use prior knowledge"
- [ ] `eval/runner.py`:并行执行
- [ ] baseline:GPT-4o + ReAct,跑出对比基线
- [ ] 把"每次代码改动跑 IEQ-Bench"变成习惯(改 prompt/改节点模型必附 delta)
- [ ] 用这套验证 `llm_routing.md` 的 ablate 条件(generate hit-only<85% 升 V3、rewrite 命中<70% 升 Flash 等)

**验收:** IEQ-Bench v1 一键跑;系统得分 + baseline 得分出表;ablate 条件可量化触发。

---

## Phase 5 — 对话入口 + 前端 + 硬件落地 + 上线稳定化

**目标:** 补齐人机入口和真实硬件,进入可上线状态。

- [ ] `ConversationalGraph`:memory-first dispatch;V4-Flash 流式;自评信心<0.7 升 V3
- [ ] `frontend/`:极简运维面板(Next.js 或 HTMX)+ FastAPI 网关(看 incident、审批 Tier3)
- [ ] `sensing/hardware/`:RPi 传感器读取 + MQTT 发布
- [ ] `sensing/ingest/`:MQTT→InfluxDB;`mcp-sensor-server` 从直读模拟器切到 InfluxDB(真实/模拟可切换)
- [ ] `ops/deployment/`:systemd units + cron(5 分钟监控、周日反思)
- [ ] 稳定化:72 小时无人值守 dry-run,修崩溃/泄漏

**验收:** 真实传感器数据驱动一个真实 incident 端到端关单;面板能审批 Tier3;systemd 重启后自恢复。

---

## Phase 6 — 上线自主长跑 ≥8 周(论文头条证据)

**目标:** Week1 vs Week8 记忆固化证据 + ≥4 周纯自主 + Tier1 自动解决率 ≥80%。

- [ ] 部署到 UCL CASA 真实环境,autonomous run
- [ ] 每周 reflection 跑起来,episodic→semantic→procedural 持续固化
- [ ] **只做必要 bug 修复 + 阈值微调 + SOP 签核,不加新功能**
- [ ] 持续采集 LangFuse 在线 trace + 每周 IEQ-Bench 复跑

**验收:** 连续 ≥4 周无人 babysitting;Week8 在复发 pattern 上可测优于 Week1;Tier1 自动解决率达标。

---

## Phase 7 — 论文 + 开源(与 Phase 6 后段重叠)

- [ ] IEQ-Bench 数据集发 HuggingFace + 文档
- [ ] GitHub repo README + 复现说明打磨(≥100 star 目标)
- [ ] dissertation 写作:A4.5 能力画像证成路由 · Week1vsWeek8 证成记忆 · IEQ-Bench vs baseline 证成系统

**验收:** 论文 12 月提交;repo 可复现;HF 数据集公开。

---

## 贯穿全程的纪律

- prompts 全部版本化 `ops/prompts/{agent}/v{n}.md`,**绝不内联**(硬约束 #4);改 prompt = 复制 `v{n+1}` + 跑 IEQ-Bench 报 delta
- 节点级路由以 `llm_routing.md` 为准,`core/router.py` 实现;改任何节点模型要 bump 表行 + 跑 bench
- `autonomy_gate` 永不绕过,连 dev 都走 Tier 评估(硬约束 #2)
- 只用 LangGraph;禁用 LangChain `Chain`/`AgentExecutor`/`create_react_agent`(硬约束 #6/#7)
- `mcp-rag-server` 内**永不放 LLM**(硬约束 #9)
- 永不引用泄漏的 Claude Code 源码(硬约束 #8)
- `generate`/`grade`/Reflector **永不降级到本地**(硬约束 #11/#12)——A4.5 已证伪的失败模式

## 两个必须早验证的架构风险点

1. **Phase 1:** 15 分钟 checkpoint suspend 跨重启恢复(Postgres 持久化)
2. **Phase 2:** SpecialistSubgraph 状态隔离(bulky 中间态不进父 checkpoint)
