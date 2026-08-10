# Model Access 与编排框架选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| LangChain RAG 编排 | 承担检索、Memory、Prompt、生成或 Agent 主控制面 | 不采用 | 不进入领域核心 | `REJECTED` | 不进入第一阶段在线 RAG | 全阶段主 RAG | `assistant-runtime` 受约束 RAG Domain Kernel | 框架默认对象和状态语义不能替代 Scope、Binding、Release、Revocation、Evidence、Citation 与 Grounding；类型渗透会扩大升级和审计边界 | 仅整体 RAG 领域架构正式重构时重评 |
| LangChain Provider Adapter | 复用模型供应商接入、消息转换、结构化输出和流式协议能力 | 第一阶段暂不引入 | 仅允许位于 Model Access Provider Adapter 内；具体包与版本未定 | `DEFERRED` | `model-access` 适配层 | Provider 复杂度触发后 | 百炼、方舟原生 SDK 或 REST Adapter | 首期 Provider 数量有限，直接 Adapter 更容易固定版本、错误语义和数据边界；保留混合两层端口，后续引入 LangChain 无需修改领域核心 | Provider 达到三个及以上，或协议、流式与结构化输出重复维护成为主要成本时启动专项 PoC |
| LangGraph 主 RAG Workflow | 用状态图编排第一阶段在线问答 | 不采用 | 不进入主请求链路 | `REJECTED` | 不进入第一阶段在线 RAG | 第一阶段 | 受约束固定 Pipeline | 当前主 RAG 是可测量的固定链路，引入通用状态图会扩大检查点、恢复、并发和副作用边界而无已证明收益 | 仅主 RAG 演变为长时动态工作流且架构边界重新评审时重评 |
| LangGraph 受限 Agent/Tool 子图 | 为多步工具调用、重试、人工确认和持久化检查点提供图执行能力 | 暂不引入 | 具体版本未定；只能实现已授权 ToolPlan 子图 | `DEFERRED` | 第二阶段 Assistant Tool Runtime | 第二阶段条件引入 | 自研受限状态机或固定 Tool Pipeline | 工具场景可能受益于状态图，但框架不得接管 Scope、Evidence、Citation、Grounding、Model Access 出站策略或任意工具发现 | 冻结 Tool Contract、授权、幂等、补偿和人工确认需求后决定是否 PoC |
| MaxKB Runtime / Workflow 复用 | 直接采用其应用、知识、会话和 Workflow 运行时 | 不采用；只参考架构思想并独立实现 | 本地研究基线 `v2@d59728533538130fc77656559c4a1caa78e9aa01`；GPLv3 | `REJECTED` | 不进入产品依赖和代码基线 | 全阶段 | 自有 Domain Kernel；按思想独立实现可取模式 | 固定 Pipeline/复杂 Workflow 分离、发布快照、Provider Registry 和资源依赖图值得参考，但知识可变、会话换版、Citation、Grounding、流式输出及许可证边界不符合本平台约束 | 仅许可证和核心领域语义同时发生根本变化时重评 |
