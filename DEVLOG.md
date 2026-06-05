# DEVLOG — 开发问题与踩坑复盘

开发过程中遇到的**问题**的专项记录:现象 → 根因 → 解决(或状态)→ 教训。供作者日后复盘项目、答辩举证、求职讲故事用。

**与其他文档的分工:**
- `EXECUTION_PLAN.md` 记**进度**(做了什么、到哪个 Phase)。
- 本文件记**问题**(踩了什么坑、为什么、怎么爬出来的、学到什么)。
- 二者互补:进度是「正面叙事」,本文件是「失败与修正的证据链」——后者往往才是复盘和面试时最有价值的部分。

---

## 记录约定

- 一条问题一个条目,编号 `P-001` 递增,**正序追加在末尾**(最新在底部)。
- 状态图例:✅ 已解决 · 🔧 进行中 · ⏳ 待处理。
- 未解决的(🔧/⏳)同时登记到下面的「未决速查」,复盘时一眼可见。
- 模板:

  ```
  ### P-0XX · <Phase> · <一句话标题>  <状态 emoji>
  - **现象**:观察到的异常表现。
  - **根因**:为什么会这样。
  - **解决** / **状态**:怎么修的;未修则写计划。
  - **教训**:下次怎么避免 / 可复用的原则。
  - **关联**:file:line · commit · memory · bench 任务。
  ```

---

## 未决速查

| 编号 | 状态 | 标题 |
|---|---|---|
| P-009 | ⏳ 待处理 | verifier 取 subtask_result 与 action 选取逻辑不一致 |
| P-010 | ⏳ 待处理 | e2e 对照 +10pp 全靠 acoustic 单域(简单任务封顶,≥10pp 未稳) |

> P-008 已于 2026-05-31 解决(generate/v4),见下。

---

## 问题记录

### P-001 · Phase 0 · 6GB 显存三方共驻不可行 + retrieve 跑 CPU 爆预算  ✅
- **现象**:计划让本地 Qwen3-8B + RAG retrieve + reranker 三方共驻一张 6GB 卡;沿用 `douluo` 旧项目经验把 retrieve 放 CPU。
- **根因**:`vram_spike.py` 实测——Qwen 单独就吃 5.6GB(已 CPU offload 2.1GB),三方共驻不可行;CPU retrieve 实测 3.76s,爆 <500ms 预算 **7.5x**。
- **解决**:dev 期 GPU 只跑 retrieve(4.0GB,fp16 98ms);Qwen 单独占卡;Phase 6 用 ollama `keep_alive` 分时复用。推翻 douluo 的 CPU 策略,定稿写入 `TECH_STACK.md`。
- **教训**:跨项目搬经验必须在**目标硬件**上实测;延迟/显存预算要用数字卡死,不能凭直觉。
- **关联**:`ops/scripts/vram_spike.py` · `TECH_STACK.md` · memory `project_vram_strategy`

### P-002 · Phase 2 · BGE-M3 safetensors 离线缓存坑  ✅
- **现象**:offline 模式加载 `bge-m3` 直接报错。
- **根因**:safetensors 权重需先在线下载预热到 HF 缓存,之后才能 offline 加载。
- **解决**:首次在线 warm cache,之后可离线;加载方式对齐 `vram_spike`(SentenceTransformer + safetensors / 手写 transformers reranker),而非 douluo 的 CPU/CrossEncoder。
- **教训**:HF 模型要 offline 部署,先在线预热缓存是前置步骤,别在断网环境第一次拉权重。
- **关联**:`rag/retrieve.py` · memory `project_phase2_retrieval`

### P-003 · Phase 2 · v4 reasoning 模型偶发返回空 content  ✅
- **现象**:Specialist 子图 `decompose/grade/generate` 偶发无端失败,响应体为空。
- **根因**:v4 reasoning 模型把 token 预算全花在 `reasoning_content`,偶发返回空的 `message.content`。
- **解决**:子图四节点加 `extra_body={"thinking":{"type":"disabled"}}`(它们是 JSON/短串结构化任务,非推理深度任务);温度固定(decompose/grade=0、generate=0.2、rewrite=0.3)。延迟 ~11s→~3s,判断可复现。Planner **保留** thinking(DAG 分解确实需要推理)。
- **教训**:reasoning 模型用于「结构化输出」节点要显式关 thinking;否则空响应 + 不可复现 + 高延迟三连。是否开 thinking 应按**节点任务性质**决定,不是一刀切。
- **关联**:`agents/specialists/builder.py:55` `_NO_THINK`

### P-004 · Phase 2 · Send 并行 fan-out 写父 state 冲突  ✅
- **现象**:波次并行 fan-out 多个 specialist 同时写父 state,LangGraph 抛并发更新错误。
- **根因**:多分支并发写同一个**非 reducer** channel,LangGraph 直接拒绝。
- **解决**:`subtask_results` 配 merge reducer(`_merge_results`)、`failed_subtasks` 配 add reducer(`operator.add`);`status` 不在并行分支里写,留到 critic 之后统一写。
- **教训**:LangGraph 里凡是会被并行分支写的 channel,必须配 reducer;并发写裸 channel = 报错。
- **关联**:`core/state.py:44` `_merge_results` · `agents/specialists/builder.py` `run_specialist`

### P-005 · Phase 2 · generate 跨节点契约(1):正文阈值 ≠ target_value  ✅
- **现象**:CriticAgent 上线后,co2 关单率从 ~3/3 掉到 ~1/3。
- **根因**:generate 正文说"通风到 below 800ppm",但 `expected_outcome.target_value` 填 900;Verifier 拿 `target_value` 核验 → 与正文不一致,critic 正当否决。
- **解决**:generate prompt bump **v2**,规则 4 强制「正文阈值 = `target_value`」(挑一个数,两处一致)。改后 critic approve → 关单 3/3。
- **教训**:LLM 同时产「自然语言」和「结构化数值」时,两者会各自漂移;prompt 必须把它们**锚定到同一个数**。
- **关联**:`ops/prompts/specialist/generate/v2.md` · commit `af4abb9`

### P-006 · Phase 2 · generate 跨节点契约(2):target_metric 用了自然语言名  ✅
- **现象**:demo 四 domain 实跑,lighting/acoustic 的 generate 把 `target_metric` 写成 `illuminance`/`noise level` → critic 正当否决 + verifier `KeyError` 隐患。
- **根因**:critic 查物理范围表、verifier 查 `read_sensors` 都按 metric **键名**索引;自然语言名不是合法键。
- **解决**:bump **v3**,规则 5 强制 `target_metric ∈ {co2,temperature,humidity,lux,noise_db}`。
- **教训**:任何「跨节点当 dict 键用」的字段都要锁定枚举,绝不能让 LLM 自由命名。
- **关联**:`ops/prompts/specialist/generate/v3.md` · `core/state.py` `SENSOR_DOMAIN` · commit `30f5a75`

### P-007 · Phase 2 · ReWOO 占位符 hydrate 因花括号漂移断裂  ✅
- **现象**:依赖型子任务(S2 `depends_on` S1)拿不到上游诊断,空跑 rewrite×3;ReWOO 依赖传递实际断裂。
- **根因**:planner LLM 偶发照抄元符号 `#{subtask_id}`,产出带花括号的 `#{S1}.diagnosis`;原正则 `#(\w+)\.` 不认这个变体。
- **解决**:放宽正则为 `#\{?(\w+)\}?\.`,容忍花括号漂移;重测 S2 占位符正确填入 S1 真诊断。
- **教训**:依赖 LLM 严格遵守符号格式不可靠;**解析端**要主动容忍常见漂移(防御式正则),比靠 prompt 纪律便宜也安全。
- **关联**:`core/graph.py:91` `_REWOO_REF` · commit `30f5a75`

### P-008 · Phase 4 · generate co2 自洽 flaky  ✅
- **现象**:co2 generate 多次采样,critic 稳定否决约 30%(2026-05-31 `--n20` baseline:自洽率 0.70、否决率 30%;05-30 手测一度 62–67%——**高方差**指标);thermal 对照 0.95–1.0。
- **根因**:非零温度(0.2)下,generate 偶发在正文多嘴**预测「干预后会降到多少」**——复述 corpus `ops-note` 的"降 150–300ppm",从 1300 起降只到 1000–1150,与自己声明的 `target_value=800` 矛盾 → critic 正当否决。**纯自洽矛盾**,`mean_hit=1.0`(groundedness 无问题)。v3 规则 4 只管「正文阈值 = target_value」,没堵住「额外的降幅预测」这个口子。
- **解决**:bump `generate/v4` 加**规则 6**——禁止正文预测降幅/到达值(`will drop by` / `will settle around`),只承诺单一 `target_value`,降多少交给 Verifier;同时明确**保留**引用标准阈值的权利(护 groundedness)。builder 指向 v4。**delta(`--n20` 同环境):co2 自洽率 0.70→1.00(否决率 30%→0%)· mean_hit 1.0→1.0(未伤 groundedness)· thermal 0.95→1.0(未误伤对照)**;+0.30 远超 `--n20` 噪声 ±0.07。
- **教训**:即使 prompt 已要求「自洽」(v3 规则 4),非零温度下 LLM 仍会「多嘴」引入矛盾数字;约束要**具体到禁止某类输出**(禁止预测降幅),而非泛泛说「保持一致」。另:修 prompt 必须 before/after **同环境同 `--n`** 量化——高方差指标尤甚,4 天前的数字不可直接当对照。
- **关联**:bench `L2-generate-co2-flaky` · `ops/prompts/specialist/generate/v4.md` 规则 6 · `agents/specialists/builder.py` 指向 v4

### P-009 · Phase 2 · verifier 取 subtask_result 与 action 选取逻辑不一致  ✅
- **现象**:(潜在,尚未触发)`verifier.py:44` 用 `next(iter(state.subtask_results.values()))` 取**第一个**子任务结果,而 `action`/`autonomy_gate` 用 `state.primary_result()`(domain 匹配异常 sensor 的那个)。
- **根因**:单子任务 co2 场景两者恰好相同,所以一直没暴露;但多子任务 DAG 且 dict 里第一个不是 primary 时,verifier 会去核验一个 advisory 子任务的指标。
- **解决**:✅(2026-05-31)verifier 改用 `state.primary_result()`,与 `action`/`autonomy_gate` 同源;None 时返回 FAILED(与那两个节点一致),不再 `next(iter())`。
- **教训**:同一个「主结果」的选取逻辑应集中一处(`primary_result()`),各节点共用,避免各取各的埋下不一致。
- **关联**:`agents/verifier.py` `run()` · `core/state.py` `primary_result()` · commit `ffeeca0`

### P-010 · Phase 4 · e2e 对照表机制跑通,但 +10pp 全靠 acoustic 单域撑(简单任务封顶)  ⏳
- **现象**:`--compare` 四域 e2e(同一 anomaly,系统 `planner`+AgenticRAG vs 朴素 ReAct,同一 `CriticAgent`+groundedness hit 裁判),`--n5`:系统 **1.00** / baseline **0.90**,macro **+10.0pp** 恰好达标。但 co2/thermal/lighting 两臂**全 1.00**,gap **全部来自 acoustic**(baseline 0.60,5 次里 2 次被 critic 正当否决,非 no_finish)。
- **根因**:单点**突发跳变**任务对 deepseek-v4-flash 基座太简单,朴素 ReAct 也能做对 → 架构优势(规划 DAG / Agentic RAG / 记忆)被任务难度**封顶**,对照趋同;acoustic `n=5` 的置信区间又宽(0.6±~0.44),这个 +10pp **易碎**,不是稳健结论。
- **(顺带)公平性修正**:baseline 跑前用 `arm(scenario)` 把模拟器读数对齐到 anomaly——否则 baseline `read_sensors` 读到 in-band 默认值、与自己 prompt 里声明的异常矛盾,会被**不公平地坑**(系统臂直接吃 anomaly、不读传感器)。那是噪声,不是架构差,必须消除才能归因干净。
- **状态**:⏳ 机制 + 公平性已坐实(这部分 ✅),但 ≥10pp 的**稳健**证据未立。下一步:扩 200 任务时**刻意塞判别性难任务**(多步规划 / 跨域副作用 / 复发 pattern 靠 memory / 误导性检索),而非堆更多简单单跳变;再换 GPT-4o 跨模型 baseline + GPT-4o+Claude 双裁判,去掉「自家 critic 当裁判」的主场嫌疑。
- **教训**:baseline 对照的**任务难度**决定信号强弱——基座够强时,简单任务上架构会趋同;要证架构价值,benchmark 必须含「基座单跑会栽、而规划/记忆/RAG 能救」的任务。看到「达标 ✓」先问**靠什么撑**:单域撑起的 macro 均值不能当结论。
- **关联**:`eval/runner.py` `Runner.compare`/`_print_compare_table` · `eval/ieq_bench/tasks/l3_e2e.jsonl` · `eval/reports/compare-20260531T150318Z.json` · EXECUTION_PLAN Phase 4「扩到 200」

### P-011 · Phase 4 · 自相矛盾陷阱实测不咬:强基座裸跑简单任务 ✅(负面结论)
- **现象**:为做 P-010 要的判别性难题,设计「自相矛盾陷阱」——高值 CO2(1600→≤1000、1500→≤800),赌 naive ReAct 会把 corpus ops-note 的「降 150-300ppm」复述进诊断正文、与自己的 target 矛盾、被 critic 正当否决。`--compare --only hard --n5` 实测:**两臂全 1.00 打平**,gap 0。
- **根因**:deepseek-v4-flash 基座**太强**。单跑 baseline 看输出:诊断「set ventilation to high... reduce CO2」、target=800/30min、**不复述任何降幅**,完全自洽。陷阱要 baseline「傻到复述」,但强基座不会。之前 generate flaky 是 SYSTEM 侧 temp>0 的随机现象(30%),不是 baseline 在 temp=0.2 下的稳定失败模式。
- **解决**:接受负面结论,不硬凑。两个 hard 任务**重标为 negative control**(证据:强基座能裸跑高值 CO2)。≥10pp-vs-ReAct 这条线**诚实判定:当前强基座 + 当前可做的简单任务上立不住**。作者拍板:误导性检索难题留 Phase 5 真 PDF corpus 落地后做(那时 ReAct 一次检索会中招、系统 grade/rewrite 能救),现在不勉强。
- **教训**:**对照实验里别把 baseline 想得太弱**。强基座会让「诱导 baseline 犯错」类陷阱失效——能拉开差距的是**结构性缺陷**(无记忆 / 无多步规划 / 无检索反思),不是「框得更难一点」。判别力来自 baseline **结构上做不到**的事(记忆消融 P-012),而非基座**偶尔会犯**的错。负面结论也是结论,如实记。
- **关联**:`eval/ieq_bench/tasks/l3_e2e_hard.jsonl`(negative control) · `eval/reports/compare-20260531T225509Z.json` · 引出 P-012 记忆消融

### P-012 · Phase 4 · 记忆消融:v3 prompt 对 resolved 案例「碰而不用」 ✅
- **现象**:新增 `--ablate-memory`(同 planner,召回 ON/OFF,看建筑特定知识有没有进 plan goal)。v3 首跑 4 任务只 1 个命中(macro lift **+0.25**):co2-damper(FAILED 案例)命中,thermal-solar / acoustic-fan / co2-allhands(resolved 案例)全没进 goal。
- **根因**:planner v3 的「用相似案例」段——对 **FAILED** 案例说「prefer a different angle」,逼 planner 点名坏路径(damper 因此进 goal);但对 **resolved** 案例只说「let it inform how you frame」,太弱,planner 把它当信心背书、goal 仍泛泛(solar/fan/all-hands 都没带出来)。记忆里的建筑特定原因没流进规划。
- **解决**:bump `planner/v4` 加规则「CARRY THE BUILDING'S SPECIFICS FORWARD」——召回案例(resolved 或 failed)若点出 anomaly 本身推不出的建筑特定原因/修法(卡死风阀 / 西晒 / 风机不平衡 / 固定时段超员),**必须在主 goal 里点名**;同时保留冷启动「(none)→ 别编造」护栏。**delta:macro lift +0.25→+0.75**(同环境)。第 4 个 acoustic 实际也带出了「HVAC supply fan for imbalance」,只是 gold 词 `rebalanc/unbalanc` 太死没匹配到「imbalance」→ 修 gold 为 `fan/imbalanc/...`(离线核对 off 不含 on 含,非造假)→ **+1.00**。L2-planner 种子 4/4 无冷启动回归。
- **教训**:① 记忆的价值是**消融轴**(同系统 on/off),不是 system-vs-ReAct——ReAct 无 planner 无记忆,拿它比会把架构和记忆混在一起。② prompt 里「参考一下」(advisory)和「点名写进输出」(imperative)效果天差地别;要某信息出现在产物里,必须**祈使**,不能「软建议」。③ gold 词要忠于模型**实际措辞**的变体,先看输出再定 gold(但只在确认 off 不含时放宽,不对着答案造假)。
- **关联**:`ops/prompts/planner/v4.md` · `agents/planner.py` `plan_with_recall` · `eval/runner.py` `ablate_memory` · `eval/ieq_bench/tasks/l3_recurrence.jsonl` · `eval/reports/ablate-memory-20260531T223417Z.json` · commit `207f2e6`

### P-013 · Phase 4 · 真 PDF corpus 接入(WELL v2 Air):知识形状变了 + pypdf 双层重复 + contextual prefix 上线  ✅
- **现象**:把 airquality 从手写占位(`sample_corpus` 12 段)换成真 WELL v2 PDF(IWBI 官方 CDN,366 页,取 Air concept p11-46)。三件事冒出来:① 真 corpus 的"知识形状"和占位**不一样**——占位假设核心是「CO2>1000ppm→加通风」,真 WELL Air 重点其实是 **PM2.5/PM10 阈值 + ventilation design + 过滤等级(MERV)**,CO2 真实阈值是 **500/750 ppm above outdoor**(A01),根本不是占位的 1000ppm;② pypdf `extract_text` 把标题/标签行**双输出**(行级:`Intent:\nIntent:`、`A01 AIR QUALITY | P` ×2);③ ingest 一直缺 node #10 contextual prefix。
- **根因**:① 占位是"安全的改写值"、凭直觉编的阈值/重点,和标准原文有系统性偏差——这是 P-010/P-011「判别性缺口」的另一面:连知识本身都被占位简化了;② WELL PDF 用描边/双层渲染,pypdf 逐 span 抽出就重复;③ 历史 TODO。
- **解决**:① `ingest.py` 加 `--source auto|corpus|sample` + `corpus_manifest.json`(文件→source/domain/页范围映射,零原文可提交;PDF 本体 gitignored);**渐进替换**——真 PDF 覆盖的 domain 换真、未覆盖留 sample filler(airquality 换真,thermal/lighting/acoustic 仍占位,不破其他域);② `collapse_repeated_lines` 折叠相邻相同行(111021 chars → 257 chunks,正文行不受影响);③ contextual prefix 接 node #10——`make_contextual_prefix` 走 router `ingest.contextual_prefix`→FAST(**deepseek-v4-flash**),prompt 版本化 `ops/prompts/ingest/contextual_prefix/v1.md`(不内联,硬约束 #4),document 前置复用 DeepSeek prefix cache,并发 8,**只改 `embed_text` 不改返回 `text`**(prefix 是检索信号非答案材料,沿用 retrieve.py 既有设计),失败退化为 ""(249/250 applied,1 失败不中断)。**delta**:retrieve airquality 召回从占位假值改为命中真实条款——CO2 query → `500/750 ppm above outdoor`、PM2.5 query → `MERV 14/16` 过滤表(reranker score 4.35),`.text` 纯净无 prefix 泄漏。
- **教训**:① **占位 corpus 不只是"内容少",是"知识被直觉污染了"**——真 corpus 一进来,下游 generate 引用的标准、critic 的物理范围、甚至 monitor 阈值都可能要跟着改(CO2 1000ppm 这种"常识"未必是标准原文)。这才是 Phase 4 ≥10pp 判别性的真正素材:真 corpus 的多来源/条件阈值会让 naive 一次检索中招、grade/rewrite 能救(P-011 留的那条线)。② build-time LLM(contextual prefix)放 ingest、不放 `mcp-rag-server`(硬约束 #9 约束的是 server,不是 ingest);失败必须退化不中断。③ PDF 抽取的工程噪声(双层重复)要在入库前清,否则污染 BM25/embedding。
- **关联**:`rag/ingest.py`(`collapse_repeated_lines`/`make_contextual_prefix`/`apply_contextual_prefixes`/`select_passages`)· `rag/corpus_manifest.json` · `ops/prompts/ingest/contextual_prefix/v1.md` · `core/router.py` node #10 `ingest.contextual_prefix`→FAST · `rag/corpus/well-v2.pdf`(gitignored)· `ops/llm_routing.md` #10
