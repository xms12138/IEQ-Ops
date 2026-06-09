# 架构理解笔记 — 顺一个 CO2 incident 走一遍

> **用途**:作者自学复看 / 答辩 / 面试讲这套 multi-agent 架构。
> **分工**:CLAUDE.md=宪法/原则 · EXECUTION_PLAN=进度 · DEVLOG=踩坑 · TECH_STACK=选型 · **本文件=主链路怎么工作 + 几个易混点的澄清**。
> **取材**:真实运行 incident `I-20260531-R1-AQ-165631`(`co2_spike`,`uv run python -m ops.scripts.demo co2_spike`)。
> ⚠️ 文中 `file:line` 是 2026-06 快照,代码改动后可能漂移,以当前代码为准。

---

## 0. 主链路一图

`MainIncidentGraph` 节点顺序(每 5 分钟由 cron + Monitor 触发):

```
monitor → planner → hydrate_placeholders → dispatch ⇄ {airquality|thermal|lighting|acoustic}
        → critic → autonomy_gate → action → ⟨挂起 15min⟩ → verifier → END
```

每个节点换一个 agent、换一个视角、换它能看到的信息 —— 这就是 CLAUDE.md 说的 **"job isolation, not agent theater"**(职责隔离,不是 agent 表演)。

| 节点 | 谁 | 干什么 | 模型 |
|---|---|---|---|
| monitor | MonitorAgent | 阈值判断,报异常(**不诊断**) | 本地→flash |
| planner | PlannerAgent | 拆 ReWOO 子任务 DAG | cloud(REASONING) |
| dispatch + 4 specialist | SpecialistSubgraph ×N | 每子任务各自诊断 | cloud flash |
| critic | CriticAgent | **审**主诊断(信任门) | 本地→flash |
| autonomy_gate | (基础设施) | 定 Tier、Tier3 阻塞等人批 | 无 LLM |
| action | (基础设施) | 调执行器 | 无 LLM |
| verifier | VerifierAgent | 15min 后核验降没降 | 本地→flash |

---

## 1. 一个 CO2 incident 的真实全链路

```
▶ monitor      co2=1300 违反[<=1000] → 建单 I-...165631 → status=planning
▶ planner      召回 3 条历史 co2 案例 → 出 2 子任务 DAG:
                 S1[airquality, 无依赖]:诊断 CO2 1300 病因 + 提通风纠正
                 S2[thermal, 依赖 S1]:评估「#S1.diagnosis 的增大通风」会不会吹冷
▶ specialist   S1: retrieve 5 chunk → grade 够 → generate
                   诊断:"CO2 1300 表明通风不足,依据 ASHRAE 62.1…"
                   期望:{co2, 800, 15min}
               S2: retrieve 3 → grade 不够 → rewrite×3 → generate(质量弱,见 §3 备注)
▶ critic       只审 primary=S1 → ✓ 批准 → status=acting
▶ autonomy_gate airquality → Tier1 → 自动放行
▶ action       set_ventilation=high (450 m³/h)（dev-fake 只打日志）
▶ ⟨挂起 15min⟩  模拟推进 → co2 ≈ 679.4
▶ verifier     delta=-120.6,verdict=met → status=closed → 轨迹写回 episodic memory
```

> 这条链路就是项目的"意义"所在 —— 见 §7 的"vs if-else"对比。

---

## 2. Planner 怎么知道拆哪些任务?

**是 planner 节点的 LLM 读 prompt 规则 + 召回案例 + anomaly 推理出来的,不是硬编码。**

prompt(`ops/prompts/planner/v3.md`)给它的"怎么拆"就三条:
1. **永远先建 1 个主任务**,domain 必须匹配异常 sensor(co2→airquality),无依赖。
2. **当且仅当纠正动作在另一个域有真实副作用**,才加依赖子任务。prompt 直接举例:降 CO2 = 更多室外空气 = 供暖季吹冷 → 加 thermal 子任务查会不会推出舒适带。简单 incident 就该单子任务,别瞎造。
3. **相似案例**:resolved 当正面证据、FAILED 当反面警告、`(none)` 就只凭 anomaly 拆。

→ 这次拆出 S1+S2,是 LLM 套用规则2、把"开通风"和"会吹冷"联系起来。换个噪声异常它就只出 S1。

**注意两点:**
- **非确定性**:同一 co2、召回不同案例/不同采样,可能拆得不同(曾观察到 run2 召回旧案后从 S1+S2 收敛成 S1)。
- **有兜底**:LLM 失败/返空 → `_fallback_plan` 出单子任务(`agents/planner.py:96`),监控环不卡死。

---

## 3. 诊断是谁做的?每个子任务分开诊断吗?

**是 `SpecialistSubgraph` 的 `generate` 节点做的**(cloud V4-Flash,强制不降级,硬约束 #11)。

**每个子任务完全分开、各跑一遍完整五节点子图:**
```
S1: decompose → retrieve → grade(够) → generate          → 诊断A
S2: decompose → retrieve → grade(不够) → rewrite×3 → generate → 诊断B
```
S1、S2 是**两次独立的 `SPECIALIST_SUBGRAPH.invoke()`**,各检索各的 chunk、各 generate。用的是**同一个编译好的子图实例**(module-load 时 compile 一次),被 dispatch 按 domain 用不同 subtask 调两次 fan-out —— 不是四个 specialist 类,是**一个 builder + `domain` 参数**。

诊断**不是"一次 LLM 生成"**,是 RAG agentic loop 的最后一步,`generate` 必须 grounded 在 `retrieve` 拿到的标准原文上(所以能引 ASHRAE 62.1)。

> **备注(诚实)**:这次 S2 质量弱 —— 占位 corpus 没有足够 thermal 副作用细节,grade 连说 3 次不够、rewrite 到上限放弃后才 generate,诊断甚至回声了 co2。但 S2 是 advisory(见 §6),不影响关单。这恰好暴露:**需要真实 corpus**(当前只有 12 占位 chunk)。

---

## 4. Specialist 的诊断 vs Critic —— 一个"写"一个"审"

**Critic 不产诊断**,它审 specialist 写好的诊断。一个是作者,一个是审稿人。

| | **Specialist**(generate) | **Critic** |
|---|---|---|
| 角色 | **写**诊断 | **审**诊断 |
| 输出 | `SpecialistResult{diagnosis 文本, expected_outcome}` | `CriticVerdict{approved: bool, unsupported_claims: [...]}` |
| 看得到啥 | 检索到的标准原文 chunk | **看不到原文**,只看诊断成品 + outcome + anomaly |
| 模型 | cloud flash(强制) | 本地→flash |
| 例 | "CO2 高因通风不足,依据 ASHRAE,开通风,目标 800" | 只回 `{approved: true}`,或 `{false, 列出不一致}` |

demo 里 `▶ critic: ✓ 批准` 背后只是一个 `{approved: true}` 布尔 —— 它没产出任何诊断文本。

**为什么分开**:LLM 自产自审不可靠(既当运动员又当裁判);独立 critic 用不同视角(物理底线 + 内部一致性)把关,防幻觉诊断驱动真设备。

---

## 5. 子图的 state —— 三个边界(共享的是"代码"不是"数据")

CLAUDE.md 说四 domain "shared a compiled instance" —— **共享的是编译好的图(代码/结构),不是运行时 state 数据**。类比:四个人用同一个函数定义 `def diagnose(subtask)`,但每次调用各有独立局部变量。

`SpecialistState` 字段(`agents/specialists/builder.py:58`):`subtask`(进)/ `sub_queries` / `current_query` / `rewrite_count` / `retrieved_chunks` / `sufficient` / `grade_reason` / `final_diagnosis`(出)。

| 边界 | 共享 state? | 说明 |
|---|---|---|
| **① 五个节点之间**(同一次 invoke 内) | ✅ 共享一个 | decompose 写 `sub_queries` → retrieve 写 `retrieved_chunks` → grade 写 `sufficient` → rewrite 写 `current_query` → generate 写 `final_diagnosis`。**五步靠这一个 state 接力** |
| **② S1 invoke vs S2 invoke** | ❌ 不共享 | 同一函数调两次,各自独立 state 实例,`retrieved_chunks` 是两份不同内存 |
| **③ 子图 vs 父图** | 🔒 隔离 | SpecialistState 是子图自己的 schema;只 `subtask` 进、`final_diagnosis` 出;大字段永不进父 checkpoint(Phase 2 红线#2,防膨胀) |

> "几个专家共享 state"这个直觉里:**对的是边界①**(一次诊断的五个**步骤**之间);**错的是**把它理解成 S1/S2 之间或四 domain 运行时共享数据。

---

## 6. Critic 怎么工作?审什么?

**整个 incident 跑一次,只审 primary(主)子任务**(`agents/critic.py:73` `primary = state.primary_result()`),S2 不看。

**为什么只审 primary**:只有 primary 会真驱动执行器(autonomy_gate / action / verifier 全 key off `primary_result()`)。advisory 子任务(S2)不动设备,不需要这道门。甚至 S2 失败了 critic 也只 log、不否决(`critic.py:68-71`)—— advisory 再烂不污染主决策。

**审什么 —— 两道门(`_validate`,`critic.py:97`):**

**门① 确定性数值底线**(无 LLM,一票否决,`_plausibility_flags` `critic.py:124`):
- `target_metric` ∈ {co2,temperature,humidity,lux,noise_db}?
- `target_value` 在物理范围?(co2∈[350,5000] / temp∈[10,40] / lux∈[20,3000]… `critic.py:51`)
- `target_time_min` ∈ [1,240] 分钟?

**门② LLM 一致性 + outcome 吻合**(`critic.validate`,本地→flash,喂诊断+outcome+anomaly,**不喂原文**):
- 内部一致性:诊断自相矛盾吗?动作从病因推得出吗?
- outcome-to-diagnosis fit:target_metric 是诊断在说的东西吗?target_value 方向对吗?时间窗合理吗?
- prompt **禁止**因"看不到原文"否决引用 —— 默认上游已忠实检索。

**判定**:`approved = llm.approved AND (not floor_flags)`(`critic.py:122`),两道门 AND。
**兜底**:LLM 挂了 → 退化成只看数值底线 `approved = not floor_flags`(`critic.py:115`),不死锁。

**会被否决的例子:**
- 门①:诊断说开通风,但 `expected_outcome.target_value = 50`(co2)→ `50 ∉ [350,5000]` → 否(物理荒谬)。
- 门②(真实发生过,DEVLOG P-008):诊断正文"预计降 150–300 ppm"(→~1100),却声明 target 800 → 自相矛盾 → 否。
- 门②:诊断"CO2 高因人多",动作却"调暗灯光"→ 动作与病因无关 → 否。

---

## 7. 否决/失败之后?—— replan 未接(实现 vs 计划)

**当前实现**:critic 否决 → `_fail`(`critic.py:85`):标 ticket `FAILED` + 条件边路由 **END**,**不动任何执行器**。硬证据在出口映射(`core/graph.py:294`):
```python
{"critic", _route_after_critic, {"autonomy_gate": "autonomy_gate", END: END}}  # 只有两个出口,没有 replan
```

**设计意图(CLAUDE.md / `critic.py:22-25` 注释)**:否决应 → **replan**(失败触发重规划,而非沉默)。**但还没接。**

**为什么 replan 没那么简单**(被推后的原因):
1. 要重置 `subtask_results`(否则被否的烂诊断还赖在 state 里)
2. 要 `replan_count` 上限(防"规划→被否→再规划"无限循环烧钱)
3. 要把否决原因(`unsupported_claims`)喂回 planner,让它换角度,否则重复同错

→ 现在先用 END 把不安全执行挡在门外(安全优先)。**这和"verifier 失败触发 replan"是同一个待补口子**,都是闭环"失败恢复"分支。

---

## 8. Autonomy Tier 谁定、怎么判 1/2/3?

`autonomy_gate` 节点定的(`core/graph.py:173`)。Tier 三级(`core/state.py:64`):
- **AUTO=1**:可逆、低影响 → 静默自动执行
- **NOTIFY=2**:执行 + 通知人
- **APPROVE=3**:`interrupt()` 阻塞,等人批才继续

**当前实现 = 按 domain 查静态表**(`core/graph.py:81`):
```python
_TIER_BY_DOMAIN = {"airquality": AutonomyTier.AUTO}
tier = _TIER_BY_DOMAIN.get(domain, AutonomyTier.APPROVE)  # 其余 domain → Tier3 兜底
```
→ `airquality=Tier1` 是**人为写死**的(注释 `graph.py:78`:ventilation 可逆、低占用者影响)。thermal/lighting/acoustic 没执行器,落 Tier3 → 这就是 demo 里那三个停在 `interrupt()` 的原因。

**设计意图**:按**可逆性 + 能耗影响 + 占用者干扰**逐动作动态算(开通风→Tier1,"关停整层空调"→Tier3)。**逐动作计算留 Phase 5**(真接多执行器时)。另:NOTIFY(Tier2)目前代码无专门分支,只 Tier3 会 interrupt。

---

## 附:几处"已实现 vs 计划"诚实清单

| 组件 | 当前实现 | 设计意图(未接) |
|---|---|---|
| critic 否决后 | 标 FAILED + END,不执行 | replan 重规划 |
| verifier 失败后 | (同上待补) | replan |
| autonomy Tier | 按 domain 静态表 | 逐动作 reversibility 计算(Phase 5) |
| RAG corpus | 12 个占位 chunk | 真实 ASHRAE/WELL/EN/WHO PDF |
| contextual prefix | prefix="" 未注入 | V4-Flash 前缀注入(节点 #10) |
| 真实硬件 | 物理模拟器 | RPi 传感器 + InfluxDB(Phase 5) |
| Tier2 NOTIFY | 无分支 | 执行+通知 |

> 一句话:**自主诊断-决策-执行-验证-记忆的闭环骨架已能在模拟器上端到端跑**;失败自我修复(replan)、逐动作 Tier、真实硬件/corpus 是 Phase 4–6 待补。
