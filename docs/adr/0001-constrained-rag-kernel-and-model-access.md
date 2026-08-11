# ADR-001：受约束 RAG Domain Kernel 与 Model Access 边界

| 属性 | 内容 |
| --- | --- |
| 状态 | `ACCEPTED` |
| 决策日期 | 2026-08-10 |
| 架构基线 | [`../tech-plan.md`](../tech-plan.md) 5.2 |
| 相关选型 | [`../technology-selection/models/model-access-orchestration-selection.md`](../technology-selection/models/model-access-orchestration-selection.md) |

## 1. 背景

平台的在线 RAG 同时受 Project、Deployment、Knowledge Binding、不可变 Knowledge Release、Access Segment、Revocation、Evidence、Citation 和 Claim Grounding 约束。这些对象决定可访问数据、可生成事实和可见输出，不能降级为 Prompt 约定或第三方框架内部状态。

LangChain、LangGraph 和 MaxKB 能降低模型接入或通用工作流开发成本，但它们默认提供的 Message、Retriever、Memory、Graph State、会话恢复和流式输出语义不等同于本平台的领域模型。直接让框架持有主 RAG 控制面会扩大类型渗透、版本耦合和越权恢复面。

## 2. 决策

1. 第一阶段由 `assistant-runtime` 自有受约束 RAG Domain Kernel，固定编排 Scope、Query Plan、独立 BM25/Vector 召回、RRF、Reranker、Evidence Hub、Generator、Grounding、Citation 和输出门禁。
2. Scope、Binding、Knowledge Release、Revocation、Evidence、Citation 和 Grounding 是平台领域对象，其状态、校验和失败语义不委托给外部框架。
3. Model Access 采用混合两层结构：领域核心依赖任务语义端口，供应商 SDK 或第三方库只实现 Provider 能力适配。
4. LangChain 不进入主 RAG 编排，只保留为 Model Access Provider Adapter 候选；是否采用仍需与直接供应商 SDK 比较后独立选型。
5. LangGraph 不进入第一阶段主 RAG。第二阶段只有在受限 ToolPlan 确实需要多步状态、重试、人工确认或持久化检查点时，才评估其作为 Agent/Tool 子图实现。
6. MaxKB 仅作为架构思想参考，不引入其运行时、Workflow 或代码。实现保持独立，避免继承其可变知识、会话换版、Citation 重建、未校验流式输出和 GPLv3 代码边界。

## 3. Model Access 契约

```text
领域任务端口
  RouterPort / QueryPlannerPort / GeneratorPort
  GroundingPort / EmbeddingPort / RerankerPort

Provider 能力适配
  ChatGenerationAdapter / StructuredOutputAdapter
  EmbeddingAdapter / RerankAdapter
```

领域端口只暴露平台 DTO、Deadline、逻辑模型、审计上下文和可校验结果。Provider SDK、LangChain Message、Callback、Chain、Retriever、Memory、Agent 或 LangGraph State 不得进入领域核心、持久化模型和跨服务协议。

## 4. 备选与取舍

| 方案 | 结论 | 主要取舍 |
| --- | --- | --- |
| LangChain 承担主 RAG Chain/Agent | 不采用 | 接入快，但框架类型、Memory、Retriever 和回调会侵入领域边界，难以证明 Release、Revocation、Citation 和输出门禁始终成立 |
| LangGraph 承担第一阶段主 RAG | 不采用 | 检索链路当前是固定受约束 Pipeline，引入通用状态图会增加恢复、并发和检查点语义，而没有已证明收益 |
| 直接复用 MaxKB Workflow | 不采用 | 产品思路可参考，但知识发布、检索融合、会话版本、Citation、Grounding 和流式输出语义不满足本平台约束；代码还受 GPLv3 约束 |
| 所有 Provider 永久直连 SDK | 不冻结 | 边界最直接，但可能重复实现协议、结构化输出和流式适配；保留 LangChain 作为适配层候选 |
| 自有 Kernel + 可替换 Provider Adapter | 采用 | 需要自行维护领域编排和契约测试，但能将框架替换成本限制在适配层，并保持安全边界可验证 |

## 5. 影响

- `assistant-runtime` 必须为固定 RAG Pipeline、发布换版、撤回、Evidence、Citation、Grounding 和失败降级提供领域级合同测试。
- Model Access Adapter 必须通过同一套结构化输出、流式、Deadline、重试、审计、数据最小化和错误映射测试。
- Knowledge Workflow 与在线 RAG 分离；解析、切分、Embedding 和索引发布不能通过在线 Agent 修改。
- 后续 Agent/Tool 子图只能调用受限端口，不能直接访问索引、Provider、跨项目 Memory 或未授权业务 API。

## 6. 替代条件

只有以下前提发生实质变化时才重新评审：

- 第一阶段固定 Pipeline 演变为需要持久化状态、长时运行、人工确认和复杂补偿的动态工作流。
- 直接 Provider Adapter 的重复维护成本经量化后显著高于第三方库，同时该库可通过契约测试且不向领域层泄漏类型或状态。
- 外部框架能够原生表达并证明平台的 Release、Revocation、Evidence、Citation、Grounding 和输出门禁不变量，且迁移收益高于控制面替换风险。
