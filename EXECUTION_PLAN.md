# EXECUTION_PLAN.md

IEQ-Ops 的权威实施进度清单。`CLAUDE.md` 引用本文件作为分阶段任务来源。

**约定:** `[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成。每个 Phase 以其 **验收 gate** 作为推进门槛,不达标不进下一阶段。窗口是目标、可调;但 Phase 6 的 8 周和 ~09-12 的代码冻结点受论文证据保护,不能被开发拖延吃掉。

起算日:2026-05-25 · 提交:2026-12。

---

## 时间线倒推

两条成功标准是时间硬约束:"自主运行 ≥ 4 周" + "Week 8 vs Week 1 记忆固化改善"(后者需在线连跑 ≥ 8 周)。倒推出开发窗口(Phase 0–5)= 现在到 ~9 月中,约 14–15 周。

| Phase | 内容 | 目标窗口 | 性质 |
|---|---|---|---|
| 0 | 地基 + 风险归档 | 05-26 → 06-06 (~1.5w) | 开发 · ✅ 2026-05-25 关闭 |
| 1 | 首条垂直闭环(模拟器 + 单 domain 桩) | 06-08 → 06-21 (2w) | 开发 · ✅ 2026-05-26 关闭(超前) |
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
- [x] `docker-compose.yml`:Postgres + Qdrant + LangFuse 三服务 2026-05-25 实测起飞(Docker Engine 29.5.2,WSL2 原生)——postgres healthy / qdrant 1.18.1 "all shards ready" / langfuse :3000 HTTP 200
- [x] `TECH_STACK.md`:选型总表 + 关键决策 + 6GB 显存共存 spike(2026-05-25 已实测定稿,见下方显存 spike 项)
- [x] `README.md` 骨架
- [~] **A4.5 归档**:作者决定跳过(2026-05-25)——能力实验结论已固化为 `llm_routing.md` 的节点路由决策,不再单独落盘 `eval/capability_profile/`。原始实验在 `~/projects/rag/douluo`(a4*.py + runs/a4*.jsonl)可追溯。
- [x] **6GB 显存共存 spike**:`ops/scripts/vram_spike.py` 实测(2026-05-25)。结论:三方共驻不可行(Qwen 单独 5.6GB 已 CPU offload 2.1GB);retrieve 必须 GPU(CPU 3.76s 爆 <500ms 预算 7.5x,GPU fp16 98ms,推翻 douluo 的 CPU 策略);dev 期 GPU 只跑 retrieve(4.0GB),Phase 6 用 ollama keep_alive 分时。定稿写入 `TECH_STACK.md`
- [x] `core/state.py`:全局 Pydantic State — `MainIncidentState` + locked schema(`AnomalyRecord` #10 / `ExpectedOutcome` #13,`extra="forbid"`)
- [x] `core/checkpointer.py`:`setup_checkpointer()` 2026-05-25 实测连通 Postgres 建表成功(checkpoints / checkpoint_blobs / checkpoint_writes / checkpoint_migrations 4 表)。**跨重启恢复留 Phase 1 🔴 验证**(风险点 #1)
- [x] `core/router.py`:实现 `llm_routing.md` 的节点→模型映射 + fallback 链(V3 超时→Flash→Tier3 incident) — 11 节点 tier 映射 + override A/B 编码 + `RouterExhausted`;真实 API 调用待 Phase 1 集成验证

**验收:✅ 2026-05-25 全部达成,Phase 0 关闭** — `docker compose up` 起 3 服务(postgres/qdrant/langfuse 实测健康);`core/` 过 `mypy --strict`(6 文件无错);显存策略实测定稿;checkpointer 建表实测通过。A4.5 归档经作者决定移出验收(结论已固化进 `llm_routing.md`)。

---

## Phase 1 — 首条垂直闭环(模拟器驱动,单 domain 桩)

**目标:** `MainIncidentGraph` 在模拟器上端到端跑通一个 CO2 incident,状态持久化、15 分钟挂起能**跨重启**恢复。

- [x] `sensing/simulator/co2.py`:physics-based CO2 模型(质量平衡:occupancy 产气 + 通风换气);`reset_room`/`save_room`/`get_room` 房间状态持久化,供 resume 跨进程读回
- [x] `mcp-sensor-server`:FastMCP,直读模拟器(`read_sensors`)
- [x] `mcp-ticket-server`:FastMCP,incident CRUD on Postgres(`create/update_incident` + `init_schema`)
- [x] `MonitorAgent.scan`:schema 锁死 `{anomaly,sensor,value,rule_violated}`(硬约束 #10);LLM 失败走 `sensing/thresholds.py` 确定性兜底,监控环永不静默卡死。dev 期 LOCAL 节点 override → deepseek-v4-flash
- [x] 极简 `PlannerAgent`:单子任务(非完整 DAG);`_retrieve_similar` 为 planner 内 inline 占位(Phase 3 换真 episodic)。dev 期 V3 override → deepseek-v4-pro
- [x] `AirQualityExpert` 桩:返回带 `expected_outcome:{target_metric,target_value,target_time_min}` 的固定诊断(硬约束 #13);Phase 2 换 SpecialistSubgraph 薄包装
- [x] `autonomy_gate`:三级 Tier 评估,Tier3 走 `interrupt()` 持久化(硬约束 #2 结构落地)。airquality=Tier1,interrupt 分支结构在但本阶段不触发
- [x] `mcp-actuator-server`:FastMCP 假执行器(`set_ventilation`,dev-fake 只打日志不动真设备)
- [x] `VerifierAgent.check`:读 `expected_outcome` 做数值比对,met→closed / missed→failed;LLM 失败走确定性比对兜底。dev 期 LOCAL override → deepseek-v4-flash
- [x] `core/graph.py`:`monitor→planner→dispatch→airquality→critic→autonomy_gate→action→(interrupt_before=["verifier"] suspend)→verifier`。memory_retrieve 按 CLAUDE.md 实现为 planner 内 inline 占位(**非独立节点**);critic 为 pass-through 占位(Phase 2 做 claim 分类)
- [x] 🔴 **15 分钟 checkpoint suspend 跨重启恢复 — 2026-05-26 实测通过**:进程A `start` 挂起(checkpoint 写 Postgres,`next=('verifier',)`)→ 进程A退出 → 全新进程B `resume <thread_id>` 从 Postgres 读回续跑。incident `I-20260526-R1-AQ-103812`:CO2 1300→679.4 ppm,verdict=met(delta −220.6),closed。incident 态 + 模拟器房间态均从持久化恢复,无内存残留。全架构最大技术风险**已坐实**

**验收:✅ 2026-05-26 全部达成,Phase 1 关闭(早于目标窗口)** — 模拟器灌 CO2 超标 → 自动建单 → 计划 → 诊断 → Tier 判定 → 假执行 → 15min 后验证关单端到端跑通(`ops/scripts/run_incident.py auto`,Postgres `incidents` 5 条历史 + 本次跨进程一条为证);🔴 跨进程重启恢复实测通过(风险点 #1 关闭)。LangFuse 接入:每节点 `@observe` span + `langfuse.openai` LLM generation 嵌套(代码层接入,trace 上传 UI 未单独核验)。**遗留**:`memory_retrieve`/`critic` 为占位待 Phase 2-3 做实;真实硬件/InfluxDB 留 Phase 5。

---

## Phase 2 — Agentic RAG 做实 + Planner 完整 DAG

**目标:** `SpecialistSubgraph` 五节点真跑(四 domain 共享一个编译实例);Planner 出真正的 ReWOO DAG。

- [~] `rag/ingest.py`:chunk → BGE-M3 嵌入入 Qdrant — 管线 2026-05-27 实测通(mini-corpus 占位 `rag/sample_corpus.py`,12 chunks 入 `ieq_standards`)。**遗留**:contextual prefix(V4-Flash+KV cache,节点 #10)+ 真 PDF 读取待接(现 `embed_text`=text)
- [x] `rag/retrieve.py`:BM25 + BGE-M3 双路召回 + bge-reranker-v2-m3 精排 — 2026-05-27 实测 GPU fp16 **51ms**(<500ms 预算),top1 命中正确条款,domain filter 生效。加载对齐 `vram_spike`(SentenceTransformer+safetensors / 手写 transformers reranker),非 douluo 的 CPU/CrossEncoder
- [x] `mcp-rag-server`:FastMCP 包 `retrieve.py`,**绝不含 LLM**(硬约束 #9) — lazy singleton,MCP 协议实测返回结构化 chunks
- [x] `agents/specialists/builder.py`:五节点 `decompose`(flash)/`retrieve`(无LLM,调 mcp-rag)/`grade`(flash 强制)/`rewrite`(LOCAL)/`generate`(flash 强制);domain 参数化;**module-load 时 compile 一次** — 2026-05-27 子图独立 + 接主图 `run_incident auto` 端到端实测跑通
- [x] 四个 wrapper `airquality/thermal/lighting/acoustic.py`:薄包装,共享 `run_specialist(payload,domain)`(接 dispatch fan-out 的 `Send` payload,非父 state);**四个全接为主图 fan-out 诊断节点**(2026-05-28 DAG 化)——诊断都跑,但只 airquality 有 actuator/action,其余三个的执行分支仍 Phase 5
- [x] 🔴 **subgraph 状态隔离**:`SpecialistState` 独立 schema,只 `subtask` 进、`final_diagnosis` 出 — 2026-05-27 实证父 checkpoint 仅 11 个 `MainIncidentState` 字段,`retrieved_chunks`/`grade_reason`/`rewrite_count` 零泄漏(风险点#2 关闭)
- [x] `generate` 输出强制 `expected_outcome:{target_metric,target_value,target_time_min}`,Pydantic `extra=forbid` 卡(硬约束 #13) — subtask_id 代码注入不信 LLM。**generate prompt bump v2(2026-05-28)**:CriticAgent 上线后实测暴露 generate 系统性产出"正文阈值(如 below 800ppm)≠ `target_value`(900ppm)"——Verifier 拿 `target_value` 核验,二者必须一致。v2 加规则 4 强制正文阈值 = `target_value`;改后 critic approve→关单 3/3(v1 时 ~1/3)。builder 指向 `generate/v2`
- [x] `CriticAgent.validate`(`agents/critic.py`,2026-05-28):**作者拍板方案 B** —— 状态隔离让 critic 在父图看不到子图 `retrieved_chunks`,放弃对照原文 trace-back(方案 A 需 `SpecialistResult.citations` 跨界,未采纳)。critic 只验两件能看到的事:① 确定性 plausibility 数值底线(target_metric 已知 / target_value 在物理范围 / target_time_min∈[1,240],无 LLM);② LLM 判 diagnosis 内部一致性 + expected_outcome 是否从诊断推得出(`critic.validate` 节点,LOCAL→flash)。LLM 失败走确定性兜底(底线过则批准,不死锁)。校验 **primary_result**;disapprove→写 ticket FAILED + 条件边路由 END **不执行**(不对不可信诊断动执行器)。disapprove→**replan** 留 Phase 3(需配 subtask_results 重置)。`core/graph.py` critic 后改条件边 `approved→autonomy_gate / 否→END`
- [x] `PlannerAgent` 升级:完整 Plan-and-Execute + ReWOO DAG(prompt v2,REASONING tier,temperature=0 保持 thinking)— 2026-05-28 实测出真 DAG(CO2 incident → S1 airquality + S2 thermal `depends_on=[S1]`)。主图改**波次拓扑** `planner→hydrate_placeholders→dispatch⇄{4 specialist}→critic`:`route_dispatch` 条件边按 ready 波次 `Send(domain,{subtask})` fan-out(无依赖并行,实测 LangGraph 1.2.1 Send+Pydantic state OK),specialist 回边 `hydrate_placeholders` 跑下一波;`#{id}.{field}` 占位符由 `hydrate_placeholders` 节点解析(实测 S2 的 `#S1.diagnosis` 填进 S1 真实诊断)。新增 `subtask_results` merge reducer + `failed_subtasks` add reducer(并行 fan-out 并发写安全)。`primary_result()` 按 anomaly domain 挑主子任务,驱动 autonomy_gate/action/verifier(实测 action 用 co2 而非 S2 的 operative_temperature)。四 specialist 全接为 fan-out **诊断**节点(actuator/action 仍 Phase 5,只 airquality 执行)。rewrite ≤3 沿用子图。mypy --strict clean
- [ ] **demo 场景库 + 展示 runner**(现场展示 / 边做边学用):把 `simulator/co2.py::reset_room()` 的单一硬编码异常泛化成 `sensing/simulator/scenarios.py` 命名场景注册表(每场景 = 一组房间初始参数 + 预期触发的 domain);模拟器从单 CO2 扩到覆盖四 domain 的可注入读数(这本就是四 specialist 能跑通的前提,不是额外工作)。`ops/scripts/demo.py` 是 `run_incident.py` 的**展示导向包装**——共用 `build_main_graph`,绝不另起平行系统;用 `graph.stream(stream_mode="updates")` 逐节点打印「现在到哪个 agent → state 出现哪些字段变更 → 该节点 LLM 输出」,首要目的是把闭环讲清楚(给作者自学、也给现场观众看)。本阶段只做**突发跳变**场景(值一次性冲过阈值);渐变劣化、复发模式(依赖 Phase 3 记忆)留后。

**验收:** 一个需多子任务 + RAG 的复杂 incident 跑通;grade 失败触发 rewrite;ReWOO 占位符正确 hydrate;父 checkpoint 不含 RAG 中间态;`demo.py` 能选一个突发跳变场景把闭环逐节点演示到关单。

**📍 进度(2026-05-27 session):** 检索地基 + Agentic RAG 子图整条打通并实测——retrieve 51ms / mcp-rag 无 LLM / 五节点 / 🔴状态隔离关闭 / rewrite 反思循环(构造缺失信息 query 触发 grade 判不够→rewrite×3→generate 诚实"原文未提及")。依赖经 `uv add` 进 `pyproject.toml`(torch cu121 + sentence-transformers + transformers + qdrant-client + rank-bm25 + langchain-text-splitters)。
**本次额外修复(已落代码)**:① builder 四节点 `extra_body={"thinking":{"type":"disabled"}}` —— v4 reasoning 偶发空 `content` 会让 generate 无端失败;② grade/decompose `temperature=0`、generate 0.2、rewrite 0.3 —— 否则 self-reflective 判断随机、rewrite 循环不可复现。修完延迟 ~11s→~3s/轮、判断可复现。
**📍 进度(2026-05-28 session):** Planner 完整 ReWOO DAG + 波次 fan-out 拓扑落地并端到端实测关单(详见上方 `[x]` Planner 行)。验收四点已坐实:多子任务+RAG✓ / grade 失败触发 rewrite(S2 rewrite×3)✓ / ReWOO 占位符正确 hydrate✓ / 父 checkpoint 仅 11 个 `MainIncidentState` 字段、RAG 中间态零泄漏✓。Phase 2 RAG 检索栈成果(上一 session)已 commit(179507c)。
**📍 进度(2026-05-28 session 续):** CriticAgent 方案 B 落地并端到端实测(详见上方 `[x]` Critic 行)。Phase 2 验收功能点只剩 demo runner。
**未完成,下次接(优先级序)**:1) **demo 场景库 + 展示 runner**(line 80,验收里 `demo.py` 那条 —— Phase 2 最后一个验收点);2) ingest contextual prefix(接 router #10,等真 PDF 才显效);3) grade prompt 可能偏严,真 corpus 后调。
**未提交**:本 session DAG 改动 + CriticAgent(core/state.py · core/graph.py · agents/planner.py · agents/critic.py · planner v2 prompt · critic v1 prompt · specialist generate v2 prompt · agents/specialists/builder.py 指向 generate/v2 · agents/specialists/ · ops/scripts/run_incident.py · ops/llm_routing.md · core/router.py · CLAUDE.md critic 句 · pyproject mypy override · plan)尚未 commit。

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
- 每落地一个 domain specialist,在 `sensing/simulator/scenarios.py` 注册一个对应的**突发跳变** demo 场景并验证 `ops/scripts/demo.py` 能端到端关单——现场展示靠注入场景而非真实传感器造异常(传感器现场无法试验出 CO2 飙升 / 温度异常)

## 两个必须早验证的架构风险点

1. **Phase 1:** 15 分钟 checkpoint suspend 跨重启恢复(Postgres 持久化)
2. **Phase 2:** SpecialistSubgraph 状态隔离(bulky 中间态不进父 checkpoint)
