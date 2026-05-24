**伦敦大学学院 CASA 实验室合作项目    项目负责人    2026.02.17 – Present**

* **项目内容**：基于 LangGraph 的多智能体系统开发，覆盖室内环境异常检测、规划、工具调用、验证的闭环流程。
* **项目工作**：
* **LangGraph**：Monitor / Planner / Specialist / Critic / Verifier 五个 Agent 协作；高风险动作通过 interrupt() 阻塞等待人工审批；规划层采用 Plan-and-Execute + ReWOO 混合范式——Planner 一次性生成 DAG，子任务靠 E1、E2 变量占位符串起来，无依赖部分并行执行。
* **Agentic RAG**：复杂 query 先拆解，返回结果由 Agent 进行 Self-Reflective 判断是否正确，不足则重写 query 再检索；后端 BM25 + BGE-M3 双路召回 + bge-reranker-v2-m3 精排，并使用 Anthropic Contextual Retrieval 给 chunk 注入上下文前缀。
* **Memory**：LangGraph State 维护 Short-term 工作记忆，Qdrant 存全部已结案 incident 轨迹作为 Episodic 记忆。
* **FastMCP**：部署 sensor / actuator / RAG / ticket 四个 Server，使用 Pydantic 确保模型格式化输出。


* **项目成果**：端到端 Token 较 ReAct baseline 下降 ~30%，Top-5 召回较 dense-only 提升 ~18%。
