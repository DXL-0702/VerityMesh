# VerityMesh 开发架构图

```mermaid
flowchart TB
    user["平台用户<br/>消费者 / 内容人员 / 审批者 / 管理员"]
    uiEntry["portal-web<br/>Vue 3 + TypeScript + Vite<br/>Portal / Project Page / Vue Web Component"]
    publicGateway["Public API Gateway · 产品待选<br/>TLS / 基础认证 / 限流 / REST 与 SSE 转发"]
    apiEntry["platform-api · Java + Spring Boot<br/>Public API / Bootstrap Token / 统一审计入口"]
    interaction{"本次用户交互"}
    userResult["用户获得结果<br/>已验证回答 / 发布状态 / 撤回状态"]

    user -->|"打开门户、项目页或宿主组件"| uiEntry
    uiEntry -->|"REST / SSE；外部 Embed 使用一次性 Bootstrap Token"| publicGateway
    publicGateway -->|"统一转发"| apiEntry
    apiEntry --> interaction

    subgraph online["在线问答链路"]
        direction TB
        qAccess["platform-api<br/>解析 Identity / ProjectGrant / Session / Binding / Release"]
        qAuthority["MySQL<br/>读取业务、权限、Session 与 Active Release 权威状态"]
        qContext["platform-api<br/>构造不可由客户端指定的 Immutable Project Execution Context"]
        qGuard["assistant-runtime · Python + FastAPI + uv<br/>Scope / Binding / Release Guard"]
        qRevocation["Redis Online<br/>复核 Revocation / Session / 短期 Memory"]
        qBm25["Elasticsearch Published BM25 Projection<br/>先应用 Project / Release / Locale / Access Filter<br/>再执行 BM25 Top-K"]
        qVector["PostgreSQL / pgvector Published Vector Projection<br/>应用同一组过滤条件<br/>再执行 Vector Top-K"]
        qKernel["assistant-runtime · Constrained RAG Domain Kernel<br/>RRF → Reranker → Evidence Hub → Prompt Builder"]
        qModels["Model Access / Provider Adapter<br/>Reranker / Generator / Grounding"]
        qValidation["assistant-runtime<br/>Claim Grounding / Citation / 内容门禁<br/>只产生 Validated Claim / Evidence-only / Refusal"]
        qProxy["platform-api → Public API Gateway<br/>记录 Message / Audit 并代理 Validated SSE"]
        qView["portal-web / Vue Web Component<br/>展示答案、引用或拒答"]

        qAccess --> qAuthority
        qAuthority --> qContext
        qContext -->|"内部 mTLS REST + Immutable Context"| qGuard
        qGuard -->|"每个请求都检查"| qRevocation
        qRevocation -->|"未命中撤回才允许文本召回"| qBm25
        qRevocation -->|"未命中撤回才允许向量召回"| qVector
        qBm25 -->|"BM25 Rank"| qKernel
        qVector -->|"Vector Rank"| qKernel
        qKernel -->|"领域端口调用"| qModels
        qModels -->|"可校验模型结果"| qValidation
        qValidation -->|"禁止透传原始 Token"| qProxy
        qProxy --> qView
    end

    interaction -->|"提问 / 搜索"| qAccess
    qView --> userResult

    subgraph publishing["知识接入与发布链路"]
        direction TB
        kControl["platform-api · Knowledge Control<br/>接收上传、Push API 或治理操作"]
        kSource["OSS Source Zone<br/>保存源对象与不可变 Source Revision"]
        kSourceTx["MySQL<br/>提交 SourceRevision / Task State / Outbox Record"]
        kOutbox["platform-api · Transactional Outbox Publisher"]
        kSourceEvent["Kafka<br/>发布可重放 SourceRevision / Tombstone Event"]
        kDispatcher["batch-worker · Python + uv<br/>Kafka Dispatcher 将事件转换为 Celery JSON Task"]
        kCelery["Redis Celery<br/>Broker / Short-lived Result / 幂等与有限重试"]
        kBuild["batch-worker · Celery<br/>从 OSS 读取内容并编排 Scan → Parse/OCR → Deduplicate → Chunk → Embed"]
        kBatchModels["Model Access / Provider Adapter<br/>OCR / Embedding"]
        kArtifacts["OSS Governance / Chunk Assets<br/>保存解析产物、不可变正文与 Chunk Manifest"]
        kBm25Staging["Elasticsearch BM25 Staging Projection<br/>写入正文、高亮字段与过滤投影"]
        kVectorStaging["PostgreSQL / pgvector Vector Staging Projection<br/>写入 Chunk、Citation、过滤字段与 Vector"]
        kEvaluation["batch-worker + Model Access<br/>执行 Retrieval / Answer / ACL / Leakage 发布评测"]
        kReadyEvent["Kafka<br/>Progress / CandidateReady Event"]
        kCandidate["platform-api Event Projector → MySQL<br/>更新任务状态与 Release Candidate"]
        kApproval["portal-web<br/>内容审批者查看评测结果并批准激活"]
        kRelease["platform-api · Release Control<br/>提交 ActivationRequested 与 Outbox Record"]
        kActivationEvent["Kafka<br/>ActivationRequested Event"]
        kActivator["batch-worker · Projection Activator<br/>验证经过批准的两套 Release Projection"]
        kBm25Ready["Elasticsearch Published-ready BM25 Projection<br/>按 knowledge_release_id 不可变"]
        kVectorReady["PostgreSQL / pgvector Published-ready Vector Projection<br/>按 knowledge_release_id 不可变"]
        kProjectionGate["batch-worker · Joint Projection Gate<br/>核对数量、Hash、ACL、评测与双 Watermark"]
        kPreparedEvent["Kafka<br/>ActivationPrepared Event"]
        kActiveState["platform-api Event Projector → MySQL<br/>单事务切换 Active Knowledge Release / Deployment Revision"]
        kView["portal-web<br/>展示发布成功、失败或可回滚状态"]

        kControl -->|"写入隔离源区"| kSource
        kSource -->|"源对象落盘后登记元数据"| kSourceTx
        kSourceTx -->|"只读取已提交记录"| kOutbox
        kOutbox --> kSourceEvent
        kSourceEvent --> kDispatcher
        kDispatcher -->|"禁止 Java 直接写 Celery 私有消息"| kCelery
        kCelery --> kBuild
        kBuild -->|"解析、治理与 Chunk 产物"| kArtifacts
        kBuild -->|"领域端口调用"| kBatchModels
        kBatchModels -->|"OCR 产物与固定模型 Revision"| kArtifacts
        kBatchModels -->|"Chunk Vector"| kVectorStaging
        kArtifacts -->|"正文与过滤元数据"| kBm25Staging
        kArtifacts -->|"Chunk、Citation 与过滤元数据"| kVectorStaging
        kBm25Staging --> kEvaluation
        kVectorStaging --> kEvaluation
        kEvaluation -->|"全部发布门禁通过"| kReadyEvent
        kReadyEvent --> kCandidate
        kCandidate --> kApproval
        kApproval -->|"人工批准"| kRelease
        kRelease -->|"经 Transactional Outbox 发布"| kActivationEvent
        kActivationEvent --> kActivator
        kActivator --> kBm25Ready
        kActivator --> kVectorReady
        kBm25Ready --> kProjectionGate
        kVectorReady --> kProjectionGate
        kProjectionGate -->|"两套投影均准备完成"| kPreparedEvent
        kPreparedEvent -->|"唯一发布提交点"| kActiveState
        kActiveState --> kView
    end

    interaction -->|"上传 / 治理 / 发布"| kControl
    kView --> userResult

    subgraph revoking["紧急撤回链路"]
        direction TB
        rCommand["platform-api · Revocation Control<br/>接收管理员紧急撤回命令"]
        rAuthority["MySQL<br/>提交权威撤回状态与 Outbox Record"]
        rRedis["Redis Online<br/>同步更新 Revocation List"]
        rImmediate["portal-web<br/>返回“撤回已立即生效”"]
        rOutbox["platform-api · Transactional Outbox Publisher"]
        rEvent["Kafka<br/>Revocation / Tombstone Event"]
        rWorker["batch-worker<br/>清理或标记受影响的检索投影"]
        rBm25Projection["Elasticsearch BM25 Projection<br/>撤回内容最终收敛"]
        rVectorProjection["PostgreSQL / pgvector Vector Projection<br/>撤回内容最终收敛"]
        rCleanupEvent["Kafka<br/>ProjectionCleanupCompleted Event"]
        rProjected["platform-api Event Projector → MySQL<br/>记录投影清理结果"]
        rView["portal-web<br/>展示撤回投影已完成"]

        rCommand --> rAuthority
        rAuthority -->|"同步安全路径"| rRedis
        rRedis --> rImmediate
        rAuthority -->|"持久异步路径"| rOutbox
        rOutbox --> rEvent
        rEvent --> rWorker
        rWorker --> rBm25Projection
        rWorker --> rVectorProjection
        rBm25Projection --> rCleanupEvent
        rVectorProjection --> rCleanupEvent
        rCleanupEvent --> rProjected
        rProjected --> rView
    end

    interaction -->|"紧急撤回"| rCommand
    rImmediate --> userResult
    rView --> userResult

    rRedis -.->|"更新同一在线撤回清单"| qRevocation
    kBm25Ready -.->|"由 Active Release ID 选中"| qBm25
    kVectorReady -.->|"由 Active Release ID 选中"| qVector
    rBm25Projection -.->|"删除 / Tombstone 同一 BM25 Projection"| qBm25
    rVectorProjection -.->|"删除 / Tombstone 同一 Vector Projection"| qVector

    classDef frontend fill:#eff6ff,stroke:#1d4ed8,color:#172554;
    classDef java fill:#fff7ed,stroke:#c2410c,color:#431407;
    classDef python fill:#ecfdf5,stroke:#047857,color:#052e16;
    classDef data fill:#fefce8,stroke:#a16207,color:#422006;
    classDef event fill:#f5f3ff,stroke:#6d28d9,color:#2e1065;
    classDef external fill:#f8fafc,stroke:#475569,color:#0f172a;

    class uiEntry,qView,kApproval,kView,rImmediate,rView frontend;
    class apiEntry,qAccess,qContext,qProxy,kControl,kOutbox,kCandidate,kRelease,kActiveState,rCommand,rOutbox,rProjected java;
    class qGuard,qKernel,qValidation,kDispatcher,kBuild,kEvaluation,kActivator,kProjectionGate,rWorker python;
    class qAuthority,qRevocation,qBm25,qVector,kSource,kSourceTx,kCelery,kArtifacts,kBm25Staging,kVectorStaging,kBm25Ready,kVectorReady,rAuthority,rRedis,rBm25Projection,rVectorProjection data;
    class kSourceEvent,kReadyEvent,kActivationEvent,kPreparedEvent,rEvent,rCleanupEvent event;
    class publicGateway,qModels,kBatchModels external;
```
