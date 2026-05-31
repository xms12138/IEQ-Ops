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

### P-009 · Phase 2 · verifier 取 subtask_result 与 action 选取逻辑不一致  ⏳
- **现象**:(潜在,尚未触发)`verifier.py:44` 用 `next(iter(state.subtask_results.values()))` 取**第一个**子任务结果,而 `action`/`autonomy_gate` 用 `state.primary_result()`(domain 匹配异常 sensor 的那个)。
- **根因**:单子任务 co2 场景两者恰好相同,所以一直没暴露;但多子任务 DAG 且 dict 里第一个不是 primary 时,verifier 会去核验一个 advisory 子任务的指标。
- **状态**:⏳ 本 session(2026-05-31)读代码时发现,待把 verifier 对齐为 `primary_result()`。
- **教训**:同一个「主结果」的选取逻辑应集中一处(`primary_result()`),各节点共用,避免各取各的埋下不一致。
- **关联**:`agents/verifier.py:44` vs `core/state.py` `primary_result()`
