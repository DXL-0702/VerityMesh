# 企业级多项目知识与智能助手平台技术架构

| 属性 | 内容 |
| --- | --- |
| 文档版本 | 5.4 |
| 基线日期 | 2026-08-11 |
| 文档定位 | 系统技术架构基线 |
| 开发架构图 | [`architecture.md`](architecture.md) |
| 平台定位 | 单企业、多项目、面向外部消费者的统一知识与智能助手平台 |
| 当前范围 | 第一阶段：公开/登录知识服务、统一助手与多项目接入 |
| 主要入口 | 企业统一门户、项目知识页、Web SDK、REST/SSE API |

## 1. 平台定位与架构摘要

### 1.1 平台定位

本平台统一治理单企业旗下所有项目的知识，并向外部消费者提供一致的知识检索和智能问答能力。所有业务系统使用相同的知识治理、发布、检索、身份、会话和助手能力。

平台解决四个核心问题：

- 将企业项目资料转换为经过审核、可追踪、可回滚的对外知识。
- 为消费者提供企业级统一入口和项目内精准问答。
- 为所有项目提供统一的聊天 UI、SDK、API 和运行时能力。
- 通过项目、版本、语言、权限、Release、Session 和 Memory 防止知识串线与越权。

```text
企业项目资料
  -> Source Zone
  -> Governance Zone
  -> Immutable Knowledge Release
  -> Enterprise Portal / Project Page / Web SDK / API
  -> 外部消费者
```

### 1.2 架构摘要

平台采用“统一体验、共享运行时、多项目隔离配置”的架构：

- 门户、项目页和 Web SDK 复用同一个 `assistant-ui`、消息协议和 Citation 模型。
- Project Deployment 固定项目范围并直接进入 Project Assistant，不调用 Global Router。
- 只有 Global Deployment 使用 Global Router，并且只能在当前用户有权访问的项目集合中路由；企业门户是第一阶段的默认 Global 入口。
- 每个项目具有独立的 Assistant Profile、Knowledge Release、Project Thread 和 Memory。
- 第一阶段使用 BM25 + Vector + RRF + Reranker 的混合 RAG；GraphRAG 作为后续按指标引入的检索模式。
- RAG 编排由 Python `assistant-runtime` 内的受约束 Domain Kernel 承担；外部框架不得持有 Scope、Binding、Release、Revocation、Evidence、Citation 或 Grounding 控制权。
- Vue 3 + TypeScript 提供门户、项目页、Web Component 和 TypeScript Client；第一阶段不提供 React Adapter。
- Java/Spring Boot `platform-api` 通过 MySQL 保存业务、身份、授权、Session、Release 和审计真相；Python 只承担在线 AI 与离线知识处理，不直接拥有权威业务状态。
- MySQL 保存业务权威状态，OSS 保存原始、治理和不可变知识资产；PostgreSQL/pgvector 保存可重建 Vector Projection，阿里云 Elasticsearch 保存可重建 BM25 Projection。
- 知识必须先治理再发布；普通更新通过新 Deployment Revision 原子激活，敏感内容通过 Revocation List 紧急阻断。
- 平台账号、OAuth Scope 和 ProjectGrant 分离；OAuth Scope 不代替项目业务权限。
- 所有模型通过 Model Access Layer 统一注册、路由、审计、限额和降级。

### 1.3 第一阶段范围

第一阶段交付：

- 企业统一门户和标准项目知识页。
- 统一聊天 UI、Web Component、TypeScript SDK、REST/SSE API。
- 匿名访问、平台统一登录和项目授权知识。
- 项目、版本、语言、Access Segment 和共享知识包治理。
- 上传、批量导入、签名 Push API、增量索引、发布、回滚和撤回。
- Project Assistant、Global Router、项目 Memory 隔离和跨项目 Evidence 聚合。
- 混合检索、Citation、拒答、Claim Grounding 和发布评测。

第一阶段不包含：

- 用户会话或上传内容自动转为正式知识。
- iOS/Android 原生 SDK。
- GraphRAG、Milvus、Weaviate、Elasticsearch Dense Vector、Flink、私有模型和多地域灾备的生产依赖。

## 2. 用户角色与产品形态

### 2.1 用户与访问模式

| 角色 | 可访问内容 | 主要能力 |
| --- | --- | --- |
| 匿名消费者 | `PUBLIC` | 搜索、问答、临时会话、反馈 |
| 平台登录用户 | `PUBLIC`、`PLATFORM_AUTHENTICATED` | 会话同步、收藏和登录级知识 |
| 项目授权用户 | 前述内容及 `PROJECT_AUTHORIZED` | 项目差异化知识 |
| 项目内容编辑者 | 本项目 Source/Governance 数据 | 导入、治理、编辑和提交审核 |
| 项目内容审批者 | 本项目 Release Candidate | 审核、发布、回滚和紧急撤回；生产发布与提交者职责分离 |
| 平台管理员 | 企业级平台资源 | 项目、身份策略、Deployment、评测、配额和审计 |
| 宿主项目研发 | Deployment 允许的接口 | Web SDK 和服务端 API 集成 |

动态业务数据在第二阶段通过经过授权的项目业务 API 按需查询，不进入通用知识索引或长期 Memory。

### 2.2 企业统一门户

统一门户提供：

- 企业项目目录和项目介绍。
- 跨项目统一搜索和 Global Assistant。
- 按项目、版本、语言和知识类型筛选。
- 登录、会话历史、收藏和反馈。
- 每条答案的项目归属、版本、引用和知识生效时间。

门户先从用户可访问的项目集合中生成候选项目。候选不明确时要求用户选择；只有用户明确提出或确认跨项目范围后，才执行跨项目 Evidence 聚合。

### 2.3 项目知识页

每个项目使用标准化知识页面：

- 项目介绍、版本选择和知识分类。
- 帮助中心、FAQ、操作指南、API 文档和版本公告。
- 项目范围搜索和统一聊天框。
- 登录后差异化知识、会话、收藏和反馈。

项目页面的 Session 固定 `project_id`。用户询问其他项目时返回 `scope_mismatch / handoff_required`，由 UI 跳转统一门户或创建新的 Project Session，不能扩大当前 Session 或复用当前项目 Memory。

### 2.4 项目嵌入与开放接口

平台提供：

- Web Component：框架无关的聊天组件。
- TypeScript Client：管理 Session、Thread、消息、上下文和反馈。
- Vue 3 Portal：直接复用 `assistant-ui` 核心组件和 TypeScript Client；第一阶段不建设其他框架 Adapter。
- REST/OpenAPI：服务端和非 Web 客户端的事实契约。
- SSE：路由、状态、已验证回答片段、Citation 和错误事件。

第一阶段外部 Embed 必须有宿主后端参与 Token 签发，不提供携带长期 API Key 的纯前端嵌入模式。

### 2.5 统一助手体验

统一的是核心 UI、协议和行为，不是所有项目使用完全相同的品牌视觉。项目可以配置品牌色、欢迎语和推荐问题，但必须复用以下能力：

- 消息、加载、失败、拒答和降级状态。
- Citation、项目范围、版本和 Access Segment 展示。
- 项目切换、Session 换版和身份过期提示。
- 反馈、重试、复制和会话恢复。

Project Session 显示单一项目范围：

```text
当前范围：项目 A
当前版本：v2.3
回答语言：zh-CN
知识权限：公开 / 平台登录 / 项目授权
```

Global Session 显示“企业全部项目”或“涉及 N 个项目”。不同项目的版本和权限放在具体 Claim/Citation 中，不能用一个全局版本标签代表全部项目。

## 3. 架构原则与关键决策

### 3.1 架构原则

1. 外部助手只能检索 Published Knowledge Zone。
2. 项目、版本、语言和权限 Scope 由服务端计算，浏览器和模型不能扩大。
3. Knowledge Release、Assistant Profile Version 和 Deployment Revision 不可变。
4. 项目是知识、会话、Memory、路由和评测的默认隔离边界。
5. Memory 只用于对话连续性，事实必须来自可引用 Evidence。
6. 固定项目请求走最短路径，不承担 Global Router 成本。
7. 控制面、知识面和数据面分离，离线故障不直接拖垮在线问答。
8. MySQL 保存业务权威状态，OSS 保存内容事实；PostgreSQL/pgvector、Elasticsearch 和后续图索引均为可重建投影。
9. 安全不变量优先于可用性；权限或撤回状态不明时 fail closed。
10. 后期组件必须由质量、容量、成本或合规指标触发，不能按预期规模提前堆叠。

### 3.2 关键架构决策

| 决策 | 采用方案 | 不采用方案 | 原因 |
| --- | --- | --- | --- |
| 助手形态 | 共享 Runtime + Global/Project Profile | 每个项目独立部署 Agent | 减少重复建设，同时保留项目隔离 |
| 项目路由 | Project 直达；Global 才调用 Router | 所有请求都通过强模型 Router | 降低延迟、成本和越权风险 |
| 检索基线 | BM25 + Vector + RRF + Reranker | 一期直接 GraphRAG | 便于建立可测量质量基线，覆盖多数文档问答 |
| RAG 编排 | `assistant-runtime` 内受约束 RAG Domain Kernel | 由 LangChain、LangGraph 或 MaxKB 持有主控制面 | 保持 Scope、Release、Evidence、Citation 和 Grounding 的领域边界，并让检索链路可测量、可替换 |
| Model Access 边界 | 领域任务端口 + Provider 能力适配两层结构 | 领域核心直接依赖供应商 SDK 或框架类型 | 允许适配层采用 LangChain 或直连 SDK，同时隔离供应商协议、版本和故障语义 |
| 业务与控制元数据 | MySQL 权威 | 检索库承载业务真相 | Java 事务、审计、权限、会话和发布状态需要单一关系型所有者 |
| 首期文本检索 | 阿里云 Elasticsearch 8.17 只承载 BM25、过滤、正文和高亮 | Elasticsearch 同时复制 Dense Vector | 与 PostgreSQL/pgvector 分工，避免向量双写和产品私有融合语义 |
| 首期向量检索 | PostgreSQL + pgvector 承载 Vector Projection | Elasticsearch 与 PostgreSQL 永久双存向量 | 符合 Python RAG 数据边界，两路召回可独立评测、降级和替换 |
| 知识发布 | Immutable Release + Atomic Activation | 在线索引原地修改 | 可复现、可评测、可回滚 |
| 身份 | 统一 Identity Service + ProjectGrant/ABAC | 仅靠 OAuth Scope 表达业务权益 | 分离身份认证、Client 能力和项目业务权限 |
| Memory | Global 偏好与 Project Conversation 分离 | 全局共享长期 Memory | 防止跨项目事实和权限上下文污染 |
| 回答流 | Claim 缓冲、验证后再 SSE | 原始 Token 先流出再校验 | 未验证事实一旦输出无法可靠撤回 |
| 开发运行时 | Vue 3 + TypeScript 前端；Java/Spring Boot 业务平台；Python AI Runtime/Worker | 单语言全栈或在 Java/Python 两侧重复领域规则 | 前端体验、业务事务与 AI/检索生态各自使用合适运行时，领域真相保持单一所有者 |
| 服务拆分 | `portal-web`、`platform-api`、`assistant-runtime`、`batch-worker` 四个 Deployment；Java 内部保持模块化单体 | 一期全面微服务或 Java/Python 混合持有同一领域状态 | 保持扩缩容和故障边界，避免在首期引入无价值网络跳数与双重领域实现 |
| 异步批处理 | MySQL Outbox + Kafka 负责可靠领域事件；Python Celery 负责任务执行 | 直接从 Java 写入 Celery Redis 私有消息，或将 Celery 作为业务状态机 | Kafka 可重放且与领域事件一致；Celery 适合 Python 批量并发、重试和任务编排 |
| Redis 角色 | 在线缓存与 Celery Broker/短期 Result 逻辑隔离 | 共用同一淘汰、容量和权限边界的 Redis 命名空间 | 防止批任务堆积、淘汰策略和访问权限干扰在线 Session、撤回和限流 |

## 4. 总体架构

### 4.1 三平面架构

```text
                     Control Plane
企业管理员 / 项目管理员
  -> Project & Version Management
  -> Knowledge Governance
  -> Assistant Profile & Deployment
  -> Access Policy / ProjectGrant / OAuth Client
  -> Release / Evaluation / Rollback / Audit

                      Data Plane
匿名消费者 / 登录消费者 / 宿主项目
  -> Portal / Project Page / Web SDK / API
  -> Public API Gateway
  -> Identity & Authorization
  -> Scope Resolver
  -> Project Assistant / Global Router（仅 GLOBAL）
  -> Hybrid Retrieval / Evidence Hub
  -> Prompt Builder / Model Access / Grounding Validator
  -> Validated Answer / Citation / Feedback

                    Knowledge Plane
项目资料
  -> Source Zone
  -> Governance Zone
  -> Knowledge Revision
  -> Immutable Knowledge Release
  -> Serving Index
```

### 4.2 平面职责

| 平面 | 主要职责 | 不承担的职责 |
| --- | --- | --- |
| Control Plane | 项目、权限策略、治理、Assistant、Deployment、评测、发布和审计 | 不承载高频消费者问答 |
| Knowledge Plane | 接入、解析、OCR、DLP、Chunk、Embedding、索引、Release 和撤回 | 不接受消费者直接查询 |
| Data Plane | 身份解析、Scope、Router、检索、回答、会话、Citation、反馈和限流 | 不访问 Source/Governance Zone |

### 4.3 核心组件

| 逻辑组件 | 职责 | 首期运行时与部署方式 |
| --- | --- | --- |
| `portal-web` | 企业门户、项目知识页和统一聊天 UI | Vue 3 + TypeScript + Vite Web 服务 |
| `assistant-ui` | Web Component、Citation、范围和项目切换组件；TypeScript Client | Vue 3 `defineCustomElement` 与 TypeScript 构建包，不是独立 K8s 服务 |
| `platform-api` | `public-api`、`knowledge-control`、`identity-access`、Session/Thread、Release、审计与 Transactional Outbox | Java/Spring Boot 模块化单体；在线 API 服务 |
| `assistant-runtime` | 在不可变 Project Execution Context 内执行 Scope、Router、QueryPlan、Evidence、受约束 RAG Domain Kernel、Citation、Grounding 与已验证 SSE 事件 | Python/FastAPI 在线 AI 服务，按请求/SSE 扩容；不直接写入权威业务状态 |
| `model-access` | 逻辑模型、供应商路由、配额、审计、降级与 Provider Adapter | `assistant-runtime` 内 Python 模块；第一阶段使用原生 SDK/REST Adapter |
| `batch-worker` | Kafka 任务分发、Celery 执行、解析、OCR、分类、Chunk、Embedding、批量索引和评测 | Python/Celery Worker 池；按 Queue 等待时间与 Kafka Lag 扩缩容 |

首期固定为 `portal-web`、`platform-api`、`assistant-runtime` 和 `batch-worker` 四个 Deployment。`platform-api` 内部模块不因逻辑职责不同而提前拆成服务；`assistant-runtime` 和 `batch-worker` 因在线/离线资源、依赖和故障边界不同保持独立。

## 5. 领域模型与版本模型

### 5.1 资源层级

```text
Enterprise
  |- SharedKnowledgePackageVersion
  |- GlobalAssistantProfileVersion
  |- GlobalDeployment
  |    `- GlobalDeploymentRevision
  `- Project
       |- ProjectVersion
       |- KnowledgeSpace
       |- KnowledgeRelease
       |- ProjectAssistantProfileVersion
       `- ProjectDeployment
            `- ProjectDeploymentRevision
```

- `Enterprise`：企业最高数据归属边界。
- `Project`：独立产品、网站、应用或业务项目。
- `ProjectVersion`：知识适用的对外产品版本。
- `KnowledgeSpace`：知识归属、治理和发布边界。
- `KnowledgeRelease`：不可变的已发布知识快照。
- `AssistantProfileVersion`：不可变的 Router、Prompt、Tool、Safety 和逻辑模型策略。
- `Deployment`：稳定的渠道与环境入口，持有当前活动 Revision 指针。
- `DeploymentRevision`：Assistant、知识绑定、身份策略、渠道、Origin 和配额的不可变运行版本。

### 5.2 知识对象模型

```text
KnowledgeSpace
  -> SourceConnector
  -> SourceObject
       -> SourceRevision
  -> KnowledgeItem
       -> LocaleVariant
            -> KnowledgeRevision
  -> KnowledgeRelease
       -> ReleaseEntry
```

`KnowledgeItem` 是跨语言稳定身份，`LocaleVariant` 保存语言版本，`KnowledgeRevision` 是治理后的不可变内容版本。

知识发布维度至少包含：

```text
project_id
project_version
locale
audience_policy
security_domain
effective_from / effective_to
```

### 5.3 Assistant Profile

Assistant Profile 定义：

- Global 或 Project Scope。
- 默认 Project Version、Locale 和回退规则。
- 允许选择的 Knowledge Space、共享知识包和 Access Segment。
- Router、检索、回答、拒答和 Grounding 策略。
- Prompt、逻辑模型、Token 预算和允许工具。
- 欢迎语、推荐问题和品牌配置。

Assistant Profile 只定义知识选择规则，不直接保存具体 Knowledge Revision。最终解析出的 Revision、共享包和索引版本由 Knowledge Release/Binding 持有，避免 Profile 变更绕过发布评测。

### 5.4 Knowledge Binding 与 Deployment

```text
DeploymentRevision
  -> scope_mode                       # PROJECT / GLOBAL
  -> project_id                       # PROJECT 必填
  -> assistant_profile_version_id
  -> knowledge_binding_set_id
  -> identity_policy_version
  -> channel / environment / origins / quota / theme

KnowledgeBindingSet
  -> ProjectExecutionBinding[]
       project_id
       project_version
       locale
       access_segment
       project_assistant_profile_version_id
       knowledge_release_id
```

Deployment Revision 的 Assistant Profile 定义入口行为，Binding 中的 Project Assistant Profile 定义对应项目的执行策略。Project Deployment 的 Binding Set 只能包含当前项目，且入口与 Binding 指向同一 Project Assistant Profile；Global Deployment 使用 Global Assistant Profile 负责路由与聚合，并由各 Binding 指向目标 Project Assistant Profile。

Locale 是 Binding 解析维度，使用 BCP 47 标签，例如 `zh-CN`、`en-US`。解析顺序为：用户明确选择 -> 用户资料 -> Project 设置 -> `Accept-Language` -> Enterprise 默认。Citation 保留源语言，回答可以使用目标语言；翻译摘要不能冒充原文引用。

活动 Deployment 指针在每个 `deployment_id + environment` 下只指向一个已验证 Revision。Project Session 固定一个 Project Execution Binding；Global Session 固定 Global Deployment Revision，并为各项目建立独立 Project Execution Context。

### 5.5 Conversation、Session 与 Thread

- `Conversation`：用户看到的长期聊天历史容器，可跨多个 Runtime Session。
- `AssistantSession`：短期、不可变的授权与执行容器，固定 Deployment Revision 和 Token。
- `ProjectThread`：Global Session 内某个项目的独立对话与 Memory 边界。
- `MessageExecutionContext`：每条消息的不可变执行快照，固定 Thread、Binding、Release、授权版本和 Plan 版本。

Project、Version、Locale、Access Segment、Profile 或 Deployment Revision 改变时创建 Successor Session，不能原地修改旧 Session。Global Session 不保存可被并发请求修改的“当前项目”字段。

## 6. 知识生命周期与增量索引

### 6.1 三段式数据边界

```text
Source Zone
原始项目资料，仅内部治理服务访问
        |
        v
Governance Zone
解析、清洗、脱敏、分类、审核和知识编辑
        |
        v
Published Knowledge Zone
不可变 Knowledge Release，外部助手唯一允许检索的数据区
```

内部资料和外部知识不能只靠一个 `status` 字段共用同一检索集合。Source/Governance Index 与 Published Serving Index 使用独立凭证、网络策略和 Security Domain。

### 6.2 第一阶段数据边界

允许进入治理和发布流程的数据：

- 项目介绍、产品说明、帮助中心和用户手册。
- FAQ、故障排查、操作指南和已批准培训材料。
- API、SDK、功能文档和版本公告。
- 服务政策、已审核案例和允许对外的共享企业知识。
- 内部需求、设计和运营资料，但必须先进入 Source Zone，再进入 Governance Zone，经脱敏、改写和审批后发布。

第一阶段不得进入对外 Serving Index：

- 需要实时读取或依赖对象级授权的动态业务数据。
- 个人敏感信息、未经审核的交互记录和业务记录原文。
- 源代码、密钥、凭证和内部网络信息。
- 可见范围不明确的草稿。
- 消费者聊天记录和上传内容。

所有上传、批量导入、签名 Push API 和 Connector 只能写入 Source Zone，不能直接写入 Governance Zone 或 Published Serving Index。Connector 仅在数据源清单、网络授权和业务负责人明确后逐个接入，不作为第一阶段的无边界通用采集能力。

### 6.3 知识发布流程

```text
Source Revision
  -> 隔离接收
  -> Malware / Secret / PII Scan
  -> Parse / OCR / Deduplicate
  -> Project / Version / Locale / Access Policy
  -> Governance Review
  -> Knowledge Revision
  -> Release Candidate
  -> Staging Index
  -> Retrieval / Answer / ACL / Leakage Evaluation
  -> Approval
  -> Knowledge Release
  -> Deployment Revision Canary
  -> Atomic Activation
```

Knowledge Release 至少固定：

- Knowledge Revision 列表。
- Shared Knowledge Package Version。
- Project Version、Locale、Audience Policy 和有效期。
- Analyzer Profile、术语/同义词字典、Chunker、Embedding Space、RRF、Reranker、BM25 Index Schema Version 和 Vector Projection Schema Version。

第一阶段使用自有确定性结构感知 Chunker，按 prose、FAQ、API、Release Notes、Policy、Table 和 Code 使用版本化 Profile。Chunk 必须保留原文字符 Offset、标题和章节路径；固定递归切分只作基准，Embedding Semantic Boundary 只作质量挑战者。精确重复使用规范化内容 SHA-256 识别；MinHash/LSH 近重复只生成治理审核信号，不跨 Project、Version、Locale 或 Access Segment 自动合并、删除或共享权限对象。

### 6.4 增量索引

```text
SourceRevision / Tombstone
  -> Transactional Outbox
  -> Kafka Durable Event Log
  -> Python Batch Dispatcher
  -> Celery Queue / Isolated Redis Broker
  -> 只重算受影响文档的解析、Chunk、Embedding 和权限投影
  -> OSS Chunk Manifest
  -> Elasticsearch BM25 Staging Projection
  -> PostgreSQL/pgvector Vector Staging Projection
  -> 增量评测
  -> Knowledge Release + Knowledge Binding Set
  -> MySQL Active Release / Deployment Revision 原子切换
```

- 每个事件包含 `event_id`、`source_revision_id`、Schema Version 和幂等键。
- Consumer 支持重放、退避、Checkpoint 和 DLQ。
- Java 只通过 Outbox 发布领域事件，不直接写入 Celery Redis 私有任务消息；Python Dispatcher 将已消费事件转换为 Celery JSON Task。
- Celery 的 chain/group/chord 只负责任务执行、并发和重试；任务状态、Release 水位、激活和回滚真相仍在 MySQL 与 Control Plane。
- 更新、删除和权限收窄都生成新 Revision；删除使用 Tombstone 清理 BM25、向量、缓存和后续图索引。
- MySQL 保存任务状态、发布水位与 Active Release；PostgreSQL/pgvector 和 Elasticsearch 只保存可重建的 Serving Projection。
- “实时更新”定义为内容通过必要审批后，P95 五分钟内完成增量构建和原子激活。
- 全量重建与在线增量使用独立队列和资源池，不能互相阻塞。

### 6.5 Deployment 激活、回滚与 Session 换版

普通发布先完整构建同一 `knowledge_release_id` 的 BM25 与 Vector Projection，并在数量、内容 Hash、ACL 和评测一致、两套 Watermark 均指向同一 Release/Manifest 后，由 Java 在 MySQL 单事务中激活新 Deployment Revision。MySQL Active Release 是唯一发布提交点；Elasticsearch Alias 只可用于运维优化，不能替代该指针。回滚通过 MySQL 重新指向仍保留的上一已验证 Revision 完成。Release 激活不改变正在执行的消息上下文，也不会在回答生成中途换版：

1. 新 Deployment Revision 激活后向相关 Session 发送 `revision_available`。
2. 下一条消息边界创建固定新 Revision 的 Successor Session，并轮换 Session Access Token。
3. UI 发送 `session_replaced` 并显式提示知识版本已更新。
4. Successor Session 继续归属原 Conversation，但旧 Evidence 不进入新 Prompt。
5. Assistant Session 执行租约初始最长 2 小时；超期请求必须换版。

敏感内容先进入在线 Revocation List，立即禁止召回，再补正式 Knowledge Revision 和 Release。紧急知识撤回和当前 Grant 撤销始终优先于固定 Revision，必须立即生效。

### 6.6 企业共享知识

- 企业品牌、公共政策等发布为版本化 Shared Knowledge Package。
- 项目显式绑定共享包版本，验证后升级，不自动跟随最新内容。
- 项目知识与共享知识冲突时，Release 明确优先级。
- 紧急安全撤回可以绕过常规升级流程。
- Shared Package 更新与项目 Release 使用相同评测、灰度和回滚机制。

## 7. 身份与访问控制架构

### 7.1 身份与授权分层

平台 Identity Service 提供或集成统一消费者账号，并负责 OIDC/OAuth、ProjectGrant、Authorization、Session 和 Embed Token。具体采用现有账号体系、托管 CIAM 或独立部署，应在身份专项设计中确定；本架构只固定身份认证、Client Scope 和项目业务权限必须分层。

```text
Identity Authentication
  -> 用户是谁

OAuth Scope
  -> 当前 Client 可调用什么能力

ProjectGrant / ABAC
  -> 用户能否访问某项目及其差异化知识

Object Authorization
  -> 用户能否访问具体 Session / Message / Citation
```

有效访问范围始终由服务端计算：

```text
Deployment 允许上限
  ∩ Token Scope
  ∩ 当前有效 ProjectGrant / ABAC
  ∩ Knowledge Access Policy
```

### 7.2 Access Segment

| Access Segment | 含义 | 判定依据 |
| --- | --- | --- |
| `PUBLIC` | 无需登录即可访问 | Deployment 和发布策略 |
| `PLATFORM_AUTHENTICATED` | 任意有效平台账号可访问 | 当前平台 Session |
| `PROJECT_AUTHORIZED` | 仅项目已授权用户可访问 | 有效 ProjectGrant / ABAC |

浏览器传入的 Access Segment 只能作为提示，不能作为授权依据。后续可以增加 `ENTITLED_CUSTOMER`、`PARTNER` 等服务端映射 Segment。

### 7.3 平台登录与项目授权

登录使用 OIDC Authorization Code + PKCE `S256`。回调校验 `state`、`nonce`、Issuer、JWT `aud`、签名和精确 Redirect URI；授权码一次性使用，登录后轮换 Session ID。

平台登录不代表自动获得所有项目知识。访问项目差异化知识时：

1. 校验当前平台 Session 和风险状态。
2. 查询 ProjectGrant、授权版本和有效期。
3. 需要委托项目业务 API 时执行增量 OAuth Consent；只访问知识时由 ProjectGrant/ABAC 判定。
4. Authorization Service 计算有效 Access Segment 和能力 Scope。
5. Assistant Session 固定权限上限和 `authz_epoch`。
6. 每次搜索、消息和历史读取重新校验当前授权；撤权立即收窄，扩权创建 Successor Session。

### 7.4 Cookie 与跨站 SSO

标准项目知识页优先部署在统一平台 Origin，例如：

```text
https://knowledge.enterprise.example/projects/{project_id}
```

- 使用 `__Host-`、`Path=/`、`HttpOnly + Secure + SameSite=Lax` 的 Host-only Session Cookie。
- Cookie 只保存随机 Session ID，不保存 Access Token、Refresh Token、项目权限或敏感信息。
- `__Host-` Cookie 不能设置 `Domain`，不同子域或顶级域不能共享同一个 Cookie。
- 独立域名通过 Identity Provider 的 OIDC SSO 创建本地 Session。
- Refresh Token 由服务端加密保存，执行旋转、复用检测和授权链撤销。
- 状态修改请求执行 CSRF 防护；登录支持设备管理、退出、Session Fixation 防护和风险检测。

### 7.5 跨域 Embed

跨域 iframe/Web SDK 不依赖第三方 Cookie：

```text
宿主后端认证访客
  -> Deployment Client 认证
  -> 可信用户断言或标准 Token Exchange（登录用户）
  -> Identity Service 计算 Subject、Project、Origin、Scope 和 authz_epoch
  -> 一次性 Embed Bootstrap Token
  -> Web SDK 创建 Assistant Session
  -> 返回 Session-bound 短期 Access Token
```

- Client Credentials 只证明宿主应用身份，不能证明最终用户身份。
- Project、Deployment、Origin 和最大 Scope 从服务端 Client 配置派生。
- 项目自有账号必须配置受信任 `issuer + audience + JWKS + subject mapping`。
- Bootstrap Token 绑定 `typ`、Client、Subject、Deployment Revision、Origin、`authz_epoch`、`exp` 和 `jti`。
- Token 不进入 URL、日志、Local Storage 或 JavaScript 可读 Cookie。
- 精确配置 CORS、CSP `frame-ancestors` 和 `postMessage` 双向 Origin 校验；高风险部署可使用 DPoP。

### 7.6 凭证类型与撤权

| 凭证 | 用途 | 核心约束 |
| --- | --- | --- |
| Portal Session Cookie | 同源门户/BFF 登录 | Host-only、不透明、JavaScript 不可读 |
| Deployment Client Credential | 宿主后端身份 | 不能代表最终用户，优先 private_key_jwt 或 mTLS |
| Embed Bootstrap Token | 创建一次 Assistant Session | 单用途、短 TTL、JTI 防重放、绑定 Origin |
| Assistant Session Access Token | 调用当前 Session API | 绑定 Session、Subject、Client、Revision 和 authz_epoch |
| OAuth Access Token | 调用项目业务 Resource Server | 独立 `typ`、JWT `aud` 和 Scope |

每个 Resource Server 必须校验凭证 `typ` 与精确 Audience，并拒绝其他 Token 类型，防止 Bootstrap Token、Session Token、Client Token 和业务 OAuth Token 混用。

退出、Grant 撤销、Client 撤销或风险封禁必须级联失效 Token、Redis Session 和授权缓存。历史消息、Citation 和收藏每次读取均按当前权限重新校验，不能因过去有权而永久可见。

门户匿名访客由同源 BFF 创建 HttpOnly Guest Session。匿名用户登录后不自动合并匿名 Conversation，除非用户明确同意。

## 8. Assistant Runtime 与检索架构

### 8.1 请求路径

```text
Unified Chat UI
  -> Session / Deployment Scope Resolver
       |- PROJECT
       |    `- Project Assistant -> ProjectQueryPlan -> Retrieval -> Evidence Hub
       |
       `- GLOBAL
            -> Authorized Project Candidate Set
            -> Global Router
                 |- Project A Retrieval Context -> EvidencePacket A
                 |- Project B Retrieval Context -> EvidencePacket B
                 `- Project C Retrieval Context -> EvidencePacket C
            -> Global Evidence Aggregator
  -> Prompt Builder
  -> Generator，按 Claim 缓冲
  -> Grounding Validator
  -> Validated Claim Stream
```

Project Assistant 是受约束的配置化执行单元，不是可任意自治或互相调用的自由 Agent。跨项目默认只产生多个结构化 EvidencePacket，Global Aggregator 不得读取 Project Conversation Memory，最后只执行一次全局生成。

### 8.2 Scope Resolver 与 Global Router

Scope Resolver 是确定性安全组件，先校验 Token、Session、Deployment Revision、当前 Grant 和 Knowledge Binding Set，再计算本次允许使用的项目集合。

- `PROJECT` Deployment 直接进入固定 Project Assistant，Global Router 模型调用数为 0。
- `GLOBAL` Deployment 只允许 Router 在服务端已授权候选集中选择项目。
- Router 输出符合 JSON Schema，并由策略引擎复核 Project ID、Version、任务类型和最大 fan-out。
- Prompt 中的“不得越权”不能替代服务端 Policy 校验。

Global Router 只负责项目识别、澄清和跨项目拆分，不直接回答项目事实、访问项目原始 Memory 或调用写工具。

路由采用三层漏斗：

1. 规则：用户显式选择、项目别名、产品名和门户上下文。
2. 轻量分类：项目和常见意图识别。
3. 强模型 Router：多项目、歧义和复杂查询兜底。

项目数较多、无法把授权项目描述放入 Router 上下文时，可以评估项目目录 BM25/Embedding 候选召回。该能力必须单独验证权限过滤、更新水位和候选召回率后再启用，不是第一阶段固定依赖。

Router 区分：

- `DISAMBIGUATION_PROBE`：只用于选择项目，不生成混合事实答案。
- `CROSS_PROJECT_ANSWER`：只有用户明确提出或确认多项目范围后才聚合。

首期跨项目 fan-out 最大为 3；每个项目分支具有独立 Deadline 和并发上限。问题涉及更多项目时要求用户缩小或确认范围，不能静默截断。部分分支失败返回 `partial_coverage`、实际覆盖项目、版本和失败原因。

被选中的项目必须在各自 Project Execution Context 内独立召回和精排，不能绕过项目、Release 和 Access Segment 边界直接对全项目混合索引裸搜。

### 8.3 GlobalRoutePlan 与 ProjectQueryPlan

- `GlobalRoutePlan`：只由 Global Router 生成，负责授权候选中的项目选择、澄清和跨项目拆分。
- `ProjectQueryPlan`：接收不可变 Project Execution Context，只决定本项目内的检索模式、过滤和证据需求。

```text
Original User Message
  -> 规则归一化与 Prompt Injection 检测
  -> 轻量意图、实体和检索模式识别
  -> 复杂问题才调用强 Planner
  -> JSON Schema ProjectQueryPlan
  -> Retrieval / Tool Plan
  -> Prompt Builder 组装 Policy、Memory、Evidence 与原始问题
```

ProjectQueryPlan 至少包含：

```text
intent
normalized_query
locale
retrieval_mode
filters
required_evidence
clarification_needed
```

用户原始消息不可变保存并传给最终模型。`normalized_query` 只用于检索。Planner 不能生成任意 SQL、Index、Project ID、Model ID 或 Tool 参数。Prompt Builder 使用版本化模板确定性组装，不额外调用模型做通用提示词润色。

### 8.4 Memory 隔离

| Memory | 允许保存 | 禁止保存 |
| --- | --- | --- |
| Global Session Memory | 语言、显示偏好、路由历史和明确选择的项目 | 项目事实、文档摘要和受限 Evidence |
| Project Conversation Memory | 当前项目指代、最近问题、Evidence ID 和对话上下文 | 其他项目内容和跨项目综合事实 |
| User Preference Memory | 用户主动保存的非敏感偏好 | 未经同意推断的敏感画像 |

Project Memory Key 至少包含：

```text
user_or_guest_id
project_id
project_version
deployment_revision_id
assistant_profile_version_id
knowledge_binding_set_id
knowledge_release_id
conversation_thread_id
locale
access_context_hash
```

每条消息固定 `session_id`、`project_thread_id`、`expected_thread_version`、Project Execution Binding、Release、`authz_epoch` 和 Plan Version。Thread 使用乐观并发控制和幂等键，防止双标签页、乱序重试和项目切换串写 Memory。

活跃 Session 和短期 Memory 保存于 Redis；登录用户明确保存的 Conversation 加密写入 MySQL Conversation Store。匿名会话默认 24 小时。Conversation 不作为知识索引数据源。

### 8.5 项目切换与跨项目结果

只有 Global Session 允许创建多个 Project Thread：

```text
Router 判断目标项目
  -> 当前授权校验
  -> 从 Knowledge Binding Set 解析 Project Execution Context
  -> 创建或重新鉴权后恢复 Project Thread
  -> UI 显式展示项目切换
```

跨项目答案不写回任一 Project Memory，只保存为 Conversation Record 类型的 `GlobalResultReference`。该记录至少包含 Owner、逐 Claim、Evidence ID、来源 Project/Release/Access Context、创建时间和 TTL。

GlobalResultReference 不能作为后续事实 Evidence。每次读取重新校验全部来源权限；某个 Grant 或 Release 失效时按 Claim 遮蔽，无法安全拆分时禁用整条记录。

### 8.6 混合检索

```text
Project / Release / Locale / Access Segment Filter
  -> BM25 Top 50 and Vector Top 50 in parallel
  -> Domain RRF，rank_constant = 60，Top 50
  -> Reranker Top 10
  -> Evidence Hub
```

第一阶段由阿里云 Elasticsearch 8.17 承载 BM25、正文、过滤和高亮，由 PostgreSQL/pgvector 承载 Vector Recall；不在 Elasticsearch 保存 Dense Vector。Project、Release、Locale、Access Segment、有效期和撤回状态必须以同一 Execution Context 在两路 Top-K 前生效，Vector 分支还必须校验 Embedding Space 和 Configuration Filter，不能先裸搜再过滤。

RRF 由受约束 Domain Kernel 对 Elasticsearch 与 PostgreSQL/pgvector 返回的两路独立 Rank 执行，按稳定 `chunk_id` 去重并保留原始 Rank/Score；不使用跨库分数直接相加或搜索产品私有混合分数替代统一融合合同。首期默认 `BM25 Top 50 + Vector Top 50 -> RRF(k=60) Top 50 -> Reranker Top 10`，参数调整必须使用同一密封评测集重新验证。

Vector Projection 至少保存 `chunk_id`、`knowledge_release_id`、Project/Version、Locale、Access Segment、有效期、Embedding Space/Model Revision、内容 Hash、最小 Chunk 正文、Citation 描述和向量。BM25 与 Vector Projection 可以重复保存正文和过滤字段，但只能从同一不可变 Chunk Manifest 构建；这种冗余用于独立召回与降级，不赋予检索库存储业务真相的资格。在线链路不在 MySQL、PostgreSQL 与 Elasticsearch 之间执行跨库 Join。

中文 BM25 主候选使用与 Elasticsearch 8.17 兼容的 IK Analysis：索引采用 `ik_max_word`，查询采用 `ik_smart`；英文和中英混合内容保留 `standard` 多字段，API、路径、代码和产品标识符保留 `keyword/whitespace` 多字段。项目术语、同义词和停用词按 Knowledge Release 版本化，禁止全局热更新改变旧 Release 的检索语义。

Vector Recall 不可用、Embedding Revision 不匹配或 Query 超限无法拆分时，执行 `BM25 Top 50 -> 可用 Reranker -> Top 10`；Reranker 不可用、超时或响应无效时回退 RRF Top 10，不在在线 Deadline 内盲目重试。Reranker Score 只用于排序，不能替代 Evidence 支持关系、拒答阈值或 Grounding 判断。Evidence Hub 最终复核项目、Release、Access Segment、有效期、撤回状态和 Citation URL。

### 8.7 回答与幻觉控制

```text
Evidence Hub
  -> Prompt Builder
  -> Generator，按完整句子或 Claim 缓冲
  -> Grounding Validator
  -> Validated Claim Stream / Evidence-only / Refusal
```

Memory 隔离只能防止上下文串库，不能单独消除幻觉。回答还必须满足：

- 只使用 Published Knowledge Release 和经过验证的业务工具结果。
- Prompt 明确区分 Policy、Memory 和 Evidence，Memory 不能作为事实证据。
- 低证据覆盖、路由低置信度或知识过期时澄清或拒答；证据冲突时并列展示来源差异，不能由生成模型擅自合并为单一事实。
- 每个事实 Claim 返回 Project、Version、Citation 和知识时间。
- Generator 按完整句子/Claim 缓冲，只有 Grounding Validator 通过后才能生成用户可见 `message_delta`。
- 已验证 Claim 在输出前继续执行内容安全、引用覆盖、PII、凭证和受限信息复核；拦截原因只写入审计，不向消费者回显内部策略。
- Validator 失败、超时或异常时不泄露原始文本；执行一次受限改写，仍失败则返回 Evidence 或拒答。

### 8.8 Model Access Layer

```text
Model Registry / Routing Policy / Audit / Cost
  |- LLM Gateway：Router、Planner、Generator
  |- Inference Gateway：Embedding、Reranker、Grounding、轻量分类
  `- Batch Dispatcher：OCR、批量 Embedding、抽取和后期图摘要
```

第一阶段逻辑模型：

| 逻辑模型 | 用途 |
| --- | --- |
| `embedding-primary` | 项目知识和查询向量化 |
| `reranker-primary` | Evidence 候选精排 |
| `router-primary` | Global 复杂路由兜底 |
| `query-planner-primary` | 复杂 ProjectQueryPlan 兜底 |
| `generator-primary` | 最终回答 |
| `grounding-validator-primary` | Claim-Evidence 支持关系复核 |
| `pii-detector` | 治理和模型出站敏感信息检测 |
| `ocr-primary` | 图片、PDF 和表格解析 |

Router、Planner 和 Generator 采用独立逻辑名称、Prompt、指标和预算，初期可以映射到同一个物理云模型。

发送云模型前执行最小化、DLP 和数据区域策略；检索内容一律视为不可信数据，不能修改系统 Policy 或工具权限。模型合同要求不用于训练、日志可关闭或零保留。Model Access Layer 配置出站白名单、Deadline、配额、熔断和供应商降级链。

Model Access 采用两层端口：

```text
领域任务端口
  RouterPort / QueryPlannerPort / GeneratorPort
  GroundingPort / EmbeddingPort / RerankerPort

Provider 能力适配
  ChatGenerationAdapter / StructuredOutputAdapter
  EmbeddingAdapter / RerankAdapter
```

- `assistant-runtime` 只依赖领域任务端口、领域 DTO 和服务端可校验的结果；Provider SDK、LangChain 类型、回调、Chain、Retriever、Memory 和 Agent 类型不得进入领域核心或跨服务契约。
- `platform-api` 完成身份、Grant、Session 和 Release 元数据解析后，通过内部 mTLS REST 调用向 `assistant-runtime` 传递不可由客户端构造的 Project Execution Context；`assistant-runtime` 必须在检索与 Evidence 处理时重新应用 Context 中的边界。
- 第一阶段 Python Provider Adapter 使用原生供应商 SDK 或 REST；LangChain 如在后期引入，也必须实现相同领域端口，并把供应商参数、重试、流式协议、错误分类和结构化输出校验封装在适配层内。
- Structured Output 只是一种适配能力，最终 Schema、权限、Evidence 和 Grounding 校验仍由服务端完成，不能把模型声明的 JSON 当作安全边界。

### 8.9 RAG 编排与受限 Agent 边界

第一阶段在线 RAG 由 `assistant-runtime` 的受约束 Domain Kernel 固定编排：

```text
Scope / Binding / Knowledge Release / Revocation
  -> Query Plan
  -> BM25 Top-K + Vector Top-K 独立召回
  -> RRF
  -> Reranker
  -> Evidence Hub
  -> Prompt Builder / Generator
  -> Claim Grounding / Citation / Validated Answer
```

- Kernel 独占 Scope、Binding、Knowledge Release、Revocation、Evidence、Citation、Grounding 和输出门禁；外部 RAG 框架不能替换这些控制面。
- `platform-api` 是 Identity、ProjectGrant、Session、Release 状态和审计的权威源；它只建立 Execution Context 并代理已验证 SSE，不能在 Java 中复制 RAG Kernel 的检索、Evidence、Citation 或 Grounding 规则。
- Python `assistant-runtime` 是 Kernel 的唯一实现位置；它不直接修改 MySQL 中的业务、权限、Session 或 Release 权威状态。
- Knowledge Plane 的解析、切分、Embedding 和索引发布与在线 RAG 编排分离；在线请求只能读取已授权的 Published Knowledge Release，不能通过编排框架修改知识状态。
- LangChain 不作为第一阶段 RAG 编排框架；它只可作为 Model Access Provider Adapter 的实现候选。
- LangGraph 不进入第一阶段主 RAG。第二阶段如需多步工具调用、重试、人工确认或持久化状态，只能在既有 Scope、ToolPlan、Tool Executor、Evidence 和审计边界内引入受限 Agent/Tool 子图。
- Project Assistant 是配置化执行单元，不因使用适配器或后续子图而获得任意 Agent 权限。

### 8.10 GraphRAG 边界

GraphRAG 不属于第一阶段请求链路。后续只作为 `ProjectQueryPlan.retrieval_mode` 可选择的检索模式，不承担项目路由、意图识别或 Prompt 组装；其引入条件、隔离维度和重建约束见第 14 章“后续技术演进边界”。

## 9. 系统接口与集成契约

### 9.1 Data Plane API

```text
POST  /v1/embed-bootstrap-tokens                         # 仅宿主后端
POST  /v1/sessions
POST  /v1/sessions/{session_id}/refresh                  # 创建 Successor Session
POST  /v1/sessions/{session_id}/project-threads
POST  /v1/sessions/{session_id}/messages                 # Project 或 Global 路由/聚合
POST  /v1/sessions/{session_id}/project-threads/{thread_id}/messages
PATCH /v1/sessions/{session_id}/client-context
GET   /v1/sessions/{session_id}/messages
POST  /v1/search
POST  /v1/messages/{message_id}/feedback
```

关键约束：

- 门户通过同源 Portal/Guest Session 创建 Assistant Session；外部 Embed 使用一次性 Bootstrap Token。
- 项目页和项目 Embed 默认只能创建 Project Session；只有显式配置为 Global Deployment 的 Portal/BFF 或 Server API Client 才能创建 Global Session。
- Session 响应返回 `conversation_id`、`session_id`、`session_type`、`deployment_revision_id`、`knowledge_binding_set_id`、有效 Access Segment 和过期时间。
- `refresh` 只能解析服务端当前活动 Revision，客户端不能指定目标 Revision；旧 Session 排空后失效。
- Project Session 不能切换 Project Execution Binding。
- Global Session 无 Thread 的消息端点只处理路由、澄清和跨项目聚合；继续项目对话必须使用 Thread 端点。
- Thread 消息携带 `expected_thread_version` 和 Idempotency Key。
- `client-context` 只允许 Schema 白名单中的页面、产品、功能和活动信息，不能修改 Subject、Project、Deployment、Revision、Scope、Access Segment 或 Model。
- Locale、Project Version 或 Access Segment 改变时通过 `refresh` 创建 Successor Session。
- Search 允许的 Project 集合只由服务端计算。
- Search 和 Answer 向客户端返回实际 Project、Project Version、Project Execution Binding、Knowledge Release、Citation 和知识生效时间；Assistant/Prompt Version、BM25/Vector Projection Watermark、逻辑模型和物理模型版本写入内部审计与 Trace。
- Session、Thread、Message、Citation 和 Feedback 同时校验 Subject、Client、Session、Deployment 和 Owner，随机 ID 不能替代对象级授权。
- Session Token 校验 `typ`、`iss`、JWT `aud`、`exp`、`jti`、`azp`、Origin、`authz_epoch` 和撤销状态。
- Bootstrap JTI 使用原子防重放；所有写接口要求 Idempotency Key。
- 未授权资源采用统一错误策略，避免利用 `403/404` 差异枚举项目和对象。

### 9.2 SSE 事件

```text
routing
project_switch
revision_available
session_replaced
claim_validated
claim_rejected
message_delta
citation
finish
error
```

所有事件携带 `message_execution_id`、`conversation_id`、`session_id`、`project_thread_id` 和实际 Binding ID；不适用字段显式为空。

`message_delta` 只包含已验证 Claim，并携带 `claim_id`、Evidence ID 和 `validation_status=VALIDATED`，不得直接流出 Generator 原始 Token。

外部 Embed 使用支持 Authorization Header 的 `fetch` 流消费 SSE。短期 Session Token 只保存在浏览器内存，不进入 URL、日志、Cookie 或 Local Storage。

### 9.3 Citation 对象

```text
project_id
project_version
knowledge_space_id
knowledge_release_id
document_id
knowledge_revision_id
locale
section
citation_url
effective_time
```

公开 API 不返回内部 `source_locator`、Connector 地址或对象存储路径。`citation_url` 必须是审核后的公开地址，或经过当前权限复核的 Citation Proxy。

### 9.4 Web SDK

```text
createClient(config)
mount(element)
createSession(options)
refreshSession()
selectProject(projectId) -> threadHandle
sendMessage(message, { threadId, expectedThreadVersion })
setContext(contextPatch)
setLocale(locale)
resetSession()
submitFeedback(feedback)
destroy()
```

事件：

```text
ready
authRequired
routing
projectChanged
revisionAvailable
sessionReplaced
claimValidated
claimRejected
message
citation
feedback
error
```

第一阶段不接受浏览器直接传入未经服务端证明的敏感业务对象标识或上下文。第二阶段此类上下文必须由宿主后端签名并执行对象级授权。

宿主 Context 使用命名空间和 JSON Schema：

```text
page
product
feature
campaign
custom
```

### 9.5 Control Plane API

管理 API 独立于消费者 API，覆盖：

- Enterprise、Project、Project Version 和 Knowledge Space。
- Source Connector、Source Object、Revision 和 Review。
- Release Candidate、Publish、Rollback 和 Emergency Revoke。
- Assistant Profile、Version、Deployment 和 Revision。
- OAuth Client、Access Policy 和 ProjectGrant。
- Evaluation Set、Release Report、Audit、Usage 和 Budget。

## 10. 存储与部署架构

### 10.1 存储职责

| 存储 | 职责 | 数据性质 |
| --- | --- | --- |
| MySQL | 项目、账号映射、Grant、SourceRevision 元数据、治理状态、Release、Assistant、Deployment、任务、Outbox、审计和持久 Conversation | Java 唯一拥有的业务权威状态 |
| 对象存储 | 原始资料、治理内容、解析/OCR 产物、不可变 Revision、Chunk Manifest、评测和发布资产 | 权威内容与可重建投影的输入事实 |
| PostgreSQL/pgvector | Published/Staging Chunk、Citation、过滤元数据、Embedding Space/Model Revision 与 Dense Vector | Python 拥有的可重建 Vector Serving Projection；不保存业务真相 |
| Elasticsearch | Published/Staging BM25 正文、标题、章节、过滤和高亮 | Python 拥有的可重建 BM25 Serving Projection；不保存 Dense Vector |
| Redis Online | 活跃 Session、短期 Memory、限流、授权缓存、撤回清单和可安全重建的在线缓存 | 临时在线状态；与 Celery Redis 隔离 |
| Redis Celery | Celery Broker 与短期 Result 协调 | 临时任务执行状态；不保存业务或发布真相 |
| Kafka | Transactional Outbox、接入、治理、索引、发布、授权、删除与 Worker 进度事件 | 可重放领域事件日志；不替代 Celery 任务执行 |

### 10.2 Serving Index 边界

- Source/Governance 资产与 Published Serving Projection 完全分离，使用独立凭证和网络策略。
- PostgreSQL/pgvector 与 Elasticsearch 必须应用同一 Project、Release、Locale、Access Policy、有效期和撤回过滤；任一投影都不能建立无边界全项目集合。
- Staging 与 Published-ready Projection 按不可变 Release 隔离。两套投影准备完成后才允许 Java 在 MySQL 切换 Active Release；在线请求始终使用 Execution Context 中固定的 `knowledge_release_id`。
- 增量构建只重算受影响文档；具体采用 Release 分区、Delta Segment、影子索引或重建策略，由两套存储各自的容量测试确定。
- MySQL 保存 Release、任务状态和两套 Projection Watermark。PostgreSQL/pgvector 与 Elasticsearch 均不作为发布状态真相源。
- PostgreSQL/pgvector 可以保存 Vector-only 降级所需的最小 Chunk 正文与 Citation，Elasticsearch 可以保存 BM25 高亮所需的正文；二者都必须通过 Chunk Manifest Hash 证明来自同一内容 Revision。
- 超大、热点或强监管项目可以采用独立 Index，不改变上层 API 和领域模型。

### 10.3 Schema 迁移与版本演进

- Java 使用 Flyway 管理 MySQL 业务 Schema；Python `uv` Workspace 使用 Alembic 管理 PostgreSQL `vector` 扩展、Vector Projection、过滤索引和向量索引。任何一方都不得修改另一方 Schema。
- 生产迁移通过独立预部署 Migration Job 执行。应用副本不在启动时自动竞争 DDL，运行身份默认没有 DDL 权限。
- 关系数据库迁移采用 expand/contract：先增加兼容结构，再执行幂等可续跑回填和读写切换，旧应用 Revision 排空后才删除旧结构。
- 生产回退优先回滚应用并执行前向补偿 Migration；破坏性 Down Migration 未经独立恢复演练不得进入自动发布流程。
- Elasticsearch 使用版本化 Index Template 与影子索引重建，不对在线索引执行破坏性字段迁移；OSS Artifact 和 Kafka Event 分别使用 Manifest Schema Version 与 Event Schema Version。
- 每个发布候选必须通过空库初始化、上一已发布 Schema 升级、中断重试、旧/新应用滚动兼容、备份恢复后升级、Flyway Validate、Alembic 单一 Head 和迁移审计测试。
- 当前项目没有已落库生产数据，本阶段只建立版本化 Schema Migration；未来存量数据搬迁必须单独设计对账、切流和回退，不得混入普通 Schema Migration。

### 10.4 Kubernetes

- `platform-api`、`assistant-runtime` 和 `batch-worker` 使用独立 Namespace 与 Service Account。
- 在线请求与离线索引使用独立节点池、队列和 ResourceQuota。
- 配置多可用区副本、PodDisruptionBudget、Anti-Affinity、NetworkPolicy 和最小权限 RBAC。
- 使用 Workload Identity、KMS、Secret Rotation 和出站白名单。
- MySQL、PostgreSQL/pgvector、Kafka、Elasticsearch 和对象存储优先采用云托管服务。
- 在线服务按请求并发、SSE 连接数和队列等待时间配置 HPA。
- `platform-api`、`assistant-runtime` 和 `batch-worker` 使用独立 Deployment、Service Account、ResourceQuota 与 HPA/KEDA 策略；`portal-web` 为独立 Web Deployment。
- `batch-worker` 按 Kafka Lag、Celery Queue 等待时间和任务资源类型使用 KEDA 扩缩容。
- 优雅终止排空流式连接或发送可恢复错误；离线任务使用 Checkpoint、幂等消费和 DLQ。

## 11. 非功能、可靠性与平台安全

### 11.1 容量模型与基线

生产上线前必须冻结以下容量输入：

```text
project_count
document_count
chunk_and_vector_count
daily_change_rate
locale_count
peak_search_qps
peak_answer_qps
concurrent_sse
average_prompt_and_output_tokens
cross_project_ratio
index_rebuild_window
monthly_cost_budget
```

容量计算使用：

- `Chunk 总量 = 已发布文档数 × 平均 Chunk 数 × 在线版本膨胀系数`。
- `向量原始字节 = Chunk 数 × 向量维度 × 每元素字节数`。
- `在线并发 = 峰值 QPS × P95 请求时长`。
- 检索、数据库、消息队列和模型并发至少保留 30% 至 50% 峰值余量。

达到以下任一条件触发专项扩容评审：持续资源利用率超过 70%、索引积压无法在更新 SLO 内清空、全量重建超过 RTO、模型配额成为主瓶颈或单项目热点影响其他项目。

### 11.2 性能与可用性目标

| 指标 | 第一阶段目标 |
| --- | --- |
| Search P95 | 不超过 1 秒 |
| Project 首个已验证回答片段 P95 | 不超过 3 秒 |
| Grounding Validator 单 Claim P95 | 不超过 500 毫秒 |
| Data Plane 月可用性 | 不低于 99.9% |
| 非用户输入导致的 Data Plane 错误率 | 低于 1% |
| 已批准变更到可检索 P95 | 不超过 5 分钟 |
| 紧急知识撤回生效 P95 | 不超过 60 秒 |
| Grant/Client 撤销传播 | P95 不超过 30 秒，P99 不超过 60 秒 |

上述模型相关延迟是工程目标，必须使用选定供应商、真实 Prompt 和实际网络完成原型验证。跨项目问题需要单独记录 P95 并在容量基线确定后设置门禁。无法满足时优先减少强 Router/Planner 调用、压缩 Evidence，或降级为搜索结果，不允许通过流出未验证 Token 换取首字延迟。

### 11.3 超时、熔断与降级

- Gateway、Authorization、Retrieval、Reranker、Generator 和 Validator 使用统一 Deadline 传播。
- 只对幂等瞬时故障执行有限重试，禁止无上限重试放大故障。
- Generator 不可用：切备用模型；仍失败则返回搜索结果和 Citation。
- Validator 不可用：不输出事实性生成文本，返回 Evidence 或拒答。
- Reranker 不可用：使用 RRF Top-K，并提高拒答阈值。
- Vector 检索不可用：降级为 BM25-only。
- Authorization 不可用：只有在已验证且未过期的 `PUBLIC` Binding 与新鲜撤回状态均可确定时才能继续；任何权限或撤回状态不明、以及所有受限 Access Segment 均 fail closed。
- Kafka/Index Worker 积压：继续服务旧 Release，不进行不完整激活。
- Global 分支失败：返回 `partial_coverage`，不推断缺失项目。
- 单项目流量突增：使用项目级 Quota、Bulkhead 和 Rate Limit 隔离。

### 11.4 数据保护与控制面安全

- Source、Governance 和 Published 使用独立存储边界、凭证和网络策略。
- Control Plane 使用独立管理员身份域、抗钓鱼 MFA、企业/项目级 RBAC 与 ABAC。
- 扩大 Access Policy、生产发布、高权限 OAuth Client 和 Grant/Policy 变更必须审计。
- 扩大数据可见范围和生产发布采用提交人与审批人职责分离。
- 模型出站执行最小化、DLP、区域和供应商合同策略。
- Citation Proxy、历史消息和收藏读取均重新执行当前对象级授权。
- 会话、审计、Source Revision 和 Release 的保留期由合规策略确定，并支持跨 MySQL、OSS、PostgreSQL/pgvector、Elasticsearch 和 Redis 的删除传播。

### 11.5 安全不变量

以下指标不是统计 SLO，而是上线阻断条件：

- 匿名访问受限知识：0。
- 跨 Project、Version、Access Segment、User、Session、Client 或 Deployment 越权：0。
- Bootstrap Token 跨 Origin 或重复使用成功：0。
- Router/Planner 非法或越权 Schema 输出被执行：0。
- 项目 Memory 交叉污染：0。
- 未验证事实进入 `message_delta`：0。
- 已撤回 Evidence 被引用：0。
- 内部 Source Locator 出现在公开响应：0。
- 消费者或项目管理员越权访问 Control Plane：0。

### 11.6 可观测性

每个回答记录以下版本和链路信息，不默认记录完整敏感 Prompt；调试采样必须脱敏、限期保留并接受审计：

```text
request_id / trace_id
conversation_id / session_id / thread_id
deployment_revision_id / project_execution_binding_id
knowledge_release_id / bm25_projection_watermark / vector_projection_watermark
mysql_schema_version / bm25_index_schema_version / vector_projection_schema_version
route_plan_version / query_plan_version
logical_model / physical_model / prompt_version
evidence_ids / claim_ids / validation_result
latency_breakdown / token_usage / estimated_cost
degradation_mode / error_code
```

指标按 Project、Deployment、Access Segment、Locale、Model 和 Provider 分层。Router、OAuth、Retrieval、Generation、Grounding、Citation、Release 和 Revocation 必须在同一 Trace 中可关联。

### 11.7 备份与恢复

- MySQL 业务权威库使用多可用区高可用和 PITR，初始目标 `RPO <= 5 分钟`、`RTO <= 2 小时`。
- 对象存储启用版本控制和生命周期策略。
- MySQL Conversation 数据配置加密备份和恢复演练，物理隔离强度与 RPO/RTO 在容量和合规基线确定后冻结。
- PostgreSQL/pgvector 与 Elasticsearch 必须能从 Release Manifest、OSS Chunk Manifest 和 Kafka 事件重建；可为缩短 RTO 配置快照，但快照不改变其投影性质。
- Redis 不作为持久权威，丢失后重新登录或重建缓存与短期 Memory。
- 每季度执行 MySQL 备份恢复、两套检索投影重建、Grant 撤销、知识撤回和模型故障演练。

## 12. 分阶段实施

### 12.1 阶段 1A：知识治理与单项目公开问答

交付：

- Project、Project Version、Knowledge Space 和管理员权限。
- Source -> Governance -> Published 三段式数据边界。
- 上传、批量导入、签名 Push API、增量索引、Release、Rollback 和 Emergency Revoke。
- 单项目 `PUBLIC` 页面、混合检索、Reranker、Citation、拒答和发布评测。
- MySQL、PostgreSQL/pgvector、对象存储、Elasticsearch、Redis、Kafka 和基础 K8s 部署。

上线门禁：完成“导入 -> 治理 -> 审批 -> 增量发布 -> 问答引用 -> 回滚/撤回 -> 删除传播”全链路验证，并证明外部请求无法访问 Source/Governance Zone。

### 12.2 阶段 1B：统一身份、UI 与项目嵌入

交付：

- 企业门户、项目知识页和 Web SDK 复用同一 `assistant-ui` 核心能力。
- Vue 3 Portal、Web Component、TypeScript SDK 和 REST/SSE API。
- 平台统一账号、Guest Session、三类 Access Segment 和 ProjectGrant。
- 第一方 Cookie、跨站 OIDC SSO、Bootstrap Token 和 Session Access Token。
- Project Session、项目 Memory、Conversation、收藏和反馈。

上线门禁：跨 User、Project、Client、Session 和 Deployment 越权为 0，Grant 撤销与 Token 防重放达到安全目标，标准项目完成接入回归。

### 12.3 阶段 1C：Global Router 与跨项目问答

交付：

- 授权项目候选集、Global Router 三层漏斗和项目规模扩展评测。
- GlobalRoutePlan、ProjectQueryPlan 和版本化 Prompt Builder。
- 隔离 Project Execution Context、EvidencePacket、Global Aggregator 和一次最终生成。
- 显式项目切换、partial_coverage 和跨项目专项评测。

上线门禁：固定项目请求不调用 Global Router；授权候选过滤、单/多项目路由、Memory 隔离、跨项目 Citation 和成本满足验收指标。

### 12.4 第二阶段：登录用户业务工具

- 项目业务 API Connector。
- 经对象级授权的实时只读业务查询。
- 受限 ToolPlan 和 Tool Executor。
- 如确有多步工具状态、重试或人工确认需求，再评估 LangGraph 等框架作为受限子图实现；不得接管 Scope、Evidence、Citation、Grounding 或模型出站策略。
- 平台账号或宿主身份与业务主体绑定。
- 对象级授权、数据最小化和实时事实 Citation。
- 经确认、幂等和审计的低风险业务操作。

实时事实只通过 Tool/API 查询，不进入通用知识索引和长期 Memory。

### 12.5 第三阶段：GraphRAG

- 项目范围内的结构化和语义关系图。
- GraphRAG Local 多跳查询。
- 异步 Global 主题归纳。
- 跨项目分别查询发布图后聚合。
- 只有相对混合检索产生明确质量收益后才扩大流量。

## 13. 第一阶段验收门禁

### 13.1 产品与集成

| 指标 | 目标 |
| --- | --- |
| 门户、项目页和 SDK 核心协议与交互一致 | 100% |
| Citation、范围、项目切换和错误组件复用 | 100% |
| 门户跨项目答案来源标注 | 100% |
| 项目 Embed 跨项目越权 | 0 |
| 管理全链路 | 导入、审批、增量发布、回滚、撤回和删除全部通过 |

### 13.2 知识与回答质量

| 指标 | 初始目标 |
| --- | --- |
| 已批准项目知识源覆盖率 | 不低于 95% |
| 已批准变更到可检索 P95 | 不超过 5 分钟 |
| Recall@10 | 不低于 90% |
| Top 3 存在有效 Evidence 比例 | 不低于 85% |
| 原子事实 Claim Citation 覆盖率 | 不低于 98% |
| Claim-Evidence 支持率 | 不低于 95% |
| 无支持事实输出率 | 不高于 1% |
| 有 Evidence 回答事实一致率 | 不低于 95% |
| 无证据拒答精确率 | 不低于 90% |
| 无证据拒答召回率 | 不低于 90% |
| 新 Revision 在活跃会话下一消息边界切换 | 100% |
| 超过 2 小时执行租约仍引用旧 Release | 0 |

### 13.3 路由、Session 与 Memory

| 指标 | 初始目标 |
| --- | --- |
| 单项目归属路由准确率 | 不低于 95% |
| 多项目拆分正确率 | 不低于 90% |
| 固定项目请求的 Global Router 调用 | 0 |
| 固定项目简单问题的强 Planner 调用 | 0 |
| 项目切换显式提示率 | 100% |
| Project Memory 交叉污染 | 0 |
| 双标签页、乱序重试或并发切换导致 Thread 串写 | 0 |
| Memory 内容被作为无 Citation 事实使用 | 0 |
| 跨项目回答 Generator 调用 | 每个用户问题 1 次 |
| 跨项目部分失败未标记 `partial_coverage` | 0 |
| 强 Router/Planner 触发率、P95 和单次成本 | 100% 可观测并按评测集设置门禁 |

### 13.4 身份与安全

| 指标 | 目标 |
| --- | --- |
| 匿名访问受限知识 | 0 |
| OAuth Scope 或 Token 伪造越权 | 0 |
| 跨 Project、Version、Access Segment 泄露 | 0 |
| 跨 User、Session、Client、Deployment IDOR | 0 |
| Bootstrap Token 跨 Origin 或重复使用成功 | 0 |
| OIDC CSRF、重放、Mix-up 和 Session Fixation | 0 |
| Grant/Client 撤销传播 | P95 不超过 30 秒，P99 不超过 60 秒 |
| 生产发布或扩大可见范围绕过双人审批 | 0 |
| 内部 Source Locator 出现在公开响应 | 0 |
| 发布前敏感信息检测和审核 | 100% |
| 紧急知识撤回生效 P95 | 不超过 60 秒 |

### 13.5 性能、可靠性与可观测性

| 指标 | 初始目标 |
| --- | --- |
| Search P95 | 不超过 1 秒 |
| Project 首个已验证片段 P95 | 不超过 3 秒 |
| Grounding Validator 单 Claim P95 | 不超过 500 毫秒 |
| 未验证事实进入 `message_delta` | 0 |
| Validator 超时/异常泄露原始文本 | 0 |
| Data Plane 月可用性 | 不低于 99.9% |
| 非用户输入导致的 Data Plane 错误率 | 低于 1% |
| 容量基线和月度成本预算 | 上线前完成压测和评审确认 |
| 所有回答记录 Project、Release、Evidence 和 Model Version | 100% |
| Token 用量和估算成本按 Project/Deployment 归集 | 100% |
| Router、OAuth、Retrieval、Generation、Grounding 和 Citation 链路可追踪 | 100% |

## 14. 后续技术演进边界

| 候选能力 | 引入条件 | 架构约束 |
| --- | --- | --- |
| Milvus | PostgreSQL/pgvector 经 HNSW/IVFFlat、分区、量化、扩容和托管产品调优后仍不满足向量 P95、积压、重建窗口或成本目标 | 只替换 Vector Recall Adapter；MySQL 仍是业务权威，Elasticsearch 保留 BM25 |
| Weaviate | 证明一体化混合检索能整体替代 Elasticsearch 并显著降低总成本 | 作为替代方案，不与 Elasticsearch + Milvus 三套长期并存 |
| GraphRAG/图数据库 | 高价值多跳问题占比明确，且相对混合检索有显著质量收益 | 图按 Project、Release、Locale 和 Audience Policy 隔离并可从 Published Knowledge 重建；禁止将不同项目或权限数据混入同一无边界图谱 |
| 受限 Agent/Tool 子图框架 | 第二阶段工具交互确实需要多步状态、重试、人工确认或持久化检查点 | 只能实现已授权 `ToolPlan` 的受限子图；不得接管 Scope、Binding、Release、Evidence、Citation、Grounding 或 Model Access 出站策略 |
| Flink | Kafka Consumer 和批处理无法满足有状态事件顺序或吞吐要求 | 不替代事务数据库和发布状态机 |
| 私有模型 | 云模型无法满足数据区域、合同、成本或稳定性要求 | 继续通过相同 Model Access 逻辑契约接入 |
| 多地域灾备 | 业务 SLO、监管或单地域风险要求 | 先完成单地域多 AZ 和恢复演练 |

跨项目 GraphRAG 分别查询各项目的已发布图，再聚合经过权限校验的结果。BM25 或 Vector 存储迁移分别使用 Release 事件回放构建影子投影，执行离线评测、双读和项目级小流量切换；迁移窗口结束后删除旧投影，不把永久在线双写作为一致性真相源。
