# EXECUTION_PLAN.md

IEQ-Ops 的权威实施进度清单。`CLAUDE.md` 引用本文件作为分阶段任务来源。

**约定:** `[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成。每个 Phase 以其 **验收 gate** 作为推进门槛,不达标不进下一阶段。窗口是目标、可调;但 Phase 6 的 8 周和 ~09-12 的代码冻结点受论文证据保护,不能被开发拖延吃掉。

起算日:2026-05-25 · 提交:2026-12。

---

## 当前进度快照（截至 2026-06-06）

> 一眼全局视图(给作者自学 / 答辩 / 求职)。每个 session 收尾更新本节;细节见下方各 Phase。

**Phase 0–3 全部完成(早于目标窗口);Phase 4 进行中:**

| Phase | 核心成果(一句话) |
|---|---|
| 0 地基 ✅ | uv 工程化 + Docker 三件套(Postgres/Qdrant/LangFuse) + 节点级 `router` + 6GB 显存策略实测定稿 |
| 1 垂直闭环 ✅ | `MainIncidentGraph` 端到端跑通(monitor→…→verifier);🔴 15 分钟挂起**跨重启恢复**实测通过 |
| 2 Agentic RAG + DAG ✅ | 检索栈(BM25+BGE-M3+reranker,51ms) + `SpecialistSubgraph` 五节点 + 🔴**子图状态隔离**;Planner 完整 ReWOO DAG + 波次 fan-out;CriticAgent(方案 B) |
| 3 三层记忆 + 反思 ✅ | episodic/semantic/procedural 三层 + `ReflectionGraph` 按 type fan-out;周反思产 fact + pending SOP(人工签核);planner 召回 episodic 影响规划 |
| 4 评测 🔧 进行中 | IEQ-Bench 24 种子(六 capability 全绿)+ **generate/v4**(co2 自洽 0.70→1.00)+ **记忆消融 `--ablate-memory` +1.00**(planner/v4,Week8>Week1 离线铁证)+ e2e `--compare`(`arm_value` 公平)。**❗诚实结论:≥10pp-vs-ReAct 当前立不住**(强基座下简单任务两臂趋同、自相矛盾陷阱不咬 P-011,原 +10pp 系 n5 噪声);稳健 ≥10pp 留 Phase5 真 corpus 误导检索难题 + GPT-4o baseline;`DEVLOG` P-001..P-012 |

> **🆕 2026-06-06:** airquality **真 PDF corpus 接入**(WELL v2 Air)+ **contextual prefix**(节点 #10,**v4-flash**)+ PDF 去重(commit `84feee0`)。真 corpus 改变 airquality 知识形状:召回命中 WELL 真实阈值(CO2 500/750ppm above outdoor、PM2.5 MERV),取代占位 1000ppm——为 Phase 4「扩 200 判别性难题 / ≥10pp」提供原料。详见 Phase 4 进度 + DEVLOG P-013。
>
> **🆕 2026-06-06(续):** ① **真 corpus 切换回归**(commit `e5ca686`,P-014)——查出 monitor「CO2≤1000=ASHRAE 62.1」是占位**误区**,降到 **WELL 900** 对齐,demo 实证误归因消失;失效检索种子留扩 200 重写。② **runner 并行化**(commit `5ea0eb6`,P-015)——`--workers`+`_pmap`,generate `--n6` **162.7s→48.7s(3.3x)**、结果一致;并挖出并修 **transformers 5.9.0 reranker 并发不安全**(GPU forward 锁 + `_get_stack` 双检锁 + 预热,真实 mcp-rag-server 接并发也需要)。**下次接:** ~~item 3 = acoustic(WHO Noise)~~ → 已超额完成,见下方 2026-06-07 条。
>
> **🆕 2026-06-07:** **thermal/lighting/acoustic 三域真 corpus 一次性接入(P-016,本 session)** —— 作者拍板**弃付费 ASHRAE 55 / EN 12464 / WHO Noise**,改用**已在手的同一份 WELL v2 PDF** 的另外三个 concept(原来只取了 Air):pypdf 扫描定位全 10 concept 物理页范围,`corpus_manifest.json` 加三条(Light p103-129 / Thermal Comfort p160-184 / Sound p185-213,同一 file 靠 `pages`+domain filter 切片),`ingest --source corpus` 出 **824 chunks**(四 domain 全真,sample 占位退场;**按作者指定三新域先不做 contextual**)。三域检索各命中 WELL 真值,并**暴露 `thresholds.py` 占位待对齐**:thermal 19-26 → WELL **21-25 °C**(引 ASHRAE 55-2013);lighting 占位标 **EN 12464-1** 但真 corpus 引的是 **CIBSE SLL**(又一个"占位引了不在库的标准",同 P-014 的 ASHRAE-1000 雷)+ 循环区 110 lux;acoustic 单一 ≤55 → WELL **分级 50/55/60 dBA + 卧室 35 dBA**。**下次接:** 三域走 P-014 纵向对齐链(thresholds→monitor rule→planner goal→generate 引用→bench gold)+ 三域 bench 种子 + 可选 contextual 全量重 embed。详见 DEVLOG P-016。

> **🆕 2026-06-08(Phase 5 抢先启动·问答优先 MVP):** 作者拍板**暂搁论文证据线,先交付可部署成品**——落地**问答管家**(语音/文字):`ConversationalAgent` 两步式(意图分类 flash→**按需取数**→合成 flash,免 RAG/免 embedding key);范围判定("温度正常吗")复用 `thresholds.py`(monitor 同款真值);新增轻量采样器 `ops/sampler.py`+`sensor_readings` 表、ticket `list_incidents`、semantic `list_facts`(scroll 全量)、级联语音 mock(浏览器 Web Speech,零 key)、FastAPI+HTMX 对话前端。端到端实测 5 类问题全通,**按需取数核验通过**(A/A+ 不拉大源、B 拉 stats、C 拉 incidents、E 拒答)。详见 Phase 5 进度 + DEVLOG P-017。

**两条架构红线风险已坐实闭环:** ① 15min 跨重启恢复(Phase 1) ② 子图状态隔离(Phase 2)——全系统最大的两个技术不确定性已排除。

**🔜 下一步(Phase 4 续,优先级序):** ✅已清:P-009、grade/rewrite 入 runner、记忆消融 +1.00、自相矛盾陷阱(P-011)、ablate 条件验证(`--ablate-check`)、**真 corpus 切换回归(P-014,co2→WELL 900)**、**runner 并行化(P-015,3.3x + 修 reranker 并发不安全)**。**剩:** ① **GPT-4o 跨模型 baseline + GPT-4o/Claude 双裁判**(卡 key,去主场嫌疑)② ✅ **三 domain 真 corpus 已接入**(WELL v2 同一 PDF 的 Light/Thermal/Sound concept,824 chunks,弃付费 ASHRAE/EN/WHO,P-016)→ 新剩:三域 thresholds/bench 走 P-014 纵向对齐 + 可选 contextual ③ 扩 200 + 判别性误导检索难题——**作者拍板等 Phase 5 真 PDF corpus**(强基座下简单任务无法判别,硬凑无意义,P-011)。"无数字不立论"的关口:架构价值现由**记忆消融 +1.00** 承载,≥10pp-vs-baseline 待真 corpus/GPT-4o。

**剩余路线:** Phase 4 评测 → Phase 5 对话+前端+硬件+上线稳定化 →(代码冻结 ~09-12)→ Phase 6 自主长跑 ≥8 周(Week8>Week1) → Phase 7 论文 + IEQ-Bench 开源。

**距离 6 条成功标准的硬缺口**(全在 Phase 4–6 产出):尚无 IEQ-Bench 分数、无 baseline 对比、无真实硬件/InfluxDB 数据、无 ≥4 周自主运行、无 Week8 vs Week1 证据、无公开 HF 数据集。**当前定性:功能骨架就绪(0–3);论文实证开采——Phase 4 首个 delta(generate/v4)已落地,baseline 对照 / Week8 证据 / HF 数据集待续(4–6)。**

**🔍 Phase 0–3 回归验证(2026-05-30 完整跑通):** 7 项全绿——静态质量门 / 31 模块编译 / 基础设施连通(PG 4 表 + Qdrant 3 collection) / 检索栈 38ms / 🔴 跨重启恢复 / 🔴 子图隔离零泄漏 / 三层记忆+反思。期间修复 2 处 ruff format 漂移 + demo 注释滞后。唯一实质问题:**generate 自洽 flaky**(co2_spike 实测 33% critic 正当否决,根因 generate 正文降幅预测与 `target_value` 矛盾),经决策留 Phase 4 作首个 bench 量化目标(见下)。

---

## 时间线倒推

两条成功标准是时间硬约束:"自主运行 ≥ 4 周" + "Week 8 vs Week 1 记忆固化改善"(后者需在线连跑 ≥ 8 周)。倒推出开发窗口(Phase 0–5)= 现在到 ~9 月中,约 14–15 周。

| Phase | 内容 | 目标窗口 | 性质 |
|---|---|---|---|
| 0 | 地基 + 风险归档 | 05-26 → 06-06 (~1.5w) | 开发 · ✅ 2026-05-25 关闭 |
| 1 | 首条垂直闭环(模拟器 + 单 domain 桩) | 06-08 → 06-21 (2w) | 开发 · ✅ 2026-05-26 关闭(超前) |
| 2 | Agentic RAG 做实 + Planner 完整 DAG | 06-22 → 07-12 (3w) | 开发 · ✅ 2026-05-29 关闭(超前) |
| 3 | 三层记忆 + 周反思 | 07-13 → 07-31 (2.5w) | 开发 · ✅ 2026-05-29 关闭(超前) |
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

- [x] `sensing/simulator/room.py`(原 `co2.py`):physics-based CO2 模型(质量平衡:occupancy 产气 + 通风换气);`reset_room`/`save_room`/`get_room` 房间状态持久化,供 resume 跨进程读回。**Phase 2(2026-05-29)扩为 `RoomState` 四 domain**:CO2 留物理模型,thermal/lighting/acoustic 静态注入读数(无 actuator 不演化),`read_all()` 供 sensor server 读全部五传感器
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

- [~] `rag/ingest.py`:chunk → BGE-M3 嵌入入 Qdrant。**2026-06-06 真 PDF + contextual prefix 落地**:`--source auto|corpus|sample` + `corpus_manifest.json`(**渐进替换**:真 PDF 覆盖的 domain 换真、未覆盖留 sample filler);pypdf 读 WELL v2 Air(p11-46,`collapse_repeated_lines` 去 PDF 双层重复,257 chunks);contextual prefix 接节点 #10(`make_contextual_prefix`→FAST=**v4-flash**,prompt 版本化 `ops/prompts/ingest/contextual_prefix/v1.md`,只改 `embed_text`、返回 `text` 纯净,249/250)。召回命中真实阈值(CO2 500/750ppm above outdoor、PM2.5 MERV),不再占位 1000ppm(详见 DEVLOG P-013)。**2026-06-07 更新**:thermal/lighting/acoustic 也接入真 WELL corpus(同一 PDF 的 Light/Thermal/Sound concept,弃付费 ASHRAE/EN/WHO,824 chunks,P-016)。**仍 `[~]`**:三新域按作者指定**先不做 contextual**(embed_text=text,与 airquality 不对称)+ thresholds 占位 / bench 种子待 P-014 式纵向对齐(下次)
- [x] `rag/retrieve.py`:BM25 + BGE-M3 双路召回 + bge-reranker-v2-m3 精排 — 2026-05-27 实测 GPU fp16 **51ms**(<500ms 预算),top1 命中正确条款,domain filter 生效。加载对齐 `vram_spike`(SentenceTransformer+safetensors / 手写 transformers reranker),非 douluo 的 CPU/CrossEncoder
- [x] `mcp-rag-server`:FastMCP 包 `retrieve.py`,**绝不含 LLM**(硬约束 #9) — lazy singleton,MCP 协议实测返回结构化 chunks
- [x] `agents/specialists/builder.py`:五节点 `decompose`(flash)/`retrieve`(无LLM,调 mcp-rag)/`grade`(flash 强制)/`rewrite`(LOCAL)/`generate`(flash 强制);domain 参数化;**module-load 时 compile 一次** — 2026-05-27 子图独立 + 接主图 `run_incident auto` 端到端实测跑通
- [x] 四个 wrapper `airquality/thermal/lighting/acoustic.py`:薄包装,共享 `run_specialist(payload,domain)`(接 dispatch fan-out 的 `Send` payload,非父 state);**四个全接为主图 fan-out 诊断节点**(2026-05-28 DAG 化)——诊断都跑,但只 airquality 有 actuator/action,其余三个的执行分支仍 Phase 5
- [x] 🔴 **subgraph 状态隔离**:`SpecialistState` 独立 schema,只 `subtask` 进、`final_diagnosis` 出 — 2026-05-27 实证父 checkpoint 仅 11 个 `MainIncidentState` 字段,`retrieved_chunks`/`grade_reason`/`rewrite_count` 零泄漏(风险点#2 关闭)
- [x] `generate` 输出强制 `expected_outcome:{target_metric,target_value,target_time_min}`,Pydantic `extra=forbid` 卡(硬约束 #13) — subtask_id 代码注入不信 LLM。**generate prompt bump v2(2026-05-28)**:CriticAgent 上线后实测暴露 generate 系统性产出"正文阈值(如 below 800ppm)≠ `target_value`(900ppm)"——Verifier 拿 `target_value` 核验,二者必须一致。v2 加规则 4 强制正文阈值 = `target_value`;改后 critic approve→关单 3/3(v1 时 ~1/3)。**bump v3(2026-05-29)**:demo 四 domain 实跑暴露 `target_metric` 跨节点契约缺口——critic 查物理范围表 + verifier 查 `read_sensors` 都按 metric 键名,但 generate 对 lighting/acoustic 产出 `illuminance`/`noise level` 自然语言名→critic 正当否决 + verifier KeyError 隐患;v3 加规则 5 强制 `target_metric ∈ {co2,temperature,humidity,lux,noise_db}`。builder 指向 `generate/v3`
- [x] `CriticAgent.validate`(`agents/critic.py`,2026-05-28):**作者拍板方案 B** —— 状态隔离让 critic 在父图看不到子图 `retrieved_chunks`,放弃对照原文 trace-back(方案 A 需 `SpecialistResult.citations` 跨界,未采纳)。critic 只验两件能看到的事:① 确定性 plausibility 数值底线(target_metric 已知 / target_value 在物理范围 / target_time_min∈[1,240],无 LLM);② LLM 判 diagnosis 内部一致性 + expected_outcome 是否从诊断推得出(`critic.validate` 节点,LOCAL→flash)。LLM 失败走确定性兜底(底线过则批准,不死锁)。校验 **primary_result**;disapprove→写 ticket FAILED + 条件边路由 END **不执行**(不对不可信诊断动执行器)。disapprove→**replan** 留 Phase 3(需配 subtask_results 重置)。`core/graph.py` critic 后改条件边 `approved→autonomy_gate / 否→END`
- [x] `PlannerAgent` 升级:完整 Plan-and-Execute + ReWOO DAG(prompt v2,REASONING tier,temperature=0 保持 thinking)— 2026-05-28 实测出真 DAG(CO2 incident → S1 airquality + S2 thermal `depends_on=[S1]`)。主图改**波次拓扑** `planner→hydrate_placeholders→dispatch⇄{4 specialist}→critic`:`route_dispatch` 条件边按 ready 波次 `Send(domain,{subtask})` fan-out(无依赖并行,实测 LangGraph 1.2.1 Send+Pydantic state OK),specialist 回边 `hydrate_placeholders` 跑下一波;`#{id}.{field}` 占位符由 `hydrate_placeholders` 节点解析(实测 S2 的 `#S1.diagnosis` 填进 S1 真实诊断)。新增 `subtask_results` merge reducer + `failed_subtasks` add reducer(并行 fan-out 并发写安全)。`primary_result()` 按 anomaly domain 挑主子任务,驱动 autonomy_gate/action/verifier(实测 action 用 co2 而非 S2 的 operative_temperature)。四 specialist 全接为 fan-out **诊断**节点(actuator/action 仍 Phase 5,只 airquality 执行)。rewrite ≤3 沿用子图。mypy --strict clean
- [x] **demo 场景库 + 展示 runner**(2026-05-29 落地 + 四场景实测):把 `room.py::reset_room()` 的单一硬编码异常泛化成 `sensing/simulator/scenarios.py` 命名场景注册表(每场景 = 房间初始参数 + 预期 domain/sensor + `closes_loop`);`RoomState` 默认全带内,场景只 override 目标传感器(避免误触发 co2,因 monitor 遍历 co2 在前)。`ops/scripts/demo.py` 共用 `build_main_graph`(绝不另起平行系统),`graph.stream(stream_mode="updates")` 逐节点打印 agent→字段变更→产出;`--list` 列场景;`run_incident.py` 因 reset_room 向后兼容仍可用。**四场景实测**:co2_spike 完整闭环关单(co2 1300→679,met);overheating/dim_workspace/noisy_room 正确路由 thermal/lighting/acoustic、过 critic、停在 autonomy_gate Tier3 `interrupt()`(执行层 Phase 5)。本阶段只做**突发跳变**;渐变劣化、复发模式(依赖 Phase 3 记忆)留后。

**验收:✅ 2026-05-29 全部达成,Phase 2 关闭(早于目标窗口)** — 一个需多子任务 + RAG 的复杂 incident 跑通;grade 失败触发 rewrite;ReWOO 占位符正确 hydrate;父 checkpoint 不含 RAG 中间态;`demo.py` 四突发跳变场景逐节点演示(co2_spike 关单 / 其余三停 Tier3)。**遗留**(不卡验收):ingest contextual prefix + 真 PDF(等真 corpus 才显效);grade prompt 真 corpus 后调。

**📍 进度(2026-05-27 session):** 检索地基 + Agentic RAG 子图整条打通并实测——retrieve 51ms / mcp-rag 无 LLM / 五节点 / 🔴状态隔离关闭 / rewrite 反思循环(构造缺失信息 query 触发 grade 判不够→rewrite×3→generate 诚实"原文未提及")。依赖经 `uv add` 进 `pyproject.toml`(torch cu121 + sentence-transformers + transformers + qdrant-client + rank-bm25 + langchain-text-splitters)。
**本次额外修复(已落代码)**:① builder 四节点 `extra_body={"thinking":{"type":"disabled"}}` —— v4 reasoning 偶发空 `content` 会让 generate 无端失败;② grade/decompose `temperature=0`、generate 0.2、rewrite 0.3 —— 否则 self-reflective 判断随机、rewrite 循环不可复现。修完延迟 ~11s→~3s/轮、判断可复现。
**📍 进度(2026-05-28 session):** Planner 完整 ReWOO DAG + 波次 fan-out 拓扑落地并端到端实测关单(详见上方 `[x]` Planner 行)。验收四点已坐实:多子任务+RAG✓ / grade 失败触发 rewrite(S2 rewrite×3)✓ / ReWOO 占位符正确 hydrate✓ / 父 checkpoint 仅 11 个 `MainIncidentState` 字段、RAG 中间态零泄漏✓。Phase 2 RAG 检索栈成果(上一 session)已 commit(179507c)。
**📍 进度(2026-05-28 session 续):** CriticAgent 方案 B 落地并端到端实测(详见上方 `[x]` Critic 行)。Phase 2 验收功能点只剩 demo runner。
**📍 进度(2026-05-29 session):** Phase 2 最后一个验收点 demo 落地并四场景实测,**Phase 2 关闭**。模拟器 `co2.py→room.py`(`CO2Room→RoomState`,git mv 保留历史)扩四 domain 静态注入 + `read_all()`;sensor server 改读 `read_all()`;新增 `sensing/simulator/scenarios.py`(4 突发跳变场景)+ `ops/scripts/demo.py`(stream 逐节点展示,airquality 关单 / 其余三 Tier3 收尾)。demo 四 domain 实跑**暴露并修复两个 bug**:① generate `target_metric` 跨节点契约(bump v3,见上方 generate 行);② **ReWOO 占位符 hydrate**——planner LLM 偶发产出带花括号的 `#{S1}.diagnosis`(照抄 `#{subtask_id}` 元符号),原正则 `#(\w+)\.` 不认致依赖子任务拿不到上游诊断(ReWOO 依赖传递实际断裂、依赖型 specialist 空跑 rewrite×3),放宽 `core/graph.py` 正则为 `#\{?(\w+)\}?\.` 防御漂移,重测 S2 占位符正确填入 S1 真诊断。ruff + mypy --strict core/ clean。
**未完成,下次接(优先级序)**:1) ingest contextual prefix(接 router #10,等真 PDF 才显效);2) grade prompt 可能偏严,真 corpus 后调;3) 进入 **Phase 3 三层记忆 + 周反思**。

---

## Phase 3 — 三层记忆 + 周反思

**目标:** 系统开始"变聪明",记忆闭环成立(Week8>Week1 的机制基础)。

- [x] `memory/episodic.py`(2026-05-29):Qdrant collection `ieq_incidents` 存结案轨迹 + `retrieve_similar()`——被 planner 节点 **inline 调用,非 LangGraph 节点**。**非对称 embedding**(作者拍板):相似度只锚定 anomaly 特征(召回时 planner 唯一可用信息),诊断/动作/结果进 payload 当"经验"带回;CPU BGE-M3(复用 rag loader、device=cpu,不抢 dev 期 GPU 的 RAG 4.0GB),lazy singleton;确定性 point_id(`uuid5(ns,incident_id)`)幂等覆盖
- [x] `memory/semantic.py`(2026-05-29):Qdrant `ieq_semantic_facts`,fact 文本入向量(复用 episodic 的 CPU BGE-M3),payload 带 incident_type/evidence_ids/week;`save_facts`(reflection 写)+`retrieve_facts`(召回,实测模糊 query score 0.75 命中)。`memory/procedural.py`:Postgres `sops` 表,`SOPTemplate` 走 pending→active|rejected 生命周期;`queue_sop`(reflection 写 pending)+`approve_sop`/`reject_sop`(人工签核)+`active_sops`(未来触发匹配,Phase 5+)
- [x] **memory 写入只走 `memory/` 模块函数 + 审计日志**,agent 不直接写(硬约束 #3)——三层全落实:verifier 调 `save_trajectory`,reflection `consolidate` 节点调 `save_facts`/`queue_sop`,均 structlog 审计(`episodic_saved`/`semantic_saved`/`sop_queued`/`sop_reviewed`);无 agent 内联 upsert
- [x] `ReflectionGraph`(`core/reflection.py`,2026-05-29):`load_episodes→route_by_type(Send fan-out)→reflect→consolidate`;**按 incident type 分块**——每类一个 `Send` 分支(复用主图 dispatch 范式),各分支独立调 reflector 防 OOM 128K;Reflector **v4-pro 强制**(硬约束 #12,router `reflector.semantic`/`reflector.procedural`→REASONING);LLM 失败返 [] 不编造(defer+alert);独立图无 checkpointer(周批处理无须 resume)。cron 接线留 Phase 5,本阶段 `ops/scripts/run_reflection.py` 手动触发(默认近 7 天窗口,`--since`/`--week` 可调)
- [x] procedural SOP 写 `pending_sops` 队列 → **人工签核才激活**(防幻觉 SOP 污染,硬约束 #8)——`queue_sop` 落 status=pending,`approve_sop` 才转 active;`run_reflection.py --pending` 列队列;实测 reflector 忠于轨迹(SOP 步骤=轨迹真实单动作 set_ventilation,未编造多余步骤)
- [x] 把 Phase 1 的 `memory_retrieve` 占位换成真 episodic 召回(2026-05-29)——`PlannerAgent._retrieve_similar` 接真召回;prompt **bump v3** 加"如何利用相似案例"(resolved 当正面证据 / FAILED 当反面警告 / 低相似则忽略,案例 advisory 不凭空造子任务);state.similar_cases 只存 ids(审计),完整 EpisodicCase 只进 prompt 不进 checkpoint

**验收:✅ 2026-05-29 三点全达成,Phase 3 关闭(早于目标窗口)** — ①结案 incident 落 episodic(库内 2 条 co2 met);②手动触发 reflection 产 `SF-2026-W22-001`(建筑特定 fact:"R1 CO2 达 1300ppm 时通风调高 450m³/h 可降至 800 以下",2 条证据,召回 score 0.75)+ `SOP-2026-001`(pending,触发 co2>1000,步骤忠于轨迹);③新 incident 召回相似旧案影响 planner(上个 session run2 plan 由 S1+S2 收敛为 S1)。

**📍 进度(2026-05-29 session):** Phase 3 **分步推进——episodic 闭环先落地并端到端实测**(作者拍板:先打通"记忆影响规划"骨架,reflection 下个 session)。烟测:save→count→recall 召回自身 score=0.92、payload 完整往返。端到端 demo `co2_spike` 两跑实证:run1 冷启动(`episodic_recall_empty`,planner `recalled=[]`)→ 关单 → `episodic_saved`;run2 召回到 run1(`hit_ids=[I-…035351]`,planner `recalled=[…]`,plan 形状从 S1+S2 收敛为 S1),Qdrant `ieq_incidents` points=2。**验收 ①③ 达成;② reflection 待**。途中确认 critic 偶发正当否决(generate 在诊断里塞"15min 降 150-300 ppm"物理估计、与自定 target 800 的降幅矛盾)——非 Phase 3 回归,属已知 generate 非确定性,留 Phase 4 bench 量化。顺带修 `rag/retrieve.py` 一处既有 E501。
**📍 进度(2026-05-29 session 续):** Phase 3 剩余全部落地,**Phase 3 关闭**。新增 `memory/semantic.py`(Qdrant facts)+`memory/procedural.py`(Postgres SOP 生命周期)+`agents/reflector.py`(semantic/procedural 双 prompt,REASONING tier,失败返 [] 不编造)+`ops/prompts/reflector/{semantic,procedural}/v1.md`+`core/reflection.py`(ReflectionGraph,按 type fan-out,复用 graph.py 的 wrap node plumbing 兼容 typed StateGraph)+`ops/scripts/run_reflection.py`(手动 runner + `--pending` 列签核队列)。episodic 加 `list_trajectories`(窗口全扫,区别于 `retrieve_similar` 的 top-k 召回)。端到端实测:2 条 co2 episodic → reflection 产 1 fact + 1 pending SOP,均建筑特定、2 条证据、忠于轨迹(SOP 未编造多余步骤);`retrieve_facts` 模糊 query score 0.75 命中。ruff + mypy --strict core/ clean。
**下次接(优先级序):** 1) **Phase 4 IEQ-Bench 评测体系 + baseline**(200 任务 / 双裁判 / GPT-4o+ReAct 基线);2) 顺带验证 reflection 在多 type、多复发样本下的归纳质量(现仅 airquality 2 条,Phase 4 bench 量化);3) 遗留:ingest contextual prefix + 真 PDF(等真 corpus)。

---

## Phase 4 — IEQ-Bench 评测体系 + baseline

**目标:** 无数字不立论(成功标准:≥75% 任务成功、领先 GPT-4o+ReAct ≥10pp)。

- [x] **🎯 首个量化目标**:**generate 自洽 flaky** — bump `generate/v4` 加规则 6(禁止正文预测降幅/到达值,只承诺单一 target_value;明确保留引用标准阈值权利护住 groundedness)。**✅ delta 已量化**(2026-05-31,`--n20` 同环境 before/after):co2 自洽率 **0.70→1.00**(否决率 30%→0%) · mean_hit 1.0→1.0(groundedness 未伤) · thermal 对照 0.95→1.0(未误伤);+0.30 远超 `--n20` 噪声 ±0.07。builder 指向 v4(05-30 手测的 62–67% 系高方差单点,故重测取同环境对照)
- [~] `eval/ieq_bench/`:200 任务,覆盖各 agent / domain / 节点能力。**✅ schema/loader + 24 种子**(retrieval/critic/planner/generate + **grade 6 / rewrite 2**,六 capability,seed 表全绿)+ **6 个 L3 e2e**(4 原 + 2 negative-control)+ **4 个 L3 recurrence**(记忆消融);**⏳ 待**: 扩到 200——其中**判别性难题(误导性检索)留 Phase 5 真 corpus**(作者拍板,P-011:强基座下简单任务无法判别,硬凑无意义)
- [x] **grade/rewrite 入 runner**(2026-05-31):暴露 `SPECIALIST_NODES` 单节点。grade=控制 chunk 集判 sufficiency(6 任务正反平衡,6/6);rewrite=gold-MRR before/after(co2 0.2→1.0、thermal 0.333→1.0 真抬升;acoustic/lighting 池太小排名不动,排除避免平凡通过)
- [~] `eval/judge.py`:双裁判;prompt **强制** "only compare to expected, do not use prior knowledge"。**✅ deepseek-flash 单裁判可跑**(模型名参数化,确定性任务暂不依赖它);**⏳ 待**: 换 GPT-4o + Claude Sonnet 4.6 双裁判(需 OpenAI/Anthropic key)
- [x] `eval/runner.py`。**✅ 可跑**(`--seed`/`--cap`/`--n`/`--compare`/`--ablate-memory`/`--only`,确定性指标 + 出 reports 表,incident_id=None 免污染 ticket);**✅ 并行化(2026-06-06)**:`--workers`(默认 4,`=1` 退顺序)+ `_pmap` 线程池并行 generate/compare 内层 sample + ablate-memory 跨 task;实测 generate `--n6` **162.7s→48.7s(3.3x)**、结果一致。途中**挖出并修一个真实并发 bug**:`_pmap` 首次引入并发 retrieve 触发 transformers 5.9.0 reranker 非线程安全(dtype Half/Float + import 竞态),加 `retrieve.py` GPU forward 锁 + `rag/server.py` `_get_stack` 双检锁 + 预热修复(真实 mcp-rag-server 上线接并发也需要);另修 seed 路径漏传 workers。详见 DEVLOG P-015
- [x] **记忆消融 `--ablate-memory`**(2026-05-31,论文 Week8>Week1 离线证据):同 planner、召回 ON/OFF、温度 0 确定性,看建筑特定知识有没有进 plan goal。**bump planner/v4**(resolved 案例也点名建筑特定原因/修法,v3 只规避 FAILED)→ macro recall-lift **+0.25→+1.00**(4/4 有记忆进规划、0/4 无记忆)。**这是 bench 里架构价值的最强判别证据**(见 P-012)
- [~] baseline:对比基线。**✅ deepseek-flash ReAct 端到端跑通**(手写 thought/action/observation,不用 langchain;同模型对照隔离架构贡献);**✅ 接 runner 出对照表**(`--compare`:同 anomaly→两臂→同一 critic+hit 裁判,`arm_value()` 按任务真值对齐模拟器,任意值都公平)。**❗诚实结论(P-011):≥10pp-vs-ReAct 在当前强基座 + 简单任务上立不住**——自相矛盾陷阱实测两臂全 1.00(v4-flash 不会傻到复述降幅),原 +10pp 的 acoustic 单域优势是 n5 噪声(lighting/acoustic baseline 在 0.6/1.0 间乱跳)。**架构价值改由记忆消融 +1.00 承载**(上一行);≥10pp 的稳健证据**作者拍板留 Phase 5 真 corpus 的误导性检索难题** + GPT-4o 跨模型 baseline(需 key)
- [ ] **GPT-4o 跨模型 baseline + GPT-4o/Claude 双裁判**(去"自家 critic 当裁判"主场嫌疑)——**未开始,卡 OpenAI/Anthropic key**
- [~] 把"每次代码改动跑 IEQ-Bench"变成习惯(改 prompt/改节点模型必附 delta)——**机制就绪**(runner);**首次完整走通**(2026-05-31 generate v3→v4:同 `--n20` before/after delta 才算数)
- [x] 用这套验证 `llm_routing.md` 的 ablate 条件——**✅ `--ablate-check`(2026-06-01)**:5 节点(grade/generate/rewrite/critic/planner)逐个量出触发指标比阈值,当前全在 floor 之上 `escalate=False`(routing 有数字支撑)。generate 的 hit_only<0.85 与 llm_routing #4e 字面吻合;grade/rewrite/critic/planner 用绝对阈值代理(字面条件要 V3-vs-flash 跨模型比,留有 key 时做)

**验收:** IEQ-Bench v1 一键跑 ✅(`--seed`/`--compare`/`--ablate-memory`/`--ablate-check`);系统得分 + baseline 得分出表 ✅(e2e `--compare`,诚实结论 ≥10pp 当前未稳留 Phase5);ablate 条件可量化触发 ✅(`--ablate-check` 全节点在 floor 之上)。**剩(卡 key):** GPT-4o 跨模型 baseline + 双裁判;扩 200 等 Phase5 真 corpus。

**📍 进度(2026-05-30 session):** Phase 4 **启动里程碑落地,`--seed` 实测出首张表**。`eval/` bench 骨架可运行——`ieq_bench/{schema,loader,tasks}` + `metrics`(确定性指标) + `judge`(deepseek-flash,模型名参数化) + `runner` + `baselines/react`(朴素 ReAct,不用 langchain)。16 种子任务复用现有资产派生,覆盖 4 capability;裁判 + baseline 起步全用 deepseek-v4-flash(作者拍板,后期换 GPT-4o+Claude 双裁判 / GPT-4o baseline)。

| layer · capability | n | pass | score |
|---|---|---|---|
| L1 retrieval | 5 | 1.00 | 1.00 |
| L2 critic | 5 | 1.00 | 1.00 |
| L2 generate | 2 | 0.50 | 0.67 |
| L2 planner | 4 | 1.00 | 1.00 |
| **ALL** | **16** | **0.94** | **0.96** |

retrieval/critic/planner 满分(critic 对 good 批准、incoherent/implausible/badmetric 三类 bad 全否决,判别力坐实);**唯一弱点 = generate co2 自洽 flaky**——co2(goal 明示 target 800)critic 否决率 **62–67%**(n=8→5/8、n=6→4/6) vs thermal 对照 12.5%,mean_hit 0.875(纯自洽矛盾:正文复述 corpus `ops-note`"降150–300ppm"与 target 800 抵触,非 groundedness)。**这是 generate/v4 的对照基准。** 修 bug:bench critic 探针用 `incident_id=None` 免写 ticket。baseline react demo 实测端到端跑通(6 步:read_sensors→retrieve×3→set_ventilation→finish,产 typed expected_outcome)。**待续**:grade/rewrite/e2e 入 runner · baseline 接 runner 出对照表 · 扩到 200 · 换真双裁判(需 key) · bump generate/v4 测 delta。

**📍 进度(2026-05-31 session):** Phase 4 **首个量化目标 generate/v4 落地并 delta 验证**。先 `--n20` 同环境跑 v3 baseline:co2 自洽率 **0.70**(否决 30%)、`mean_hit=1.0` → 坐实纯自洽矛盾(非 groundedness);thermal 对照 0.95。bump `generate/v4` 加规则 6(禁止正文预测降幅/到达值,明确保留引用标准阈值权利),`builder.py` 指向 v4,同条件重跑:**co2 0.70→1.00(否决 30%→0%) · mean_hit 1.0→1.0(未伤 groundedness) · thermal→1.0(未误伤对照)**,+0.30 远超 `--n20` 噪声 ±0.07。3 个 v4 样本人工核验:诊断完整(cause+action+ASHRAE/WELL 引用)、矛盾的降幅预测消失、target 一致。首次完整走通"改 prompt = bump v+1 + 同环境 before/after delta"纪律。顺带新建 `DEVLOG.md`(问题/踩坑复盘,回填 P-001..P-009)+ README 接入并修正其滞后状态。**下次接**:grade/rewrite/e2e 入 runner · baseline 接 runner 出对照表 · 扩到 200。

**📍 进度(2026-05-31 session 续):** **baseline 接 runner 出对照表落地**——`eval/runner.py` 加 `--compare`(L3 e2e 双臂):同一 anomaly 进**系统臂**(`planner`+episodic 召回 → 主子任务 → `SpecialistSubgraph` Agentic RAG)和 **baseline 臂**(朴素 ReAct),两边诊断喂**同一个真 `CriticAgent`**(信任门 = 能否执行)+ groundedness hit,success = critic 批准率;新增 `eval/ieq_bench/tasks/l3_e2e.jsonl`(4 域)+ `ComparisonRow` schema + `_print_compare_table`(打 gap、判 ≥10pp)。**公平性**:跑 baseline 前 `arm(scenario)` 对齐模拟器读数到 anomaly(否则 baseline `read_sensors` 读 in-band 默认值与 prompt 矛盾,不公平地坑它)。`--n5` 实测:**系统 1.00 / ReAct 0.90,macro +10.0pp**。**但这个达标易碎**——gap 全来自 acoustic(baseline 0.60,2/5 被 critic 正当否决),co2/thermal/lighting 两臂全 1.00:单跳变任务对 v4-flash 基座太简单,架构对照趋同。**方法论结论(P-010)**:扩 200 必须刻意塞「基座单跑会栽、规划/记忆/RAG 能救」的判别性难任务,否则 ≥10pp 立不住。ruff + mypy clean。**下次接**:grade/rewrite 入 runner · 扩判别性难任务到 200 · GPT-4o 跨模型 baseline + 双裁判。

**📍 进度(2026-06-01 session):** Phase 4 推进一大步,且**坐实一个诚实的负面结论**。落地:① **P-009** verifier 对齐 `primary_result()`(commit `ffeeca0`);② **grade/rewrite 入 runner**——暴露 `SPECIALIST_NODES` 单节点,grade 6 任务(控制 chunk 集判 sufficiency,正反平衡 6/6)、rewrite 2 任务(gold-MRR before/after,co2 0.2→1.0、thermal 0.333→1.0;acoustic/lighting 池太小排名不动故排除),seed 表升至 **24 任务全绿**;③ **记忆消融 `--ablate-memory`**(commit `207f2e6`)——作者拍板:记忆是**消融轴**(同 planner 召回 ON/OFF)而非 system-vs-ReAct(ReAct 无 planner 无记忆,混在一起证不干净)。用 planner `temperature=0` 确定性接缝 `plan_with_recall`,看建筑特定知识有没有进 plan goal;**bump planner/v4**(resolved 案例也点名建筑特定原因/修法,v3 只规避 FAILED)→ macro recall-lift **+0.25→+0.75→+1.00**(gold 词修正,见 P-012),4/4 有记忆进规划、0/4 无记忆,**这是 bench 里架构价值的最强判别证据**;④ **自相矛盾陷阱**(作者从难题菜单选的)**实测失败**(P-011):高值 CO2 两臂全 1.00——v4-flash 基座太强不会复述降幅,陷阱不咬。两个 hard 任务**重标为 negative control**。**诚实定调:≥10pp-vs-ReAct 在当前强基座 + 简单任务上立不住**,作者拍板留 Phase 5 真 corpus 的误导性检索难题再冲;架构价值现由记忆消融 +1.00 承载。新增 `arm_value()`(按任务真值公平对齐)+ runner `--only` 过滤。回填 DEVLOG P-011/P-012、P-009 转 ✅。**下次接**:GPT-4o 跨模型 baseline + 双裁判(卡 key) · llm_routing ablate 条件验证 · runner 并行化 · 扩 200(等 Phase5 真 corpus)。

**📍 进度(2026-06-06 session):** **真 PDF corpus 接入(airquality)+ contextual prefix(节点 #10)+ PDF 去重**(commit `84feee0`,详见上方 Phase 2 ingest 行 + DEVLOG P-013)。**完成**:① pypdf 读真 WELL v2 Air(IWBI 官方 CDN,366p 取 p11-46)替换占位,`--source auto|corpus|sample` + `corpus_manifest.json` **渐进替换**(真覆盖域换真、未覆盖留 sample filler,不破 thermal/lighting/acoustic);② `collapse_repeated_lines` 去 PDF 双层重复(257 chunks);③ contextual prefix 走 router→**deepseek-v4-flash**(作者指定),prompt 版本化不内联,并发,只改 `embed_text`、返回 `text` 纯净,249/250 applied(失败退化不中断)。**坐实一个 Phase 4 判别性素材**:真 corpus 改变 airquality 知识形状——召回从占位 1000ppm 变成 WELL 真实阈值(CO2 500/750ppm above outdoor、PM2.5 MERV 表),正是 P-010/P-011 缺的「基座单跑会栽、检索能救」原料。**新待办(优先级序)**:① ✅ **真 corpus 切换回归(本 session 已清,见下)**;② 其他三 domain 真 corpus(WHO Noise=acoustic 免费可下,EN/ASHRAE 付费卡获取);③ 有真 corpus 后扩 200 的误导性检索难题(冲 ≥10pp);④ grade prompt 按真 corpus 重调。

**📍 进度(2026-06-06 session 续):** **真 corpus 切换回归 done**(新待办①清)。三层打架盘清并对齐:① **monitor 占位误区**——`thresholds.py` 写「co2 ≤1000 (ASHRAE 62.1 guideline)」是个**广为流传的错误说法**(62.1 设通风率不设 1000ppm CO2 上限),且 1000 在 WELL corpus 0 命中(真 WELL A01 = 900/750 ppm);这条假归因经 monitor anomaly→planner goal→generate 一路传染,让 generate 把 goal 的「1000/ASHRAE」误当「excerpt 1」引用。**作者拍板触发线 1000→900 对齐 WELL**(`thresholds.py` co2 `high=900` + rule 引 WELL 1-point),连带排查无误触发(默认 co2=650<900)/critic 物理范围不打架;**复跑 demo `co2_spike` 实证**:诊断改为「exceeds the 900 ppm threshold specified in the WELL v2 standard (excerpt 1)」(误归因消失、excerpt 1 真含该值)、`target_value=900`、critic approve、verifier met/closed。② **检索 bench 1.00→0.60**:两个 co2 种子的 gold source(`ashrae-62.1`/`ops-note`)是旧 sample 标签、已不在真库——**非检索能力退化,是 gold 陈旧**;作者拍板**并入扩 200 统一按 WELL 重写**(连同 generate/e2e 里硬编码的 1000/ASHRAE anomaly 输入)。详见 DEVLOG P-014。**教训**:切 corpus 是一条 `corpus→monitor 阈值→planner goal→generate 引用→bench gold` 的纵向回归链,占位阈值甚至可能编码了"常识级误区",真 corpus 是照妖镜。

---

## Phase 5 — 对话入口 + 前端 + 硬件落地 + 上线稳定化

**目标:** 补齐人机入口和真实硬件,进入可上线状态。

- [~] `ConversationalGraph`:**问答管家 MVP 落地(2026-06-08)**——`ConversationalAgent` 两步式(意图分类→按需取数→合成),收 thresholds/读数/stats/incident/facts/SOP;**免 RAG/embedding**(范围判定靠 thresholds=corpus 蒸馏值,与 monitor 同款真值,自洽)。**遗留**:非完整 LangGraph(单轮函数,遵 memory.py 先例)、非流式、不升 V3(作者拍板对话全 deepseek-v4-flash)
- [~] `frontend/`:**对话页落地(2026-06-08)**——FastAPI 网关 + Jinja2/HTMX 单页(聊天 + 录音 Web Speech STT + 浏览器 TTS)+ 级联语音 mock(`voice/provider.py`,STT→文本 LLM→TTS,零 key)。**遗留**:运维面板(看 incident、审批 Tier3)
- [ ] `sensing/hardware/`:RPi 传感器读取 + MQTT 发布
- [ ] `sensing/ingest/`:MQTT→InfluxDB;`mcp-sensor-server` 从直读模拟器切到 InfluxDB(真实/模拟可切换)
- [~] `ops/deployment/`:**问答管家两 systemd 模板落地**(`ieq-web`/`ieq-sampler`,2026-06-08)。**遗留**:incident 5 分钟监控 cron + 周日反思 cron
- [ ] 稳定化:72 小时无人值守 dry-run,修崩溃/泄漏

**验收:** 真实传感器数据驱动一个真实 incident 端到端关单;面板能审批 Tier3;systemd 重启后自恢复。

**📍 进度(2026-06-08 session):** **问答优先 MVP 落地并端到端实测**(作者拍板暂搁论文、先做可部署成品)。新增:`sensing/history.py`+`sensor_readings` 表(采样器写、统计读)、`ops/sampler.py`(APScheduler 轻量采样,**不跑 incident graph**)、ticket `list_incidents`、semantic `list_facts`(Qdrant scroll 全量、**免 embedding key**)、`agents/conversational.py`(两步式:`conversational.dispatch` flash 出 `RetrievalPlan`→按需取数→`conversational.respond` flash 合成;router 加 `conversational.dispatch`=FAST;失败退化拉核心源)、`voice/provider.py`(级联 mock)、`frontend/`(FastAPI+HTMX+Web Speech)。两 prompt 版本化(`conversational/{dispatch,respond}/v1`)。**实测**:ruff+mypy clean;数据层采样+`query_stats` 正确;5 类问题端到端真 LLM 通过,**按需取数核验通过**(A/A+ sources=[]、B=['stats']、C=['incidents']、E 拒答);web `/` 200 + `/api/sensors/current` JSON。**范围/取舍**:免 RAG(范围判定靠 thresholds)、对话全 flash、语音 mock(浏览器 Web Speech)、**RPi 友好**(零本地模型/无 torch)。**本期不做**(留后):incident 5min 常驻调度 + 进度面板、embedding 远端化、真语音 API、真硬件、72h dry-run。详见 DEVLOG P-017。

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
