# EXECUTION_PLAN.md

IEQ-Ops 的权威实施进度清单。`CLAUDE.md` 引用本文件作为分阶段任务来源。

**约定:** `[ ]` 未开始 · `[~]` 进行中 · `[x]` 完成。每个 Phase 以其 **验收 gate** 作为推进门槛,不达标不进下一阶段。窗口是目标、可调;但 Phase 6 的 8 周和 ~09-12 的代码冻结点受论文证据保护,不能被开发拖延吃掉。

起算日:2026-05-25 · 提交:2026-12。

---

## 当前进度快照（截至 2026-06-08）

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

> **🆕 2026-06-08(续·对话多轮+流式 + 硬件方案定稿):** ① **对话多轮 + 流式落地并提交**(commit `1ebadd8`)——history 由**前端持有**、后端无状态(免 session、滑窗 6),dispatch+respond 都吃历史(裸追问 "what about humidity?" 实测接住上轮、答湿度);`core/router.py::stream()` 流式吐 token(fallback 仅未吐字前切换;语音保留非流式),prompt bump **v2** + 对话**全英文**;真 LLM 实测流式 33 块 / 首 token 1.9s,ruff+mypy(core 严格)全绿(DEVLOG **P-018**)。② **真实硬件接入方案定稿**(未写码)——demo 只摆 **RPi+触摸屏**,**Arduino MKR WiFi 1010** 传感器节点经 WiFi/MQTT → RPi Mosquitto → **Postgres `sensor_readings`**(**弃 InfluxDB**,当前量级过度工程);切入点是换 `read_sensors` body(`SENSOR_SOURCE=sim|hardware` 并存),上层 multi-agent 零改;麦克风留 RPi。详见 Phase 5「硬件接入方案」+ memory `project_hardware_deployment`。

> **🆕 2026-06-08(续·三域 thresholds 纵向对齐 P-019):** 补完 P-016「下次接」清单——thermal/lighting/acoustic 三域占位阈值对齐到真 WELL corpus,走完 P-014 的 **corpus→monitor→planner→generate→bench** 纵向链。**取证先行推翻一个二手说法**:P-016 快照「EN 12464 不在库」**不准确**(corpus 5 个参考指南都列了,真问题是 lighting 数值 300→**320 lux**);thermal **19-26→21-25 °C**、acoustic **55→50 dBA**(占位比 WELL 最低合规线还松)。**实跑三域 demo 实证链环④**:generate 全部 grounded 到真值——lighting "320 lux per **CIBSE SLL**(excerpt 1)"、thermal "21-25 + **ASHRAE 55-2013**(excerpt 2)"、acoustic "**50 dBA Cat3**(excerpt 5)",无假归因。**bench 迁移含三裁断**:l1 gold→`well-v2`(诚实标注单 source 退化为烟雾测试)、`l2_critic`/`l2_rewrite` 故意不动(封闭单元/单source失效)、`hardwell` 800-WELL 负控放过。**新暴露(待跟进)**:acoustic critic 否决 `target_time_min=15` 不现实(降噪非 15min 可达,与阈值无关)。ruff+mypy(strict core)全绿。详见 DEVLOG P-019。

> **🆕 2026-06-08(续·critic 否决在人工域升级请人 P-020):** 承接 P-019 acoustic 发现 + v5 prompt 回滚(masking/风扇是「改善感知不改数值」型,critic 正确否决但 acoustic 卡死 FAILED)。作者拍板「声学只报 incident 然后请人介入」。**核心洞察**:critic 否决=「别自动执行」——对有 actuator 的域(Tier1/2)否决=FAILED 合理,对**无 actuator、必然人工**的域(Tier3)否决=系统做不到=**正该请人**,不该当失败。**实现**:`tier_for_sensor()` 移 `core/state.py`(critic 不能 import graph)、`_route_after_critic` 让 Tier3 否决→`autonomy_gate`、`critic._disapprove` 新增(Tier3→`AWAITING_APPROVAL` 不 FAILED)、interrupt payload 带 critic `concerns` 给人研判。**critic 判断标准一字未动**(没放松),只改否决后的去向。**实测**:acoustic→`critic_escalate_human`→`awaiting_approval`→Tier3 interrupt(带 masking 顾虑),**不再 FAILED**;thermal approved→Tier3(concerns=[],回归 OK)。复用现成 `AWAITING_APPROVAL`+interrupt,不动 schema、不绕 autonomy_gate。详见 DEVLOG P-020。

> **🆕 2026-06-09(Phase 5·真语音级联落地 P-021,接力计划 `5-agent-mrk1010-...-lamport.md`):** 作者敲定下一阶段三件事(顺序 **3→2→1**:WSL 真语音 → MKR1010 真数据 → 部署 Pi),并先开工**语音**。把语音从浏览器 mock 升级到**阿里云百炼真云级联**:TTS=**Qwen3-TTS-Flash realtime `qwen3-tts-flash-realtime`**(**新加坡 endpoint**,作者实测比北京快 ~5s;音色 `Jennifer`/詹妮弗 + 英文)、STT=`paraformer-realtime-v2`,**butler 全英文**(新增 memory 约束)。**低延迟设计**:`respond_stream` token 边吐边灌 Qwen3-TTS realtime WS(`append_text`),音频帧边回边播,出声延迟≈STT+LLM 首句+TTS 首包(非各段相加)。**实现**:DashScope 回调推送用 `queue+线程` 桥成 `synthesize_stream` 拉取迭代器;`/api/voice/stream` 用 `_tee`+NDJSON 一条流复用 `{query|token|audio|done}`;前端 `PcmPlayer`(Web Audio gapless 播 24k PCM)+`WavRecorder`(自编 16k WAV 给云 STT);无 key 退回 mock。**mock 链路 TestClient E2E 验通**(query1+token31+done,grounded 英文),ruff+mypy(strict core)全绿。**待跟进**:真 CosyVoice 音频段卡 `DASHSCOPE_API_KEY`(`ops/scripts/voice_smoke.py` 填 key 即验+量首包)、英文音色待挑、STT 二期流式、WS 预热。详见 DEVLOG P-021。**部署拓扑结论**(Pi 无 GPU):Pi 跑轻路径(5min 监测扫描+建单+Q&A+采样,皆不吃 GPU/torch),完整 Specialist RAG 闭环留开发机(RTX3060)——见计划「延后决策 A/B/C」。

> **🆕 2026-06-09(续·butler 输出修整 + 长期运行加固 #1/#2/#9/#10):** 浏览器实测后修两处 butler 体验,并排查两个长期常驻功能(5min 监控扫描 + 对话)的工程缺口、按作者指定顺序补 4 项上线前必修。**butler**:① respond prompt **bump v3**——禁所有 markdown(TTS 不再念 `*` 星号)+ 数字口语化 + 每答简短、列表(incident/facts)只说最相关一条 +「还有其他」不逐条念;前端 `speak()` 加 `stripMarkdown` 兜底。② `list_facts` 从「全量 scroll 倒进 prompt」改 **取最近 5 条**(按 created_at,纯 scroll、**不引 embedding**,作者拍板)——上下文随 facts 增长不爆。**长期运行加固**(列 13 项问题,补 4 个必修):**#1 建单去重**(`monitor` 查 `active_incident_for_sensor`,已有未关闭单则 suppress 不重复建,route 改判 `incident_id`;实测 temp=29 异常被 suppress、不刷单)· **#2 常驻 resume 调度**(新 `ops/scheduler.py` APScheduler:scan 5min + resume 1min;新 `core/suspend.py` + `suspended_threads` 表**外部登记 thread↔incident、不碰 graph**;实测 scan_tick 走通)· **#10 checkpoint 清理**(原生 `delete_thread` 融入 scan 终态 / resume 完成,不堆积)· **#9 连接池**(新 `core/db.py` 进程级 `ConnectionPool` min1/max10 dict_row,四处 `_conn` 走池;mypy strict 过)。ruff+mypy(strict core)全绿。**部署注意**:scheduler 跑**开发机**(scan 可达 specialist RAG/GPU),Pi 只 sampler+web;resume 按**真实墙钟**不推进模拟器;scheduler 的 systemd 模板待。**未提交**(本 session 改动 + P-021 语音待一起整理)。详见 Phase 5 进度 + 待写 DEVLOG P-022。

> **🆕 2026-06-10(Phase 5·实物展台 Pi 部署启动 — 接力 3→2→1 的「1 部署」前置):** 作者拍板先交付**可展示实物**(暂搁论文证据线):Pi4 8GB 单机跑全栈 + Arduino MKR1010 传感器节点 + 触摸屏 kiosk + 现场问答。**硬件定型**:SCD-30(CO2+温湿,一颗覆盖 air+thermal)+ Grove Light v1.1 / Sound v1.6(模拟值,非真 lux/dBA,作者接受)→ MKR1010(有 ADC 正好读模拟)→ WiFi/MQTT → Pi。**关键决策**:诊断 RAG 检索跑 **Pi CPU**(闭环偶尔触发、10s+ 可接受;唯一本地算力需求,LLM 全云)、OS **Lite 64-bit**、PG/Qdrant **原生装不用 Docker**、异常**真实+可注入**并存。**Pi bring-up 进展(本 session)**:连接打通(路由器**客户端隔离**→Windows portproxy 绕过→`ssh pi` 免密)、git/rsync/uv、代码+corpus+.env 同步、`uv sync --python 3.11`(.venv 3.11.15、**torch 2.6.0+cpu**,踩平 cu121→CPU + transformers 5.9.0/st 5.5.1 版本坑)、核心库 import 全通、**PostgreSQL 17** active。**待**:建 PG 库 + 装 Qdrant + ingest + **CPU spike(命门:量 BGE-M3+reranker 在 Pi CPU 的内存/速度)**。计划见 `.claude/plans/enchanted-questing-shore.md`,详见 DEVLOG **P-022**。

> **🆕 2026-06-14(Phase 5·Pi 展台阶段0 完成 — 单机方案命门排除):** 承接 P-022 env 就绪,跑完阶段0。**基础设施**:PG17 原生 `ieqops` 库+8表、Qdrant v1.18.2 aarch64 binary+systemd、ingest 824 chunks(CPU fp32,green)。**CPU 检索 spike(命门,新 `ops/scripts/pi_retrieve_spike.py`)**:① **内存过关**(完整 retrieve 峰值 3.8-4.0GiB 零 swap,8GB 足)② **速度是真问题**——单次 ~189s,分段定位 **99% 在 reranker**(每候选 ~6s 线性;max_length 杠杆无效=动态 padding 已省、线程已吃满)。**提速落地**:候选池可配 `RAG_RERANK_CANDIDATES`(默认30护评测/Pi=5),**candidate=5:189s→24.4s(7.7x)**,四域 top1 仍命中真值(airquality 略偏通风条款=reranker 退化为排序的代价)。**收口**:`IEQ_RAG_DEVICE` 从 `os.getenv` 收进 `core/config.py` Settings(`rag_device`,AliasChoices 兼容旧名),systemd 不再需 shell export。**端到端验证**:Pi `demo.py co2_spike` 两次关单(closed/met,记忆轨迹也写入),收口后纯靠 `.env` 走 cpu 仍关单。**Pi 单机跑诊断闭环成立。** 详见 DEVLOG **P-023** + memory `project_pi_cpu_retrieval`。**下一步**:阶段1 语音收尾 / 运维面板 / replan(纯软件,不等硬件)→ 屏+麦+喇叭到位真机联调 → Arduino 到货接真传感器。

**两条架构红线风险已坐实闭环:** ① 15min 跨重启恢复(Phase 1) ② 子图状态隔离(Phase 2)——全系统最大的两个技术不确定性已排除。

**🔜 下一步(Phase 4 续,优先级序):** ✅已清:P-009、grade/rewrite 入 runner、记忆消融 +1.00、自相矛盾陷阱(P-011)、ablate 条件验证(`--ablate-check`)、**真 corpus 切换回归(P-014,co2→WELL 900)**、**runner 并行化(P-015,3.3x + 修 reranker 并发不安全)**。**剩:** ① **GPT-4o 跨模型 baseline + GPT-4o/Claude 双裁判**(卡 key,去主场嫌疑)② ✅ **三 domain 真 corpus 已接入**(WELL v2 同一 PDF 的 Light/Thermal/Sound concept,824 chunks,弃付费 ASHRAE/EN/WHO,P-016)+ ✅ **三域 thresholds/bench 纵向对齐完成**(thermal 21-25/lighting 320/acoustic 50 dBA,实跑三域 generate 全 grounded 到 WELL 真值,P-019);剩可选 contextual 全量重 embed ③ 扩 200 + 判别性误导检索难题——**作者拍板等 Phase 5 真 PDF corpus**(强基座下简单任务无法判别,硬凑无意义,P-011)。"无数字不立论"的关口:架构价值现由**记忆消融 +1.00** 承载,≥10pp-vs-baseline 待真 corpus/GPT-4o。

**🔜 Phase 5 对话线(2026-06-08 起当前重心):** 问答管家 MVP ✅ → 多轮+流式 ✅(commit `1ebadd8`)→ 真语音级联 ✅(P-021)→ butler 输出修整 + 长期运行加固 ✅(2026-06-09)。**下一缺口:** ① RAG 标准条款问答(要标准原文/出处时)② 运维面板(看 incident / 审批 Tier3)③ 长期运行剩余加固(#3 审批超时 / #4 monitor 纯确定性 / #7 语音清理 / #8 web auth)+ scheduler/cron 的 systemd 模板。**硬件:** 按定稿方案落码(Arduino MKR 1010 固件 + `sensing/ingest` writer + `read_sensors` 的 sim/hardware 切换,两空目录待写)。

**📌 下次接力(2026-06-08 session 收尾 — 下次从这接):**
本 session 落地并提交三件:① **三域 thresholds 纵向对齐**(P-019,commit `41b098f`:thermal 21-25 / lighting 320 / acoustic 50 dBA 对齐真 WELL,bench 迁移,实跑三域 generate 全 grounded)② **critic 否决在人工域升级请人**(P-020,commit `8b04e47`:Tier3 无 actuator 域被否→escalate Tier3 interrupt 带 critic 顾虑,不再 FAILED;Tier1/2 仍 FAILED;critic 判断标准未动)③ **commit 全英文化**(11 个中文 commit 重写 + force push,「commit 纯英文」入 memory)。**期间发现并回滚 v5 generate prompt**(让 specialist 提「窗内可见效手段」反而引导 masking/风扇这类「改善感知不改数值」型手段,thermal 自洽退化,负 delta 不 merge)。**下次按优先级接:**
> 1. **[Phase 3 缺口·健壮性核心] 接 replan** —— critic 否决(Tier1/2)/ verifier missed 当前都是终态(END/FAILED),无「重新规划」。P-020 的 Tier3 escalate 是「无自主解→交人」,replan 是「方案被否→换思路重试」,两者互补。需配 `subtask_results` 重置。
> 2. **[Phase 5] acoustic 真闭环** —— 外部噪声只能 escalate 请人(已实现)。真降 dBA 需「关室内噪声源」:换室内源 demo 场景 + 记忆驱动诊断(无记忆泛泛 masking 被否、有记忆关室内风机通过 = 顺带展示 Week8>Week1 记忆价值)+ acoustic actuator。
> 3. **[Phase 4·可选] 三域 contextual** —— thermal/lighting/acoustic 的 574 chunks 是裸 chunk(无 contextual prefix),与 airquality 不对称;补做需 `--contextual` 全量重 embed 四域。
> 4. **[Phase 4] GPT-4o baseline + 双裁判**(卡 key)+ **扩 200 判别性误导检索难题**(真 corpus 已就位,P-011 等的就是它)。
> 5. **[dissertation discussion] 度量范式 limitation** —— 「数值度量 vs 感知型干预」:masking 不降 dBA、风扇不降干球温,系统闭环只认数值→认不了「改善感知」型正当手段(v5 实证,已回滚)。是真实约束,写进论文 discussion。
> 6. **[Phase 5] 其余** —— ✅ 真语音级联(P-021)· ✅ incident 常驻调度(`ops/scheduler.py`)· ✅ 长期运行加固 #1/#2/#9/#10(2026-06-09);**剩** 运维面板(看 incident + 审批 Tier3)/ 长期加固续(#3/#4/#7/#8)+ systemd 模板 / 硬件落码。

**剩余路线:** Phase 4 评测 → Phase 5 对话+前端+硬件+上线稳定化 →(代码冻结 ~09-12)→ Phase 6 自主长跑 ≥8 周(Week8>Week1) → Phase 7 论文 + IEQ-Bench 开源。

**距离 6 条成功标准的硬缺口**(全在 Phase 4–6 产出):尚无 IEQ-Bench 分数、无 baseline 对比、无真实硬件数据、无 ≥4 周自主运行、无 Week8 vs Week1 证据、无公开 HF 数据集。**当前定性:功能骨架就绪(0–3);论文实证开采——Phase 4 首个 delta(generate/v4)已落地,baseline 对照 / Week8 证据 / HF 数据集待续(4–6)。**

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

- [~] `ConversationalGraph`:**问答管家 MVP 落地(2026-06-08)**——`ConversationalAgent` 两步式(意图分类→按需取数→合成),收 thresholds/读数/stats/incident/facts/SOP;**免 RAG/embedding**(范围判定靠 thresholds=corpus 蒸馏值,与 monitor 同款真值,自洽)。**多轮 + 流式已落地(2026-06-08 续)**:history 由前端维护、每轮带上(后端无状态、滑窗最近 6 条),dispatch+respond 均吃历史(追问 "what about humidity?" 实测接住上轮、答湿度);`respond_stream` 流式吐 token(实测首 token ~2s、33 块),`respond` 保留非流式供语音级联;对话全英文。**遗留**:非完整 LangGraph(函数式,遵 memory.py 先例)、不升 V3(作者拍板对话全 deepseek-v4-flash)、RAG 标准条款问答留后。**2026-06-09**:respond bump **v3**(禁 markdown/纯口语、TTS 不念星号 + 每答简短 + 列表只说最相关一条);`list_facts` 改**取最近 5 条**(纯 scroll、不引 embedding)防上下文随 facts 膨胀
- [~] `frontend/`:**对话页落地(2026-06-08)**——FastAPI 网关 + Jinja2/HTMX 单页(聊天 + 录音 Web Speech STT + 浏览器 TTS)+ 级联语音 mock(`voice/provider.py`,STT→文本 LLM→TTS,零 key)。**多轮+流式(2026-06-08 续)**:`/api/chat` 改 `StreamingResponse`、前端 `ReadableStream` 边收边渲染;客户端持有 history、每轮带最近 6 条;STT/TTS + 界面改 en-US;加 "New conversation" 清空历史。**遗留**:运维面板(看 incident、审批 Tier3)、真语音 API + RPi kiosk Web Speech 验证
- [ ] **真实硬件接入(方案 2026-06-08 定稿,见下「硬件接入方案」)**:
  - [ ] **Arduino 固件**(MKR WiFi 1010,C++):SCD40(CO2,I2C `0x62`)+ BH1750(光照,I2C `0x23`)挂同一 I2C 总线 + DHT22(温湿,单总线)→ WiFiNINA + ArduinoMqttClient 发 JSON 到 MQTT topic(板为 3.3V 逻辑,三传感器天然匹配)
  - [ ] **RPi 网关**:装 Mosquitto broker;`sensing/ingest/` 新写 MQTT 订阅 writer(paho)→ `sensing.history.record_reading()` 写**现有 Postgres `sensor_readings` 表**(**弃 InfluxDB**,理由见下)
  - [ ] **`read_sensors` 切换**:`mcp-sensor-server.read_sensors` 加 `SENSOR_SOURCE=sim|hardware` env 开关——hardware 读 `sensor_readings` 最新行、sim 仍读模拟器(**两者并存**:demo 既展示真实感知、又靠注入场景演 incident 闭环);**工具名+输出形状不变 → 上层 multi-agent 零改动**(这是接入最干净的切入点)
  - [ ] **麦克风留 RPi**:USB mic + Python 端算响度(dB)并入同一帧(Arduino 算力不适合持续声学采样;acoustic thresholds 本就待 P-016 对齐,噪声这块暂粗)
- [~] `ops/deployment/`:**问答管家两 systemd 模板落地**(`ieq-web`/`ieq-sampler`,2026-06-08)。**2026-06-09:`ops/scheduler.py` 落地**——APScheduler 两 job:scan 5min(监控扫描+建单,已含去重)、resume 1min(复活到期挂起→verifier,终态 purge checkpoint);取代手动 `run_incident.py`、是系统心跳,**跑开发机**(scan 可达 specialist RAG)。**遗留**:scheduler / sampler / 周日反思的 systemd+cron 模板(scheduler 现可 `python -m ops.scheduler` 手动起)
- [~] 稳定化:**长期运行加固(2026-06-09,排查 13 项问题、补 4 项上线前必修)**——✅ #1 建单去重(持续异常不再每 5min 刷单)· ✅ #2 常驻 resume 调度(`scheduler.py` + `suspended_threads` 登记表,挂起必被复活)· ✅ #10 checkpoint 清理(`delete_thread`,不堆积)· ✅ #9 连接池(`core/db.py`,四处 `_conn` 走池)。**之后要做(按严重度)**:#3 Tier3 审批超时、#4 monitor 改纯确定性(省 ~8640 次/月云调用 + 合规硬约束 #1)、#6 incidents 也降量(同 facts)、#7 语音线程/WS 复用与断开清理、#8 web auth/限流、#5 云 API 故障韧性、#11 日志 rotation、#13 sim/真传感器异常密度(方法论)。**最后**:72 小时无人值守 dry-run,修崩溃/泄漏

**验收:** 真实传感器数据驱动一个真实 incident 端到端关单;面板能审批 Tier3;systemd 重启后自恢复。

**📍 进度(2026-06-08 session):** **问答优先 MVP 落地并端到端实测**(作者拍板暂搁论文、先做可部署成品)。新增:`sensing/history.py`+`sensor_readings` 表(采样器写、统计读)、`ops/sampler.py`(APScheduler 轻量采样,**不跑 incident graph**)、ticket `list_incidents`、semantic `list_facts`(Qdrant scroll 全量、**免 embedding key**)、`agents/conversational.py`(两步式:`conversational.dispatch` flash 出 `RetrievalPlan`→按需取数→`conversational.respond` flash 合成;router 加 `conversational.dispatch`=FAST;失败退化拉核心源)、`voice/provider.py`(级联 mock)、`frontend/`(FastAPI+HTMX+Web Speech)。两 prompt 版本化(`conversational/{dispatch,respond}/v1`)。**实测**:ruff+mypy clean;数据层采样+`query_stats` 正确;5 类问题端到端真 LLM 通过,**按需取数核验通过**(A/A+ sources=[]、B=['stats']、C=['incidents']、E 拒答);web `/` 200 + `/api/sensors/current` JSON。**范围/取舍**:免 RAG(范围判定靠 thresholds)、对话全 flash、语音 mock(浏览器 Web Speech)、**RPi 友好**(零本地模型/无 torch)。**本期不做**(留后):incident 5min 常驻调度 + 进度面板、embedding 远端化、真语音 API、真硬件、72h dry-run。详见 DEVLOG P-017。

**🔧 硬件接入方案(2026-06-08 定稿,作者拍板):**

- **目标场景**:答辩/demo 桌面只摆 **RPi 4 + 触摸屏**,传感器不直插 RPi GPIO,改用 **Arduino MKR WiFi 1010 当独立传感器节点**(板载 WiFi、3.3V,适配 I2C 传感器)经 WiFi/MQTT 上报——正是 `sensing/` 的设计本意(传感器节点 + 网关,而非 RPi 直插一堆线)。
- **数据流**:`Arduino(SCD40/BH1750/DHT22) ─WiFi/MQTT─▶ RPi Mosquitto ─▶ sensing/ingest writer ─▶ Postgres sensor_readings 表 ─▶ read_sensors(hardware 模式)`;麦克风走 USB 接 RPi、本地 Python 算 dB 并入同一帧。
- **切入点(最干净处)**:全系统读传感器只经 `mcp-sensor-server.read_sensors`(返回 `dict[str,float]`),换它的 body 即可,monitor/verifier/sampler/问答管家**全部零改**;`SENSOR_SOURCE=sim|hardware` 切换,两源并存(真实感知 + 注入场景演闭环,缺一不可)。
- **决策:弃 InfluxDB,复用 Postgres `sensor_readings`**(推翻 CLAUDE.md 原 InfluxDB 计划——属「具体工具选型」,TECH_STACK 优先;`read_sensors`/`sensor_readings` 注释本就留 "Phase 5 *can* move to InfluxDB" 余地,未锁死)。**理由**:采样 5min/次(demo 10s)→ 跑满 8 周也就几十万行,对 Postgres 是毛毛雨,InfluxDB 的高频压缩/降采样/retention 优势**这个量级用不上**;RPi 资源紧、Postgres 已在跑、问答管家已读该表 → Arduino 真数据一进表当场被问答管家用上。InfluxDB 留作「真到大数据量再说」(或上 TimescaleDB 给 Postgres 加时序,不另起库)。

**📍 进度(2026-06-08 续·对话多轮+流式):** 把问答管家从单轮无状态升级为**多轮 + 流式**(作者拍板英文对话)。① **多轮**:history 由**前端持有**、每轮随请求带上(后端无状态、免 session 管理、多 worker 不怕),后端滑窗截最近 6 条;**dispatch 与 respond 都吃历史**(指代/追问才解析得了)。prompt bump v2(system 指令风格 + 多轮说明 + 全英文)。② **流式**:`core/router.py` 加 `stream()`(fallback 只在**未吐字前**切换,中途失败不重试以免重复输出);`/api/chat` 改 `StreamingResponse` 吐纯文本 token,前端 `ReadableStream` 边收边渲染;语音路径保留**非流式**(浏览器 TTS 要完整文本)。③ **实测**(真 LLM,Postgres/Qdrant 起):"is the temperature ok?"→sources=[]、流式 33 块、首 token 1.9s、答 22.5℃∈19-26;裸追问 "what about humidity?"→turns=1、接住上轮、答 45%RH∈30-60。ruff + mypy(core 严格)全绿。详见 DEVLOG P-018。

**📍 进度(2026-06-09 续·butler 输出修整 + 长期运行加固):** 浏览器实测问答管家后定两项 butler 修整 + 补长期无人值守工程缺口,详见快照 🆕 2026-06-09(续)。**改动文件**:butler——`ops/prompts/conversational/respond/v3.md`(禁 markdown+简短+列表概括)、`frontend/app/index.html`(`stripMarkdown` 兜底)、`memory/semantic.py`(`list_facts` 最近 5 条)+`agents/conversational.py`(传 `limit=5`);加固——`agents/monitor.py`+`mcp_servers/ticket/server.py`(`active_incident_for_sensor` 工具 + `suspended_threads` DDL)+`core/graph.py`(route 改判 `incident_id`)、新 `core/suspend.py`+`ops/scheduler.py`、新 `core/db.py`(连接池)+`sensing/history.py`/`memory/procedural.py`(走池)。**实测**:ruff+mypy(strict core)全绿;scan_tick 去重→END→purge、登记表 due/discard、`delete_thread` 均通过。**待**:写 DEVLOG P-022、整理提交(连同 P-021 语音)、scheduler 的 systemd 模板。

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
