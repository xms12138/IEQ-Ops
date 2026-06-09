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
| P-014 | 🔧 部分延后 | airquality bench 种子按 WELL 重写(retrieval 0.60 + generate/e2e 硬编码 1000/ASHRAE),并入扩 200 |
| P-016 | 🔧 待对齐 | thermal/lighting/acoustic 真 corpus 已接入(WELL v2 三 concept,824 chunks);thresholds 占位 + 三域 bench 种子 + contextual 待下次对齐 |

> P-008 已于 2026-05-31 解决(generate/v4),P-014 阈值对齐已 ✅、bench 种子重写并入扩 200,均见下。

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

### P-014 · Phase 4 · 真 corpus 切换回归:monitor 的「ASHRAE 62.1 = 1000ppm」是占位误区,对齐到 WELL 900  ✅(bench 种子重写延后)
- **现象**:P-013 真 WELL corpus 接入后做切换回归(demo `co2_spike` + airquality bench 复跑),三层打架浮出:① **检索 bench 1.00→0.60**——`L1-retrieval-co2-001`(gold=`ashrae-62.1`)、`L1-retrieval-co2-ops-001`(gold=`ops-note`)的 gold source 是旧 `sample_corpus` 的标签,真库里只有 `well-v2`,必失败;② **monitor**:`thresholds.py` co2 rule 写「co2 ≤1000 ppm(ASHRAE 62.1 indoor air-quality guideline)」;③ **generate**:诊断输出「exceeds the ASHRAE 62.1 limit of 1000 ppm (excerpt 1) … reduce below 800 ppm」。
- **根因**:① **「ASHRAE 62.1 设 1000ppm CO2 上限」本身是广为流传的误区**——62.1 设的是通风换气率,从不设 1000ppm 的 CO2 健康上限(那条常被误传);真 WELL v2 A01 是 **900 ppm(1-point)/ 750 ppm(2-point)**,且「1000」在 WELL corpus 里 **0 命中**(`ASHRAE 62.1` 在 corpus 里 7 命中,但全是「通风率按 62.1 Natural Ventilation Procedure」,不是 CO2 上限)。② 这条假归因从 `thresholds.py` 的 `rule_violated` 串一路传进 monitor anomaly → planner subtask goal → generate,generate 就把 goal 的「1000/ASHRAE」当成「excerpt 1」引用了(典型的**占位知识污染下游归因**,正是 P-013 教训①预言的)。③ bench 种子在占位时代写死了 `ashrae-62.1`/`ops-note` 这些只存在于 `sample_corpus` 的 source 标签。
- **解决**:**作者拍板「触发线降到 900 对齐 WELL」**——`thresholds.py` co2 `high 1000→900`、rule 改「co2 must stay <= 900 ppm (WELL v2 Air, 1-point threshold)」,去掉 ASHRAE 假归因。连带排查:`RoomState.co2_ppm` 默认 650(动态稳态 ~720)均 < 900,非 co2 场景不会被新阈值误触发;critic 物理范围 `(350,5000)` 含 900/750 无打架;co2_spike(1300)仍触发、降到 679 仍 met。**复跑 demo `co2_spike` 实证对齐**:anomaly→「≤900 ppm」、goal→「against the 900 ppm threshold」、诊断→「exceeds the **900 ppm threshold specified in the WELL v2 standard (excerpt 1)**」(excerpt 1 真含该阈值,误归因消失)、`target_value=900`、critic approve、verifier met/closed。**bench 种子重写延后**(作者拍板 Q2):两个失效检索种子(`ashrae-62.1`/`ops-note` gold)+ generate/e2e 种子里硬编码的「1000/ASHRAE」anomaly 输入,统一留到 Phase 4「扩 200 判别性难题」时按 WELL 重写;短期 retrieval bench 维持 0.60(known-fail,非检索能力退化,是 gold 标签陈旧)。
- **教训**:① **占位阈值可能编码了一个「常识级误区」**——不是"数值不精确",是"把一个流行的错误说法当标准写进了系统真值";真 corpus 是照妖镜,一进来就把它逼出来。这比 P-013 的「知识形状不同」更尖锐:连 monitor 这种最底层的确定性规则都得跟着真标准改。② 切 corpus 不是只换 `rag/`,是一条 **corpus→monitor 阈值→planner goal→generate 引用→bench gold** 的纵向回归链,每一环都可能埋着旧占位的影子,必须端到端复跑才照得全。③ bench 的 gold 也是"占位资产",换真 corpus 后 gold 同样要迁移,否则绿表变红还以为是能力退化。
- **关联**:`sensing/thresholds.py` co2 行 · `agents/monitor.py`(`rules_text` 渲染)· `eval/ieq_bench/tasks/l1_retrieval.jsonl`(co2-001/co2-ops-001 known-fail,待 200 重写)· `eval/ieq_bench/tasks/{l2_generate,l3_e2e}.jsonl`(硬编码 1000/ASHRAE,待 200 重写)· P-013（真 corpus 接入,本条是其下游回归）

### P-015 · Phase 4 · runner 并行化:`_pmap` 暴露 reranker 并发不安全(transformers 5.9.0)+ seed 路径漏传 workers  ✅
- **现象**:给 `eval/runner.py` 加 `_pmap`(ThreadPoolExecutor)并行 generate/compare 的内层 sample 循环后,bench 一跑就崩:`RuntimeError: expected scalar type Half but found Float`(reranker `layer_norm`)+ 偶发 `ImportError: cannot import name 'AutoModelForSequenceClassification' from 'transformers'`。但**单次/顺序** retrieve 完全正常(直接 `RetrievalStack.retrieve` / 单 `call_tool` / 单 subgraph invoke 都 OK)。还发现 `--workers 1` 不生效:线程名探针显示样本跑在 `ThreadPoolExecutor-3_*`、`self.workers` 恒为 4。
- **根因**:① **transformers 5.9.0**(06-06 随 pypdf 接入连带 bump)下 bge-reranker **不是并发安全的**——多线程并发 forward 让 fp16 模型 dtype 状态错乱(Half/Float 混用),并发首次 `_get_stack` 又多线程同时触发 lazy import `AutoModelForSequenceClassification` 竞态拿到半初始化模块。改前 generate bench 是**顺序 for 循环、无并发**,所以一直没暴露;我的 `_pmap` 首次引入并发 retrieve 才点着这个雷。② `Runner` 构造在 seed/cap 路径(`main()` 末尾,原 line 743)**漏传 `workers=args.workers`**、一直用默认 4——`replace_all` 漏改的发散调用点,导致 `--workers` 在该路径被忽略(所有"workers=1"测试其实都在 4 路并发,误导排查良久)。
- **解决**:① `rag/retrieve.py` 加 `self._gpu_lock`,串行化 `_embed`+`_rerank_scores` 的 GPU forward(~50ms,远低于真正并行的 cloud-LLM 成本,代价可忽略);② `mcp_servers/rag/server.py` 的 `_get_stack` **双检锁**,并发首访只构造一次栈(import 单线程化);③ runner 加 `_warm_rag` 预热,线程 fan-out 前单线程把栈加载好;④ 补 seed 路径的 `workers=args.workers`。**验证**(同环境 `--n6` 同任务):workers=1 → decompose 间隔 ~17s 真顺序 / `WALL=162.7s`;workers=6 → decompose 0.24s 内并发 / `WALL=48.7s`,**3.3x 提速**,两者 consistency 全 1.00、零 dtype/import 错。
- **教训**:① **共享 GPU 模型单例不是自动线程安全的**——并行化调用方必须显式串行化 forward(锁)或每线程独立实例;这不只是 bench 的事,真实 `mcp-rag-server` 上线接并发 MCP 请求同样需要,属前瞻修复而非临时补丁。② transformers 5.x 把 `torch_dtype` 废弃为 `dtype`,并发下旧参数 dtype 处理更脆;锁顺带规避(顺序路径仍工作,故未强改加载参数,留最小改动面)。③ `replace_all` 会漏发散调用点(`Runner()` vs `Runner(n_samples=...)` vs 末尾那个无参版),改完务必 `grep "Runner("` 核对全部构造点。④ **工具坑自记**:`pkill -f "eval.runner"` 会连带杀掉命令行里含该串的当前 shell 自身;前台 `sleep` 被 harness 禁——排查期间两者各坑掉若干次 run,误判为代码问题。
- **关联**:`eval/runner.py`(`_pmap`/`_warm_rag`/`--workers`/seed 路径 `workers`)· `rag/retrieve.py`(`_gpu_lock`)· `mcp_servers/rag/server.py`(`_stack_lock` 双检)· transformers 5.9.0 · P-002(bge-m3 HF 在线检查拖慢加载,排查期每次 run 多付 ~25s)

### P-016 · Phase 4 · thermal/lighting/acoustic 真 corpus 一次性接入(WELL v2 同一 PDF 三 concept)+ 占位阈值待对齐  🔧(接入完成,下游对齐留下次)
- **现象/动作**:原计划 acoustic 用 WHO Noise、thermal/lighting 卡在付费 ASHRAE 55 / EN 12464。复盘发现**手上那份 airquality 用的 WELL v2 PDF(366pp)本就是 10-concept 全集**——Light / Thermal Comfort / Sound 三个 concept 都在同一份里,免费、零额外获取。作者据此拍板弃付费标准。pypdf 扫描定位全 10 concept overview 物理页(Air11 / Water47 / Nourishment72 / **Light103** / Movement130 / **Thermal160** / **Sound185** / Materials214 / Mind247 / Community274),`corpus_manifest.json` 加三条(同一 `well-v2.pdf`,靠 `pages`+domain filter 切片:lighting 103-129 / thermal 160-184 / acoustic 185-213),`ingest --source corpus`(**按作者指定三新域先不做 contextual**)→ **824 chunks**,四 domain 全真、sample 占位全退场。三域检索 sanity-check 各命中 WELL 真值。
- **根因(为何之前以为要找付费源)**:把"airquality corpus = WELL Air"记成了"WELL 只有 Air",忽略同一 PDF 已覆盖另三域;manifest 当初注释还特意写"p47 onward excluded 以免误标 airquality",强化了"其他域没资料"的错觉。其实只是当时按 domain 渐进接入、没回头看整本覆盖面。
- **检索证实的占位 vs WELL 真值差异(下次对齐素材)**:

  | domain | `thresholds.py` 占位 | WELL v2 真值(检索命中) |
  |---|---|---|
  | thermal | 19-26 °C | dry-bulb **21-25 °C**(≥90% 占用时段)+ 风速 ≤0.2 m/s + 上限 33.5 °C,引 **ASHRAE 55-2013** |
  | lighting | lux ≥300,来源标 **EN 12464-1** | 引的是 **CIBSE SLL Code for Lighting**(非 EN!);循环/储藏/餐饮区 **110 lux(10 fc)**;work area 按 task+age 分级(Option 2 predetermined) |
  | acoustic | ≤55 dBA(单值) | **分级 50/55/60 dBA**(Cat 1/2/3)+ dBC 70/75/80;**卧室 ≤35 dBA**(Leq 夜间 12h);5 min 均值 |

- **教训**:① **找新数据源前先把手上资料的覆盖面查全**——一份 WELL v2 省掉三处付费墙,差点白找 WHO/ASHRAE/EN。② **再次印证 P-013/P-014**:lighting 占位把来源标成 `EN 12464-1`,但真库里引的是 **CIBSE SLL** —— 又一个"占位引用了不在 corpus 里的标准"的雷(generate 会引 EN 但库里只有 WELL/CIBSE,同 P-014 的 ASHRAE-1000 同型),三域 thresholds 都得走 P-014 的 corpus→monitor→planner→generate→bench 纵向对齐链。③ 三新域**先不做 contextual**(embed_text=text),与 airquality(已接 #10)暂不对称;补做需 `--contextual` 全量重 embed 四域,留下次连同 thresholds 对齐一起。
- **下次接(清单)**:1) `thermal` 19-26→**21-25 °C**(WELL T01),去 ASHRAE 误标;2) `lighting` 来源 `EN 12464-1`→**CIBSE SLL/WELL**,用更精确 query 复核 work area 具体 lux 值;3) `acoustic` 单值 55→选 **WELL 档位(Cat)** 或加 dBA 分级;4) 三域 thresholds 改完跑 P-014 纵向链端到端复跑(demo + monitor rule + generate 引用);5) 三域各加 bench 种子(retrieval/generate/e2e);6) (可选)三域补 contextual 全量重 embed。
- **关联**:`rag/corpus_manifest.json`(+3 条)· `rag/ingest.py`(`--source corpus`,824 chunks)· `sensing/thresholds.py`(thermal/lux/noise_db 三行待对齐)· `rag/retrieve.py`(验证)· P-013/P-014(同型纵向对齐)· memory `project_corpus_source`

### P-017 · Phase 5 · 问答管家:从"全拉"修正为"意图分类按需取数" + 范围判定免 RAG  ✅
- **现象/动作**:做问答优先 MVP 的 `ConversationalAgent` 时,初版设计是"把所有廉价源(读数/历史/incident/facts/SOP)全拉进 LLM 一次合成"。作者两次质疑:① "不管问什么都把四个领域的历史全传给 LLM 吗?" ② "温度在正常范围内吗,要去调 RAG 了?"
- **根因**:① 全拉图省事,但违背 CLAUDE.md 写的 memory-first **dispatch**(本意就是按需取数);数据增长后(incident/facts 累积、读数序列上万行)token 爆 + 噪声干扰抓重点;对"现在温度多少"这种简单问题灌一周 incident 纯浪费。② 一度以为"判断是否正常"要查标准 corpus。
- **解决**:① 改**两步式**——一次轻量 flash 出 `RetrievalPlan`(need_stats/incidents/facts/sops + domain/sensor/since),**基线(read_sensors+thresholds)恒带、大源按计划选择性拉 + 领域过滤**;再一次 flash 合成。实测按需取数生效:"现在温度多少"/"温度正常吗" sources=[](只基线)、"过去24h CO2" sources=['stats']、"最近异常" sources=['incidents']。② **范围判定免 RAG**:"在不在范围/超标没/合不合格" = 当前读数 vs `thresholds.py`——它是 corpus 阈值的**蒸馏固化**、且是 monitor 判异常的**同款真值**(管家用它答与系统自洽);只有"标准条款原文/出处/为什么是这个值/跨标准差异"才需查 corpus(留后)。故 MVP **不上 RAG/embedding**,免 key、RPi 零本地模型(不背 torch)。两次 LLM 都 deepseek-v4-flash(作者拍板对话全 flash、不升 V3)。
- **教训**:① "廉价源"也不该无脑全拉——数据会增长,dispatch 的价值就是**按需**;要某信息进上下文,用意图分类显式 gate,别图省事全灌。② 判断"要不要 RAG"看**要不要标准原文**:数值阈值比较有蒸馏值(thresholds)就够,thresholds 本就是 corpus 的固化,且与 monitor 共享真值=自洽——这也复用了 P-014"thresholds 是系统真值"的结论。③ FastAPI 的 `File(default=None)` 放参数默认里会被 ruff B008 拦,改 `UploadFile | None = None`(FastAPI 仍识别为上传)即可。
- **关联**:`agents/conversational.py`(两步式 + `RetrievalPlan`)· `ops/prompts/conversational/{dispatch,respond}/v1.md` · `sensing/history.py`/`ops/sampler.py`/`sensor_readings` 表 · `core/router.py` node `conversational.dispatch`=FAST · `sensing/thresholds.py`(范围判定真值)· `voice/provider.py`(级联 mock)· `frontend/`(FastAPI+HTMX+Web Speech)· 计划 `5-incident-...-resilient-duckling.md`

### P-018 · Phase 5 · 问答管家多轮 + 流式:前端持有 history(后端无状态)+ mypy 流式 overload 退化  ✅
- **现象/动作**:把单轮无状态问答升级为**多轮 + 流式**(作者拍板英文对话)。
- **关键设计**:① **多轮无状态**——history 由**前端持有**、每轮随请求带上,后端**不存 session**(免 session 表/内存 dict、FastAPI 多 worker 不怕状态不共享),后端 `_parse_history` 防御式解析 + 滑窗截最近 6 条;**dispatch 和 respond 都要喂历史**(只喂 respond 不够:dispatch 拿不到上文就把裸追问 "what about humidity?" 的 sensor 分类不出来)。prompt bump **v2**:从「`$query` 占位塞进单 user message」改为 **system 指令 + 历史多 message + 当前 user(含 `<context>` 包当轮取数)**,全英文。② **流式**——`router.stream()` yield delta,**fallback 只在「还没吐出任何 token」前切换**(`produced` flag);一旦开吐,中途失败直接抛(重试会重复输出)。`respond_stream` 是 generator,**dispatch+gather 惰性到首次迭代才跑**(StreamingResponse 一迭代就触发,首 token 含这段)。语音路径保留**非流式** `respond`(浏览器 TTS 要完整文本)。
- **踩坑**:`self._client.chat.completions.create(stream=True, **kwargs)` 里 `**kwargs: Any` 让 openai `create` 的 **overload 解析退化**,mypy 把流式返回推断成 `tuple[str,Any] | ChatCompletionChunk`,迭代 `chunk.choices` 报 union-attr。修:`cast("Iterator[ChatCompletionChunk]", create(...))` 钉死类型(非流式 `complete()` 无此问题——overload 在 stream 缺省时正确选 ChatCompletion)。
- **实测**(真 LLM,Postgres/Qdrant 起):"is the temperature ok?"→sources=[]、流式 33 块、首 token 1.9s、答 22.5℃∈19-26;裸追问 "what about humidity?"(未点名环境湿度)→turns=1、**接住上轮**、答 45%RH∈30-60、还呼应上轮说 "also fine"。ruff + mypy(core 严格)全绿。
- **教训**:① 多轮的「循环」和「上下文」是两件事——Web 形态循环天然有(每条消息一轮),真正要补的是**把历史喂进去**;且**两步式里每一步**(分类+合成)都要吃历史,漏掉分类那步指代就断。② history **前端持有 + 后端无状态**是 MVP 最省的多轮方案(无 session 管理),代价是每轮多传一点 + 后端要兜底解析/滑窗。③ 流式 fallback 不能像非流式那样无脑重试——**已吐字就不能重来**,只能在未产出前切换。④ `**kwargs: Any` 会击穿 SDK 的 `@overload`,流式/非流式返回类型混淆,`cast` 比一堆 `type: ignore` 干净。
- **关联**:`core/router.py` `stream()`(`produced` fallback + cast)· `agents/conversational.py`(`respond`/`respond_stream`/`_prepare`/history-aware `_dispatch`)· `ops/prompts/conversational/{dispatch,respond}/v2.md` · `frontend/api/main.py`(`/api/chat` StreamingResponse + `_parse_history` 滑窗)· `frontend/app/index.html`(ReadableStream 流读 + 客户端 history + en-US)· P-017(本条是其多轮+流式续作)

### P-019 · Phase 4/5 · 三域 thresholds 纵向对齐:走完 P-016 留的 corpus→monitor→planner→generate→bench 链 + 三裁断  ✅
- **动作**:补完 P-016「下次接」清单 1-4——thermal/lighting/acoustic 三域 `thresholds.py` 占位对齐到真 WELL corpus,并端到端走完 P-014 定义的 **corpus→monitor 阈值→planner goal→generate 引用→bench gold** 纵向链。
- **取证先行(P-014 方法论)**:不信二手转述,直接 scroll Qdrant `ieq_standards` 三域 chunk 提真值。三处占位病灶 + **推翻一个二手说法**:thermal **19-26→21-25 °C**(WELL T01 干球 "70-77°F(21-25°C)",引 ASHRAE 55-2013);lighting **300→320 lux**(WELL Predetermined 表 "Offices and classrooms: 30 fc(320 lux) at task surface",循环区 110)——corpus **5 个参考指南都列了**(IES/EN 12464-1/ISO 8995/GB50034/CIBSE SLL),P-016 快照「EN 12464 不在库」**不准确**,真问题是数值 300→320;acoustic **55→50 dBA**(WELL S02 表 Average Leq 1-point/Cat3 = 50,占位 55 比最低合规线还松)。RoomState 默认(22.5/420/41)排查全仍 in-band、critic 物理范围不打架。
- **运行链对齐**:`thresholds.py` 三行值+rule(长串括号隐式拼接过 E501,**拼接结果脚本校验逐字 == bench rule_violated**)、`room.py` band 注释、`scenarios.py` 三 demo 描述;monitor `rules_text()` 自动渲染对齐。
- **bench 迁移 + 三裁断**:① `l1_retrieval` 5 条 gold_sources(含 co2 残留 ashrae-62.1/ops-note)→`well-v2`——但**诚实标注退化**:真 corpus 单 source,`score_retrieval` 按 source 比对会让 hit@k **恒真**,迁移=消除 known-fail 但变烟雾测试,真判别留扩 200(同理 `l2_rewrite` 单 source MRR 恒 1 失效,**不动**)。② 运行链镜像 jsonl(planner/recurrence/e2e/generate/e2e_hard)`rule_violated` 统一成新 thresholds 串(脚本只替含旧占位标志的,**dry-run 抓出并放过** `hardwell` 的 `800 ppm WELL DCV`——故意的更严负控,非残留)。③ **`l2_critic` 整组不动**——封闭确定性单元,`co2-good` 诊断 target=1000 配旧 rule 才自洽,改 anomaly rule 而不动 target 会**直接破坏 gold approved**;critic 的 anomaly.rule 非运行链镜像。④ gold_values 据**实跑**定(下条)。
- **实跑三域链环④(真 LLM + GPU 检索,demo 三场景)**:generate 全部 grounded 到真 corpus 真值、有 excerpt 出处、无假归因——lighting "320 lux ... per **CIBSE SLL** (excerpt 1)"(故 e2e gold `EN 12464`→**`320`**,锚数值不锚随检索波动的标准名);thermal "29°C ... 21-25°C comfort range, **ASHRAE 55-2013** (excerpt 2)";acoustic "**Category 3 background noise limit of 50 dBA (Leq)** (excerpt 5)"。co2 据 P-014 已证引 WELL/900,gold `ASHRAE`→`WELL`。
- **正交既有问题(非本次引入,记待跟进)**:acoustic demo **critic 否决**——理由 `target_time_min=15` 不现实("降噪靠设备选型+立面改造,15min 不可达"),与 50/55 阈值无关,是 acoustic specialist 的 expected_outcome 时间窗问题(降噪本就非 15min 物理过程)。诊断真值已对、critic 在正确工作。留后:acoustic `target_time_min` 调成合理窗 / 或 demo 场景标注。
- **校验**:ruff+format+mypy(strict core)全绿;9 jsonl 全合法;残留扫描仅剩 `l2_critic`(故意保留)。
- **教训**:① **真 corpus 是照妖镜,二手转述也得复验**——这次连「EN 12464 不在库」的快照说法都被取证推翻(它在,5 选 1),靠 scroll 真 chunk 而非信记录。② bench gold 迁移**不是无脑替换**:单 source 退化(retrieval 假绿)、封闭单元(critic 改 rule 破坏自洽)、故意负控(hardwell)三类都要 dry-run + 人工裁断,脚本「按 sensor 统一」会误伤。③ 纵向对齐**必须实跑链环④**才算闭环——只改 thresholds 不跑 generate,看不出它引 CIBSE 还是 EN、引 320 还是编值。④ acoustic 的 critic 否决证明 **plausibility/coherence 闸在干活**,也暴露 specialist 时间窗与物理过程脱节——真闭环系统该有的张力。
- **关联**:`sensing/thresholds.py`(三域值+rule)· `sensing/simulator/{room,scenarios}.py` · `eval/ieq_bench/tasks/{l1_retrieval,l2_planner,l2_generate,l3_e2e,l3_e2e_hard,l3_recurrence}.jsonl`(迁移)· `l2_critic.jsonl`(故意不动)· `eval/metrics.py`(score_retrieval/generate_hit 判分语义)· P-014(co2 同型,本条是三域版)· P-016(补完其「下次接」1-4)· memory `project_corpus_source`

### P-020 · Phase 4/5 · critic 否决在「无 actuator 的人工域」升级为请人介入,而非 FAILED  ✅
- **动作**:作者拍板「声学只报 incident 然后请人类介入」。承接 P-019——acoustic 的 critic 否决(masking/换设备不降 dBA)本是**正确**判断,但归宿是 FAILED(像出错),不符合「系统做不到 → 交人」的语义。把 critic 否决在 Tier3(无 actuator、必然人工)域**升级为走 autonomy_gate 请人**;Tier1/2(会自动执行)域仍 FAILED。
- **关键洞察**:critic 否决的含义是「别让系统自动执行这个方案」。对**有执行器**的域(airquality Tier1)否决 = 别自动执行 = FAILED 合理;对**无执行器、本就人工**的域(thermal/lighting/acoustic Tier3)否决 = 系统自己做不到 = **这正是该请人的信号**,不该当失败。**critic 的判断标准一字未动**(没放松),只改否决之后的去向。
- **实现(分层干净)**:① `_TIER_BY_DOMAIN` + `tier_for_sensor()` 从 `core/graph.py` 移到 `core/state.py`——critic 要按 tier 分流但**不能 import graph(循环依赖)**,放 state 两边共用。② `_route_after_critic`:approved 或 (disapproved + Tier3) → `autonomy_gate`;否则 END。③ `critic._disapprove`(新):Tier3 → status `AWAITING_APPROVAL` + ticket patch(不 FAILED);Tier1/2 → 原 `_fail`(FAILED)。④ `autonomy_gate` interrupt payload 带 critic `concerns`——escalation 时 reason 区分「No autonomous fix available」,把 critic 顾虑交给人研判。**复用现成的 `AWAITING_APPROVAL` 状态 + Tier3 interrupt 机制,不新增状态、不动 schema、不绕过 autonomy_gate(硬约束#2)**。
- **实测**:acoustic `noisy_room` → `critic_disapproved`(masking 加噪不降 dBA)→ `critic_escalate_human` → ticket `awaiting_approval` → ⏸ Tier3 interrupt(reason「No autonomous fix available」+ concerns 带 masking 顾虑)。**不再 FAILED**。回归:thermal `overheating` approved → Tier3 interrupt(concerns=[],普通审批,payload 改动没崩);co2 Tier1(AUTO)不进 interrupt 分支,approved 路径未触。ruff+mypy(strict core)全绿。
- **教训**:① 同一个「否决」对不同 tier 该有不同归宿——**有自主手段的域否决=失败(别瞎执行),无自主手段的域否决=升级人工(本就该人来)**。这比「放松 critic 兜底」健康得多:质量闸不破、坏方案不漏、人只在系统真做不到时被叫。② domain→tier 映射放 state(非 graph)是为让 critic 读它而不循环 import——**路由策略该放在 agent 和 graph 都够得着的中性层**。③ mypy 收窄:`escalated = verdict is not None and ...` 这种 bool 中转变量 mypy 不借它 narrow,要把 `verdict is not None` 直接写进使用处的 if。
- **边界/待跟进**:acoustic 无 actuator(Phase 5),人 approve 后 `action` 节点暂无 acoustic 执行器(demo 停在 interrupt 符合「请人介入」语义);Tier1/2 否决 → replan 仍 Phase 3 未接(否决=END,无重规划)。
- **关联**:`core/state.py`(`_TIER_BY_DOMAIN`/`tier_for_sensor`/复用 `IncidentStatus.AWAITING_APPROVAL`)· `core/graph.py`(`_route_after_critic`/`autonomy_gate`)· `agents/critic.py`(`_disapprove`)· P-019(承接其 acoustic 时间窗发现 + v5 回滚)· CLAUDE.md 硬约束#2

### P-021 · Phase 5 · 真语音级联:阿里云百炼 CosyVoice 流式 TTS + 英文 STT,push 回调桥成拉取流 + NDJSON 多路复用  🔧(mock 链路 E2E 验通,真 key 段待填)
- **动作**:承接 P-018 文本流式,把语音从 `MockVoiceProvider`(浏览器 Web Speech)升级到**真云级联**——作者拍板 STT/TTS 走**阿里云百炼**,TTS=**CosyVoice `cosyvoice-v3-flash`**(实时最快档),STT=`paraformer-realtime-v2`;**butler 全英文**(STT en + 英文音色 + LLM 已英文)。
- **延迟设计(作者核心诉求「LLM 既然流式,怎么让对话延迟最低」)**:**不等整段答完再合成**——`respond_stream` 的 token 边吐边灌进 CosyVoice 双工 WS(`server_commit` 服务端自动分句),`audio.delta` 边回边播;出声延迟 ≈ STT + LLM 首句 + TTS 首包,**而非各段相加**。LLM 首 token ~1.9s(P-018)是地板,把 TTS 藏在生成背后而非叠加其后;压延迟手段:预热/常驻 WS 连接(首包含建连)、prompt「先一句话直答」、PCM 24k 免解码、选 v3-flash。
- **关键实现**:① **push→pull 桥**——DashScope SDK 是回调推送(`ResultCallback.on_data(bytes)`),但要 `synthesize_stream(text_iter)->Iterator[bytes]` 拉取式:`queue.Queue` + feeder 线程(迭代 token `streaming_call()` 喂字、`streaming_complete()` 收尾)、回调把音频帧 put 进队、主生成器 get 出来 yield、`_DONE` 哨兵收尾,完后读 `get_first_package_delay()`。② **NDJSON 多路复用** `/api/voice/stream`——一条流里既要**屏幕文字**又要**语音**:`_tee()` 把 token 流分两路(put 进 bus 给前端显示 + yield 给 TTS),audio 帧 base64 进同一 bus,主生成器序列化成 `{query|token|audio|done}` 行。③ **前端**——`PcmPlayer`(Web Audio 把 24k PCM 帧排到游标 gapless 播)+ `WavRecorder`(ScriptProcessor 抓音频、降采 16k、自编 WAV;MediaRecorder 出 webm/opus 不合 paraformer)+ NDJSON 流读。④ **降级**——`get_voice_provider()` 无 key/构造失败退回 mock;mock `synthesize_stream` drain token 不出音频,前端无 audio 帧时回退浏览器 `speak()`,链路恒可演示。
- **实测(mock 链路,真 ConversationalAgent+DeepSeek)**:`TestClient` 打 `/api/voice/stream`「what's the CO2 right now?」→ HTTP 200、`query`1+`token`31+`done`1、**无 audio**(mock 正确)、`first_package_ms=None`、答 "650 ppm ... at or below 900 ppm"(grounded 英文)。tee→线程→bus→NDJSON 整条编排验通。ruff+mypy(strict core)全绿。
- **Δ 同 session 改型(作者实测后定)**:作者测出**新加坡 endpoint 比北京快 ~5s**,拍板改用 **Qwen3-TTS-Flash**——TTS 从 CosyVoice 换成 **`qwen3-tts-flash-realtime`**(新加坡 `wss://dashscope-intl.aliyuncs.com/api-ws/v1/realtime`),音色 **`Jennifer`(詹妮弗/美剧大女主)** + `language_type=English`。**接口换家族**(CosyVoice `tts_v2.SpeechSynthesizer` ≠ Qwen):`QwenTtsRealtime.connect()/update_session(voice,language_type)/append_text(chunk)/finish()` + 回调 `on_event` 取 `response.audio.delta`(base64,**仍 PCM 24k → 前端 PcmPlayer 不用动**),首包用内置 `get_first_audio_delay()`;完成检测用**终止事件集 + 静默超时双保险**(realtime 终止事件名不定,避免挂死)。`CosyVoiceProvider`→`DashScopeVoiceProvider`(名副其实)。
- **STT 新加坡区踩坑链(真 key 逐个排掉)**:① `paraformer-realtime-v2`(`Recognition`/`/api-ws/v1/inference`)→ **401**:`Recognition` 用全局 `base_websocket_api_url`(默认北京),新加坡 key 打北京 ws 被拒;② ws 指新加坡 → **status 44 Model not found**:**paraformer 新加坡区没有**,intl 的 ASR 是 **Qwen3-ASR** 系;③ OpenAI 兼容 `audio.transcriptions` → **404 不支持**;④ 改 **`qwen3-asr-flash` 走 `MultiModalConversation.call`**(HTTP,audio 走 `messages` 的 `file://` URL,`asr_options={'language':'en','enable_lid':False}`)→ **200 通**。STT 不再走 ws,`dashscope_asr_ws_url` 删除。与作者拍板 `qwen3-asr-flash` 一致。
- **两端真实 E2E 全绿(新加坡 key)**:TTS round-trip 首包 **666/684ms**;TTS→降采16k→STT 保真("...650 ppm..."→"CO two level of six hundred and fifty parts per million...",数字/缩写口语化正常);**真端点 `/api/voice/stream` 上传 wav 全链路**:STT→LLM 流式 34 token→**真 TTS 28 音频帧**→done,首包 **651ms**,grounded 英文。**`.env` 需 `VOICE_PROVIDER=aliyun`**(只填 key 不够,否则端点退回 mock→transcribe 空→error,已实测踩到)。mock 链路改名后复验仍通。
- **待跟进**:真音频段卡 `DASHSCOPE_API_KEY`(未在 `.env`)——`ops/scripts/voice_smoke.py` 填 key 一命令验真合成+量首包;STT 二期上流式;realtime `commit`/server 分段模式 + WS 预热常驻连接留优化。voice/ 的 dashscope `import-untyped` 仅因第三方缺 stub(严格门只管 core)。
- **教训**:① 回调推送 SDK 接流式 Web,**queue+线程桥成拉取迭代器**是干净解法——别在回调里直接 await/yield。② 一条 HTTP 流要同时带文字和二进制,**NDJSON + base64 帧**比双连接简单;`_tee` 让 token 一源两用(显示 + 喂 TTS)。③ 浏览器要真 wav 给云 STT 得**自己编 WAV**(MediaRecorder 给的是 webm/opus);TTS 回放用 Web Audio 排游标做 gapless,别每帧 new 一个 `<audio>`。
- **关联**:`voice/provider.py`(`DashScopeVoiceProvider`/`synthesize_stream` push-pull 桥 + QwenTtsRealtime/`get_voice_provider` 分支)· `frontend/api/main.py`(`/api/voice/stream` NDJSON 多路)· `frontend/app/index.html`(`PcmPlayer`/`WavRecorder`/NDJSON 流读)· `core/config.py`(`dashscope_api_key`/`dashscope_ws_url`/`dashscope_http_url`/`tts_model`/`tts_voice`/`tts_language`/`asr_model`)· `ops/scripts/voice_smoke.py` · P-018(文本流式前作)· memory `project_voice_cascade`/`project_butler_english` · 计划 `5-agent-mrk1010-...-lamport.md` Task 1
