# 第一阶段实施执行方案

| 属性 | 内容 |
| --- | --- |
| 状态 | `ACCEPTED` |
| 文档类型 | 第一阶段实施与交付拆分基线 |
| 适用范围 | 阶段 `1A + 1B + 1C` |
| 架构事实源 | [`../tech-plan.md`](../tech-plan.md)、[`../architecture.md`](../architecture.md) |
| 架构决策 | [`../adr/0001-constrained-rag-kernel-and-model-access.md`](../adr/0001-constrained-rag-kernel-and-model-access.md)、[`../adr/0002-java-platform-and-python-ai-runtime.md`](../adr/0002-java-platform-and-python-ai-runtime.md)、[`../adr/0003-mysql-authority-and-pgvector-retrieval-projection.md`](../adr/0003-mysql-authority-and-pgvector-retrieval-projection.md) |
| 外部依赖状态 | [`../technology-selection/technology-selection.md`](../technology-selection/technology-selection.md) |
| 具体执行路线 | [`0002-phase-1-seven-day-execution-route.md`](0002-phase-1-seven-day-execution-route.md) |
| 最后更新 | 2026-08-11 |

本文已经审核接受，负责把冻结的第一阶段架构拆成可开发、可集成、可验收的交付批次。本文不修改 `tech-plan.md`、ADR 或技术选型状态；外部产品仍以技术选型索引为唯一事实源，本文中的提交顺序不表示对应产品已经完成选型。

## 1. 目标与完成定义

第一阶段不是单一问答 MVP，而是完整交付以下三段能力：

```text
阶段 1A：知识治理与单项目公开问答
  -> 阶段 1B：统一身份、UI 与项目嵌入
  -> 阶段 1C：Global Router 与跨项目问答
```

阶段之间按能力递进，但不要求所有研发工作严格串行。共享协议、测试夹具、基础设施和 UI 核心可以提前并行；任何子阶段只有在其跨层链路和退出门禁同时满足后才算完成。

| 子阶段 | 用户可观察结果 | 完成定义 |
| --- | --- | --- |
| `1A` | 内容人员能够导入、治理、审批、发布、回滚和撤回知识；匿名消费者能够在固定项目范围内搜索、问答并查看 Citation | `Source -> Governance -> Published` 全链路可追踪；Project 请求只检索已发布 Release；混合检索、Grounding、拒答、回滚、撤回和删除传播通过门禁 |
| `1B` | 用户通过门户、项目页或宿主 Web Component 获得一致的登录、会话、问答、Citation、收藏和反馈体验 | 平台身份、ProjectGrant、三类 Access Segment、Guest Session、OIDC、Bootstrap Token、Session Token 和对象级授权形成闭环；跨 User、Project、Client、Session、Deployment 越权为 0 |
| `1C` | 门户能够在用户已授权的项目集合内完成项目识别、澄清、显式切换和跨项目 Evidence 聚合 | 固定项目请求不调用 Global Router；单项目和多项目路由达到质量门禁；Project Thread、Memory、Citation 和部分失败保持项目隔离 |

第一阶段最终完成还要求 [`../tech-plan.md`](../tech-plan.md) 第 13 章的产品、质量、路由、身份、安全、性能、可靠性和可观测性门禁全部关闭。单个页面可用、单个模型调用成功或局部 PoC 通过均不构成第一阶段完成。

### 1.1 明确排除

- 不实现第二阶段的项目业务 API Connector、ToolPlan 或 Tool Executor。
- 不实现第三阶段 GraphRAG、图数据库或跨项目混合图。
- 不引入 LangChain 主 RAG、LangGraph 主 Workflow 或 MaxKB Runtime。
- 不建设 React Adapter、原生移动 SDK、Flink、Milvus、Weaviate、Elasticsearch Dense Vector、私有模型生产链路或多地域灾备。
- 不把消费者会话、用户上传内容或未审批资料自动转为 Published Knowledge。
- 不通过本实施方案替尚未完成的网关、身份、安全、解析、云产品或可观测性选型作出产品决定。

## 2. 分层架构基线

| 层次 | 第一阶段所有者 | 固定运行时或形态 | 必须持有的职责 | 不得持有的职责 |
| --- | --- | --- | --- | --- |
| 前端体验层 | `portal-web`、`assistant-ui`、TypeScript Client | Vue 3 + TypeScript + Vite；Web Component | 门户、项目页、治理界面、会话状态、Citation、项目切换、Embed 和用户反馈 | 不计算授权范围，不允许客户端指定 Project Execution Context、Release、Access Segment 或模型 |
| Java 平台层 | `platform-api` | Java + Spring Boot 模块化单体 | Project、Identity、Grant、Session、Thread、Release、任务状态、审计、Transactional Outbox 和外部 API | 不复制检索、Evidence、Citation、Grounding 或 RAG Kernel 规则 |
| 在线 AI 层 | `assistant-runtime` | Python + FastAPI + `uv` | 不可变 Execution Context Guard、Project/Global 查询计划、Elasticsearch BM25、pgvector Vector、RRF、Evidence、Prompt、模型访问、Grounding、Citation 和已验证事件 | 不直接修改 MySQL 权威状态，不接受客户端自造 Scope，不流出未验证模型 Token |
| 知识批处理层 | `batch-worker` | Python + Celery + `uv` | Kafka 事件分发、扫描、解析、OCR、去重、Chunk、Embedding、OSS Artifact、BM25/Vector Staging、发布评测、准备和投影清理 | 不成为业务状态机，不决定审批和 Active Release 真相，不接受 Java 直接写入 Celery 私有协议 |
| 权威数据与事件层 | MySQL、OSS、Kafka | 业务关系状态、不可变内容、可重放事件 | MySQL 保存业务状态，OSS 保存 Source/Governance/Revision/Chunk 资产，Kafka 保存领域事件 | 不允许 PostgreSQL/pgvector、Redis 或 Elasticsearch 成为 Release、授权或任务状态真相 |
| 检索与临时投影层 | PostgreSQL/pgvector、Elasticsearch、Redis Online、Redis Celery | Published/Staging 检索投影与短期状态 | 分别提供 Vector 与 BM25 召回、在线 Session/撤回缓存和 Celery Broker/短期 Result | 不永久双存 Vector，不长期共享 Online 与 Celery 的容量、ACL、淘汰或故障边界 |
| 部署层 | 四个 Deployment | `portal-web`、`platform-api`、`assistant-runtime`、`batch-worker` | 独立发布、扩缩容、Service Account、网络与资源隔离 | 不因逻辑模块数量提前拆成更多服务 |

### 2.1 Monorepo 物理目录

| 路径 | 所有权与用途 |
| --- | --- |
| `apps/portal-web/` | `portal-web` Web Deployment |
| `services/platform-api/` | Java/Spring Boot 模块化单体；持有 MySQL/Flyway Migration |
| `services/assistant-runtime/` | Python/FastAPI 在线 AI Runtime |
| `services/batch-worker/` | Python/Celery 离线 Worker；持有 PostgreSQL/pgvector Alembic Migration |
| `packages/assistant-ui/` | Vue UI 核心组件与 Web Component 构建包 |
| `packages/typescript-client/` | OpenAPI Client、SSE 状态机与 Session/Thread API 构建包 |
| `contracts/` | 跨语言 OpenAPI、SSE、Execution Context、Kafka、Celery、错误与评测 Schema |
| `infra/` | 本地集成环境、ACK 资源、网络策略和两个独立 Migration Job；不复制服务拥有的 Migration |
| `tests/` | 跨服务合同、E2E、密封评测、安全、性能与恢复测试；组件局部测试仍归组件目录 |
| `docs/` | 架构、ADR、技术选型、实施方案、PoC 证据与 Runbook |
| `tools/` | 仓库验证、代码生成和可重复 PoC 工具 |

根目录只保留仓库入口、协作契约和全局工具配置。前端、Python 与 Java 工程基线已经初始化，版本统一见 [`技术栈与外部选型总览`](../technology-selection/technology-selection.md)，可执行版本由各工作区 Manifest、锁文件和 Wrapper 固定。正式跨语言 Schema 与代码生成配置仍由 `P1-00` 交付；工程初始化不代表 Day 1 已开始。

## 3. 跨层合同优先

实现从合同开始，但合同只冻结已经由架构确定的语义，不提前冻结尚未完成的外部产品。每个合同必须有 Schema Version、兼容规则、示例、错误语义和消费者合同测试。

| 合同 | 生产者 | 消费者 | 第一阶段必须固定的内容 |
| --- | --- | --- | --- |
| Public OpenAPI | `platform-api` | Portal、TypeScript Client、宿主后端 | Session、Message、Search、Feedback、Bootstrap Token、Control Plane API、幂等键和统一错误模型 |
| SSE Event Schema | `assistant-runtime` 产生领域事件，`platform-api` 审计并代理 | Portal、Web Component、TypeScript Client | `routing`、`project_switch`、`revision_available`、`session_replaced`、Claim、`message_delta`、Citation、Finish 和 Error 的顺序与恢复语义 |
| Immutable Project Execution Context | `platform-api` | `assistant-runtime` | Subject、Client、Deployment Revision、Binding、Project、Version、Locale、Access Segment、Release、`authz_epoch`、Deadline 和审计上下文；客户端不可构造 |
| Kafka Event Schema | `platform-api` Outbox、`batch-worker` | Python Dispatcher、Java Event Projector | SourceRevision、Tombstone、Progress、CandidateReady、ActivationRequested、ActivationCompleted、Revocation 和失败事件；事件 ID、幂等键和版本 |
| Celery JSON Task Schema | Python Dispatcher | `batch-worker` | 任务类型、输入 Revision、幂等键、Deadline、有限重试、资源类别和结果事件；禁止 `pickle` |
| Retrieval/Evidence Contract | `assistant-runtime` 内部模块 | RAG Domain Kernel、评测工具 | Filter、BM25/Vector 独立 Rank、RRF、Reranker、EvidencePacket、Citation、降级模式和拒答原因 |
| Evaluation Report Schema | `batch-worker` | `platform-api`、治理 UI | Retrieval、Answer、ACL、Leakage、容量和成本指标；数据集版本、模型版本、BM25/Vector Projection 版本和通过状态 |

合同仓库应作为 Monorepo 的共享边界，生成客户端和服务端类型时保留语言独立 Schema。Java 与 Python 不共享 ORM、进程内 DTO、框架 Message 或 Provider SDK 类型。

## 4. 前端层执行方案

### 4.1 共享前端结构

前端按一个 Web Deployment 和两个可复用包组织：

```text
portal-web
  -> Enterprise Portal
  -> Project Knowledge Page
  -> Knowledge Governance / Release Console

assistant-ui
  -> Vue 3 Core Components
  -> Vue Web Component

typescript-client
  -> OpenAPI Client
  -> SSE Parser / State Machine
  -> Session / Thread / Feedback API
```

`portal-web`、项目页和 Web Component 必须复用同一消息状态机、Citation 组件、范围组件、错误模型和 TypeScript Client。品牌色、欢迎语和推荐问题允许配置，权限、协议和失败语义不允许由宿主覆盖。

### 4.2 阶段 1A

- 实现 Project、Project Version、Knowledge Space、Source Revision、治理任务、Release Candidate 和 Deployment Revision 的管理界面。
- 实现上传、批量导入和签名 Push API 任务状态视图；上传只显示 Source Zone 接收结果，不提供绕过治理直接发布入口。
- 实现治理审核、评测报告、双人审批、发布、回滚、紧急撤回和删除传播状态。
- 实现固定项目 `PUBLIC` 知识页、匿名短期执行会话、搜索和问答；范围栏固定显示 Project、Version、Locale 和 `PUBLIC`。完整 Guest Session、登录合并选择和持久 Conversation 在 `1B` 交付。
- 实现回答、Evidence-only、拒答、降级、错误、Citation、反馈和重试状态；未收到 `claim_validated` 的文本不得进入用户消息。
- 实现发布换版提示：接收 `revision_available`，在下一条消息边界执行 Session Refresh，并展示 `session_replaced`。

### 4.3 阶段 1B

- 实现 Portal Guest Session、平台登录、退出、身份过期、授权不足、Grant 撤销和重新认证状态。
- 实现三个 Access Segment 的可见范围展示，但前端显示值只来自服务端响应，不能作为请求授权参数。
- 实现 Conversation、Project Session、Project Thread、收藏、反馈和历史消息；读取历史时正确处理当前权限已收窄的 Claim 遮蔽。
- 将 `assistant-ui` 发布为 Vue Web Component，提供精确 Origin 配置、Bootstrap Token 交换、内存内 Session Token 和 `postMessage` Origin 校验。
- TypeScript Client 实现 `createSession`、`refreshSession`、`sendMessage`、`selectProject`、`setContext`、`setLocale`、`resetSession`、`submitFeedback` 和 `destroy`。
- 实现 SSE 断连、超时、重复事件和有界恢复；重连不得重复提交 Message 或越过 Session/Thread Version。

### 4.4 阶段 1C

- 企业门户提供授权项目候选、路由中、需要澄清、项目切换和跨项目确认状态。
- 固定项目页面收到 `scope_mismatch / handoff_required` 时，只提供跳转门户或创建新 Project Session，不扩大原 Session。
- 跨项目回答按 Claim 展示来源 Project、Version、Release、Citation 和知识时间；不使用单一全局版本标签。
- 展示 `partial_coverage`、实际覆盖项目和分支失败原因；不得把缺失项目表现为“未发现相关内容”。
- 同一 Global Session 中每个 Project Thread 保持独立 UI 状态和 Thread Version；显式展示切换，禁止静默复用其他项目上下文。

### 4.5 前端验证

- 组件测试覆盖消息状态机、Citation、拒答、降级、项目切换、Session 换版和权限收窄。
- TypeScript Client 使用 OpenAPI/SSE 合同夹具验证事件乱序、重复、断连、错误映射和幂等重试。
- Portal、项目页和 Web Component 对同一测试 Session 运行行为一致性回归。
- E2E 覆盖匿名、登录、项目授权、过期 Token、撤权、跨 Origin Bootstrap Token、防重放和双标签页并发。
- 可访问性、键盘操作、响应式布局和长 Citation 文本纳入发布检查；任何动态状态不得造成按钮、消息或 Citation 重叠。

## 5. Java 后端层执行方案

### 5.1 模块边界

`platform-api` 保持模块化单体，模块之间通过显式应用服务和领域事件协作，不通过共享表随意改写彼此状态：

| 模块 | 权威职责 |
| --- | --- |
| `public-api` | REST/SSE 入口、请求校验、幂等、限流上下文、统一错误和审计入口 |
| `project-catalog` | Enterprise、Project、Project Version、Knowledge Space、Deployment 和 Profile 元数据 |
| `identity-access` | Identity 映射、OAuth Client、ProjectGrant、Access Segment、`authz_epoch`、Bootstrap Token 和对象级授权 |
| `session-thread` | Conversation、Assistant Session、Project Thread、Message、乐观并发和 Successor Session |
| `knowledge-control` | Source Object/Revision、治理状态、审核、任务命令和 Source Zone 接入合同 |
| `release-control` | Release Candidate、双人审批、Knowledge Release、Binding、Activation、Rollback、Emergency Revoke 和删除传播 |
| `audit-usage` | 审计、使用量、成本归集、反馈和合规查询 |
| `outbox-projection` | Transactional Outbox、Kafka 发布、Worker 进度投影、幂等消费和失败状态 |

### 5.2 阶段 1A

- 建立 Project、Project Version、Knowledge Space、Source Revision、Knowledge Revision、Knowledge Release、Binding、Deployment Revision 和任务状态模型。
- 所有 Source 接入先将对象写入隔离 OSS Source Zone，再在 MySQL 事务中登记 SourceRevision、Task State 和 Outbox Record。
- 实现 SourceRevision/Tombstone 领域事件、Outbox Publisher 和 Worker Progress/CandidateReady 投影。
- 实现治理审核与职责分离：提交者不能批准自己提交的生产发布或可见范围扩大。
- 实现 Release Candidate、评测门禁、ActivationRequested、ActivationCompleted、原子激活、回滚和当前活动 Revision 指针。
- 实现 Emergency Revoke 同步安全路径：在 MySQL 提交权威撤回状态后更新 Redis Online Revocation List，再异步发布 Tombstone 清理两套检索投影。
- 实现固定 Project `PUBLIC` 短期执行 Session、Search、Message、Feedback 和 Citation Proxy 对象级授权；该 Session 不提供登录身份、跨设备历史或长期 Conversation。
- 每条消息构造不可变 Project Execution Context，经内部 mTLS REST 调用 `assistant-runtime`；只代理经过验证的 SSE 事件。

### 5.3 阶段 1B

- 集成或实现 Identity Service 边界，支持 Guest、平台登录用户和项目授权用户；具体 IdP 产品由专项选型关闭。
- 实现 OIDC Authorization Code + PKCE、第一方 Session Cookie、Refresh Token 旋转、CSRF 防护和 Session Fixation 防护。
- 实现 ProjectGrant/ABAC、Client Scope、Knowledge Access Policy 和 Object Authorization 的服务端交集计算。
- 实现一次性 Embed Bootstrap Token，绑定 Client、Subject、Origin、Deployment Revision、`authz_epoch`、`exp` 和 `jti`；JTI 原子防重放。
- 实现 Session-bound Access Token、Token `typ`/Audience 隔离、撤销级联和历史对象重新授权。
- 实现 Conversation、Session、Thread、Message、收藏、反馈和 Project Memory 元数据；Thread 使用 `expected_thread_version` 与 Idempotency Key。
- Project、Version、Locale、Access Segment、Profile 或 Deployment Revision 改变时创建 Successor Session，不原地修改旧 Session。

### 5.4 阶段 1C

- 为 Global Deployment 计算当前用户可访问的 Project Candidate Set，候选集必须在进入 Router 前完成授权过滤。
- Global Session 固定 Global Deployment Revision，不保存可被并发请求修改的“当前项目”字段。
- 为选中的每个项目解析独立 Project Execution Context 和 Project Thread，分别调用 `assistant-runtime`。
- 保存跨项目结果为 `GlobalResultReference`，按 Claim 记录 Project、Release、Access Context 和 Evidence ID；读取时重新授权。
- 分支部分失败时保存并返回 `partial_coverage`；Grant 或 Release 失效后按 Claim 遮蔽，无法安全拆分时禁用整条结果。
- 记录 Router、Planner、项目 fan-out、分支延迟、模型用量和最终单次 Generator 调用的审计数据。

### 5.5 Java 验证

- 领域单元测试覆盖发布状态机、职责分离、Session 换版、Thread 乐观锁、Grant 收窄和撤回优先级。
- MySQL 集成测试覆盖事务回滚、Outbox 原子性、重复事件、乱序事件、投影幂等和并发审批。
- OpenAPI、内部 Execution Context 和 Kafka Schema 执行生产者/消费者合同测试。
- 安全测试覆盖 Token 类型混用、Audience 错误、Bootstrap 重放、跨 Origin、IDOR、CSRF、OIDC Mix-up、Session Fixation 和未授权资源枚举。
- 审计断言确保每次回答都关联 Project、Deployment Revision、Release、Evidence、模型版本、Token 用量和成本。

## 6. 在线 AI 层执行方案

### 6.1 受约束 RAG Domain Kernel

`assistant-runtime` 内固定执行以下 Pipeline：

```text
Authenticated Internal Request
  -> Immutable Context Schema / Deadline / Revocation Guard
  -> ProjectQueryPlan
  -> BM25 Top 50 + Vector Top 50，先过滤后召回
  -> Domain RRF(k=60) Top 50
  -> Reranker Top 10
  -> Evidence Hub
  -> Prompt Builder / Generator，按 Claim 缓冲
  -> Grounding / Citation / Content Gate
  -> Validated Claim / Evidence-only / Refusal SSE
```

Kernel 独占 Scope、Binding、Release、Revocation、Evidence、Citation、Grounding 和输出门禁。Model Access 只暴露领域任务端口和平台 DTO，第一阶段 Provider Adapter 使用原生供应商 SDK 或 REST，不引入 LangChain 类型。

### 6.2 阶段 1A

- 定义并验证 Project Execution Context；任何缺失、过期、签名无效、权限不明或撤回状态不明的请求 fail closed。
- 实现固定 ProjectQueryPlan 的确定性路径；简单问题不调用强 Planner，Planner 不允许输出任意 Project、Index、Model 或 Tool 参数。
- 实现 Elasticsearch BM25 与 PostgreSQL/pgvector Vector 独立召回；Project、Release、Locale、Access Segment、有效期和撤回状态使用同一 Execution Context 在各路 Top-K 前生效，Vector 分支额外校验 Embedding Space 与配置指纹。
- 实现 Domain RRF、`chunk_id` 去重、原始 Rank/Score 保留、Reranker 和 Evidence Hub 二次边界复核。
- 实现版本化 Prompt Builder，明确区分 Policy、Memory、Evidence 和原始问题；Memory 不得成为事实 Evidence。
- Generator 按完整句子或 Claim 缓冲；Grounding、Citation、内容安全、PII 和受限信息门禁全部通过后才产生 `message_delta`。
- 实现降级：Vector 不可用退 BM25，Reranker 不可用退 RRF，Generator 不可用退备用模型或 Evidence，Validator 不可用只返回 Evidence 或拒答。
- 为每次执行记录检索参数、Evidence、Claim、逻辑/物理模型、Prompt Version、延迟、Token、成本和降级模式。

### 6.3 阶段 1B

- 重新应用 Java 传入的 Subject、Client、Session、Deployment、Binding、Release、Access Segment 和 `authz_epoch`；浏览器 Context 只作为白名单检索提示。
- Project Memory Key 完整包含 User/Guest、Project、Version、Deployment Revision、Profile、Binding、Release、Thread、Locale 和 Access Context Hash。
- 只将当前项目指代、最近问题和 Evidence ID 用于对话连续性；其他项目内容、跨项目综合事实和未经引用的记忆不得进入事实层。
- Session Refresh 后旧 Evidence 不进入新 Prompt；超过两小时执行租约的旧 Release 请求必须拒绝并要求换版。
- 内部错误映射为稳定领域错误；不得向 Public SSE 暴露 Provider 响应、Prompt、Source Locator 或策略拦截细节。

### 6.4 阶段 1C

- 仅 Global Deployment 启用 Global Router；固定 Project Deployment 的 Router 调用必须为 0。
- 路由实现规则、轻量分类、强模型兜底三层漏斗，并使用 JSON Schema 和服务端策略复核输出。
- 区分 `DISAMBIGUATION_PROBE` 与 `CROSS_PROJECT_ANSWER`；只有用户明确提出或确认多项目范围后才聚合。
- 首期 fan-out 最大为 3，每个项目分支使用独立 Context、Deadline、并发上限、检索和 EvidencePacket。
- Global Aggregator 只接收受约束 EvidencePacket，不读取 Project Conversation Memory；跨项目回答最终 Generator 每个用户问题只调用一次。
- 部分失败返回实际覆盖项目和 `partial_coverage`，不推断缺失项目，不把一个项目的 Evidence 补到另一个项目。

### 6.5 在线 AI 验证

- Domain Kernel 使用纯领域夹具执行单元和属性测试，验证任何非法 Context、越权 Router/Planner 输出、撤回 Evidence 和跨项目污染均被拒绝。
- 检索合同测试固定 BM25/Vector 输入 Rank，验证 RRF、去重、过滤顺序、降级和 Reranker 无效响应。
- Model Adapter 契约测试覆盖结构化输出、Deadline、有限重试、流式协议、错误分类、审计、数据最小化和 Provider 回退。
- Grounding 测试覆盖支持、矛盾、证据不足、灰区、超时和异常；断言未验证文本永不进入 `message_delta`。
- 路由评测分别统计规则、轻量模型和强模型触发率、准确率、P95、成本、fan-out 和 `partial_coverage`。

## 7. 知识批处理层执行方案

### 7.1 任务边界

```text
Kafka SourceRevision / Tombstone
  -> Python Dispatcher
  -> Celery JSON Task / Redis Celery
  -> Scan -> Parse/OCR -> Deduplicate -> Chunk -> Embed
  -> OSS Chunk Manifest
  -> Elasticsearch BM25 Staging Projection
  -> PostgreSQL/pgvector Vector Staging Projection
  -> Retrieval / Answer / ACL / Leakage Evaluation
  -> Kafka CandidateReady / Failure
  -> Java Approval / ActivationRequested
  -> Joint Projection Gate / ActivationPrepared
  -> Java 在 MySQL 原子切换 Active Release
```

### 7.2 阶段 1A

- Dispatcher 校验 Kafka Schema、事件版本和幂等键，将事件转换为 JSON Celery Task；未知版本进入失败事件或 DLQ，不静默消费。
- Worker 只从 OSS Source/Governance Zone 读取明确 Revision，不接受任意对象路径或客户端 URL。
- 按资源类型拆分扫描、解析/OCR、去重、结构感知 Chunk、Embedding、批量索引和评测 Queue；全量重建与在线增量使用独立队列。
- Chunker 使用版本化 Profile 处理 prose、FAQ、API、Release Notes、Policy、Table 和 Code，保留字符 Offset、标题、章节路径和 Citation 重建信息。
- 精确重复使用规范化 SHA-256；MinHash/LSH 只产生治理审核信号，不跨 Project、Version、Locale 或 Access Segment 自动合并。
- 解析、治理和 Chunk 产物以不可变 Artifact 与 Chunk Manifest 写入 OSS；每个投影必须记录同一 Manifest Hash。
- Elasticsearch 只写 BM25 正文、高亮和过滤投影；PostgreSQL/pgvector 写 Chunk、Citation、过滤元数据、Embedding Space/Model Revision 与 Dense Vector，不向 Elasticsearch 复制向量。
- Embedding Space、Tokenizer/Model Revision、Analyzer、Chunker、RRF、Reranker、BM25 Index Schema Version 和 Vector Projection Schema Version 写入 Release Manifest。
- Staging 与 Published-ready Projection 按 Release 隔离；只有 Java 已批准的 ActivationRequested 才能准备两套投影，数量、Hash、ACL 和评测一致、两套 Watermark 均指向同一 Release/Manifest 后发布 ActivationPrepared，由 Java 在 MySQL 单事务切换 Active Release。
- Tombstone 清理 Elasticsearch BM25、PostgreSQL/pgvector Vector 和缓存投影；完成后发布可重放结果事件。

### 7.3 阶段 1B

- 将 Access Segment、Audience Policy、有效期和 Citation URL 投影到每个 Chunk，并为权限收窄生成增量 Tombstone/Revision。
- 评测增加匿名、平台登录和项目授权三类 ACL 矩阵，以及公开响应 Source Locator、PII、Secret 和受限信息泄露检查。
- Worker 进度事件支持治理 UI 展示总量、成功、失败、重试、DLQ、评测结果和可操作原因。

### 7.4 阶段 1C

- 为 Global Router 与跨项目问答生成版本化项目目录和路由评测集；若启用项目目录检索，必须单独验证授权过滤、更新水位和候选召回率。
- 生成跨项目查询、歧义、单项目归属、多项目拆分、部分失败和 Memory 隔离评测样本。
- 各项目保持独立 Release、索引过滤和评测结果；不构建无边界全项目混合索引。

### 7.5 批处理验证

- 测试重复、乱序、重放、失败重试、Worker 崩溃、Checkpoint、DLQ 和幂等写入。
- 测试 Source 对象缺失、恶意文件、解析超限、OCR 失败、模型超时、批量写部分失败和索引版本不兼容。
- 测试未通过评测、未获批准或状态过期的 Candidate 无法激活。
- 测试回滚、紧急撤回、删除传播，以及 Elasticsearch BM25 与 PostgreSQL/pgvector Vector 从 Release Manifest、OSS、Kafka 独立重建。
- 压测增量与全量队列隔离，证明已批准变更到可检索 P95 不超过 5 分钟。

## 8. 数据与基础设施层执行方案

### 8.1 数据职责

| 组件 | 第一阶段建设内容 | 故障与恢复原则 |
| --- | --- | --- |
| MySQL | 业务、身份映射、Grant、SourceRevision 元数据、Session、Release、任务、Conversation、Outbox 和审计 Schema；Flyway、备份和 PITR | Java 业务权威；初始 `RPO <= 5 分钟`、`RTO <= 2 小时` |
| OSS | Source、Governance、解析/OCR、Immutable Revision、Chunk Manifest、评测和发布资产的 Bucket/Prefix、版本控制、加密和生命周期 | 内容事实源；对象路径不进入公开响应 |
| PostgreSQL/pgvector | Chunk、Citation、过滤元数据、Embedding Space/Model Revision、Dense Vector；Alembic、过滤索引、向量索引和重建 | 可重建 Vector Projection；不保存业务、授权、审批、任务或 Active Release 真相 |
| Kafka | 领域事件 Topic、Schema、分区键、保留、重放、DLQ 和 Consumer Lag | 可重放事件日志；不替代任务执行 |
| Redis Online | Session、短期 Memory、限流、授权缓存、Revocation List | 非权威；丢失后重建或重新登录；权限状态不明时 fail closed |
| Redis Celery | Celery Broker、短期 Result、Queue 隔离和有限重试 | 非权威；与 Online 至少逻辑隔离 |
| Elasticsearch | Staging/Published BM25 Index Template、Analyzer、正文、高亮、过滤字段和 Watermark；不配置 Dense Vector 字段 | 可从 Release Manifest、OSS 和 Kafka 重建 |

### 8.2 数据库迁移与版本演进

| 迁移目标 | 所有者与工具 | 第一阶段必须实现 |
| --- | --- | --- |
| MySQL 业务 Schema | Java `platform-api` + Flyway | 版本化 DDL、索引、约束、Outbox、Migration History 与 Validate；只由独立 Migration Job 使用 DDL 身份 |
| PostgreSQL/pgvector Schema | Python `uv` Workspace + Alembic | `vector` 扩展、Projection 表、过滤/向量索引、单一 Head 和 Migration History；只由独立 Migration Job 使用 DDL 身份 |
| Elasticsearch Schema | Python `batch-worker` + 版本化 Index Template | 新 Template 构建影子 Release Projection，经评测后启用；禁止破坏性原地字段迁移 |
| OSS/Kafka Schema | Manifest Version / Event Schema Version | Artifact 不可变；事件保持兼容，未知版本进入失败事件或 DLQ |

- MySQL 与 PostgreSQL Migration Job 独立运行，不能共享事务、迁移历史、DDL 身份或自动启动逻辑；Java 无 PostgreSQL 权限，Python 无 MySQL DDL/业务写权限。
- 关系数据库变更采用 expand/contract。先增加兼容结构，再执行幂等可续跑回填和读写切换，旧应用 Revision 排空后才允许 Contract。
- 生产回退优先回滚应用并执行显式前向补偿；任何破坏性 Down Migration 必须先通过备份恢复演练，不能成为默认自动回退。
- CI 必须覆盖空库初始化、上一发布 Schema 升级、中断后重试、旧/新应用滚动兼容、备份恢复后升级、Flyway Validate、Alembic 单一 Head 和迁移版本审计。
- 当前没有已落库生产数据，不创建虚假的 PostgreSQL 到 MySQL 搬迁脚本；未来出现存量数据源时单独设计对账、切流和回退。

### 8.3 部署与网络

- 固定四个 Deployment，分别配置 Service Account、ResourceQuota、NetworkPolicy、健康检查、优雅终止和扩缩容策略。
- `platform-api`、`assistant-runtime`、`batch-worker` 使用独立安全身份；Java 到 Python 使用内部 mTLS REST。
- Source/Governance、Staging 和 Published 使用独立凭证与网络策略；Data Plane 只能读取 Published Projection。
- 在线服务按请求并发、SSE 连接和延迟扩缩容；Worker 按 Kafka Lag、Celery Queue 等待时间和任务资源类型扩缩容。
- 在线与离线任务使用独立节点/资源配额；Worker 积压时继续服务旧 Release，不激活不完整索引。
- 配置统一 Deadline、熔断、项目级 Quota、Bulkhead、Rate Limit、出站白名单和 Secret Rotation。

### 8.4 可观测性

第一阶段必须统一关联下列信号，具体 SDK、协议和后端产品仍由专项选型决定：

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

Router、OAuth、Retrieval、Generation、Grounding、Citation、Release 和 Revocation 必须在同一 Trace 中可关联。日志默认不记录完整敏感 Prompt；调试采样需要脱敏、限期保留和审计。

## 9. 交付批次与依赖顺序

以下批次是已经接受的交付分解，不是对任何尚未完成选型的自动批准。七天内的并行编排、每日产物和退出门禁见 [`0002-phase-1-seven-day-execution-route.md`](0002-phase-1-seven-day-execution-route.md)。批次可在合同稳定后并行，但退出门禁不能跳过。

| 批次 | 主要目标 | 前端 | Java 后端 | 在线 AI | 批处理 / 数据 / 基础设施 | 退出门禁 |
| --- | --- | --- | --- | --- | --- | --- |
| `P1-00` | 合同与测试基座 | 消费 OpenAPI/SSE 夹具，建立共享状态机测试 | 固定 Public API、内部 Context、事件和错误合同；建立 Flyway 基线 | 固定领域 DTO、Retrieval/Evidence/Model Port 合同 | 固定 Kafka/Celery/Evaluation Schema；建立 Alembic 与 Projection Schema 基线；准备密封测试集 | 合同与 Migration 校验通过；所有层能用同一 Trace/ID/错误语义集成 |
| `P1-01` | Project 与 Source 接入 | Project、Version、Space、上传和任务页 | MySQL Project Catalog、SourceRevision、OSS 登记、Outbox | 仅建立受认证内部入口与 Context 校验 | Source Zone、Kafka Dispatcher、Celery 幂等任务 | 上传只能进入 Source Zone；MySQL 事务、Outbox 和重复消费通过 |
| `P1-02` | 治理与 Staging 构建 | 治理审核、扫描/解析结果和失败处置 | MySQL 治理状态、审核权限、Worker 结果投影 | 提供 Embedding/模型任务端口合同 | Scan、Parse/OCR、Deduplicate、Chunk、Embed、OSS Manifest、ES BM25 与 pgvector Staging | 原文 Offset/Citation 可重建；两套投影 Manifest Hash 一致；恶意或未审核内容不能进入 Candidate |
| `P1-03` | 单项目检索与回答 | Project Search/Chat、Citation、拒答和降级 | PUBLIC 短期 Session、Message、Search、Context、SSE 代理 | Elasticsearch BM25、pgvector Vector、RRF、Reranker、Evidence、Generator、Grounding | 检索和回答评测集、两套 Published 测试投影 | 两路先过滤后召回；质量、Citation、未验证输出和延迟门禁达到 1A 基线 |
| `P1-04` | 发布、回滚、撤回和删除 | Candidate 报告、双人审批、换版、回滚、撤回状态 | MySQL Release 状态机、Active Release 原子切换、Rollback、Revoke、Successor Session | 每请求复核 Release/Revocation；旧租约拒绝 | Joint Projection Gate、ActivationPrepared、Tombstone、两套投影重建 | MySQL 是唯一发布提交点；“导入到删除传播”通过；紧急撤回 P95 不超过 60 秒 |
| `P1-05` | 1A 联合验收 | 完整管理员与消费者 E2E | 状态、审计、幂等和失败恢复 | 质量、Grounding 和降级矩阵 | 增量、全量、恢复和容量压测 | 1A 上线门禁关闭；Source/Governance 无外部访问路径 |
| `P1-06` | 身份、Grant 与 Session | 登录、Guest、授权、历史、收藏和权限变化 | OIDC、Cookie、Grant、ABAC、Session/Thread、Token 和对象授权 | 应用 Subject/Client/Authz Context 和 Project Memory Key | Redis Online Session/Revocation、ACL 评测 | 三类 Access Segment 通过；Token 混用、IDOR、撤权泄露为 0 |
| `P1-07` | 统一 UI、SDK 与 Embed | Portal、Project Page、Web Component、TypeScript Client 一致实现 | Bootstrap Token、Origin、Client、SSE 恢复和审计 | 稳定错误、换版和已验证事件合同 | Gateway/SSE/Origin/容量联调环境 | 核心协议、Citation、范围、项目切换和错误组件复用 100%；Bootstrap 重放为 0 |
| `P1-08` | 1B 联合验收 | 标准项目接入回归和跨 Origin E2E | Grant/Client 撤销传播、OIDC 攻击面、对象授权 | Session 换版、Memory、错误与降级 | 安全、容量和可观测性联调 | 跨 User、Project、Client、Session、Deployment 越权为 0；撤销时延达标 |
| `P1-09` | Global Router 与 Project Thread | 候选、澄清、显式切换和 Thread UI | 授权候选集、Global Session、Thread、GlobalResultReference | 三层 Router、ProjectQueryPlan、隔离 Context | 路由/跨项目密封评测集 | 固定 Project Router 调用为 0；单项目路由准确率不低于 95% |
| `P1-10` | 跨项目 Evidence 聚合 | 跨项目 Claim/Citation、确认和 partial coverage | fan-out 控制、结果授权、Claim 遮蔽和审计 | 独立项目分支、EvidencePacket、Aggregator、一次最终生成 | 跨项目性能、成本、权限和失败注入 | 多项目拆分不低于 90%；每问 Generator 1 次；Memory 污染和漏标 partial coverage 为 0 |
| `P1-11` | 第一阶段生产门禁 | 全入口回归、可访问性和用户流程 | 全状态机、安全、审计、MySQL Migration 与备份恢复 | 全质量、模型回退和延迟矩阵 | pgvector Migration、两套投影容量/恢复和删除演练 | `tech-plan.md` 第 13 章全部门禁关闭并形成可审计报告 |

关键依赖如下：

```text
P1-00
  -> P1-01 -> P1-02 -> P1-03 -> P1-04 -> P1-05
                                        |
                                        `-> P1-06 -> P1-07 -> P1-08
                                                              |
                                                              `-> P1-09 -> P1-10 -> P1-11
```

`P1-06` 的身份合同和 `P1-07` 的 UI 包可以在 `1A` 后半段并行开发，但必须基于已稳定的 Session、SSE、Citation 和 Release 语义。`1C` 可以提前建设评测集和 Router 端口，不能在授权候选集、Project Thread 和 Memory 隔离未完成前接入真实 Global 流量。

## 10. 测试与验收矩阵

### 10.1 测试层次

| 测试层次 | 必须证明的内容 |
| --- | --- |
| 单元测试 | 各层状态机、领域规则、过滤、RRF、Grounding、Token 校验、幂等和错误映射 |
| Schema/合同测试 | OpenAPI、SSE、Execution Context、Kafka、Celery、Evidence 和 Evaluation Report 的生产者/消费者兼容 |
| 组件集成测试 | MySQL 事务/Outbox/Flyway、PostgreSQL/pgvector Filter/Rank/Alembic、Redis 原子操作、Kafka 重放、Celery 重试、Elasticsearch BM25/Filter/Template 和模型 Adapter |
| 跨服务集成测试 | Java -> Python mTLS Context、Validated SSE 代理、Kafka -> Celery -> Kafka 状态闭环和 Release 激活 |
| E2E | 门户、项目页、Web Component 的导入、治理、发布、问答、换版、撤回、登录、授权、项目切换和跨项目流程 |
| 安全测试 | Source/Governance 隔离、ACL 矩阵、Token 混用、IDOR、OIDC、CSRF、重放、Origin、Prompt Injection、PII/Secret 泄露 |
| 质量评测 | Retrieval、Reranker、Claim-Evidence、拒答、Router、Planner、跨项目拆分和 Citation 覆盖 |
| 性能与可靠性 | Search、首个已验证片段、Validator、发布延迟、撤销传播、可用性、错误率、扩缩容、积压、恢复和成本 |

### 10.2 密封评测资产

第一阶段至少维护以下版本化评测资产：

- 代表真实项目的多语言 Published 文档、Query、Relevant Chunk 和 Citation Gold Set。
- Project、Version、Locale、Access Segment、有效期和撤回组合的 ACL Matrix。
- 有支持、矛盾、证据不足、陈旧知识、敏感信息和拒答样本组成的 Claim-Evidence Set。
- 单项目归属、歧义、多项目拆分、超 fan-out、部分失败和项目切换组成的 Global Route Set。
- 双标签页、乱序重试、Session 换版、Grant 撤销和 Thread 冲突组成的并发场景集。
- Parser/OCR/表格/代码/大文件/恶意文件/Secret/PII 样本集。
- 固定 Provider、模型、Tokenizer、Embedding Space、Analyzer、Chunker、Prompt、BM25 Index Schema 和 Vector Projection Schema Revision 的评测 Manifest。

评测训练集、调参集和最终密封验收集必须分离。任何检索参数、Prompt、模型或索引配置变化都使用同一密封集重新验证，不能只报告改进样本。

### 10.3 第一阶段硬门禁分配

| 门禁域 | 主要关闭阶段 | 核心目标 |
| --- | --- | --- |
| 产品与集成 | `1A` 管理全链路；`1B` UI/SDK；`1C` 来源标注 | 管理全链路通过；核心协议和组件复用 100%；Embed 跨项目越权 0 |
| 知识与回答质量 | `1A` 建立基线，`1B/1C` 回归 | Recall@10 不低于 90%；Top 3 有效 Evidence 不低于 85%；Claim Citation 覆盖不低于 98%；无支持事实不高于 1%；拒答精确率和召回率均不低于 90% |
| 路由、Session、Memory | `1B` 建立 Session/Memory，`1C` 关闭路由 | 单项目归属不低于 95%；多项目拆分不低于 90%；固定项目 Router/强 Planner 调用 0；项目 Memory 污染和 Thread 串写 0 |
| 身份与安全 | `1A` 数据边界/撤回，`1B` 身份/Embed，`1C` 跨项目回归 | 所有跨边界泄露、Token 伪造、IDOR、重放和审批绕过为 0；Grant/Client 撤销 P95 <= 30 秒、P99 <= 60 秒；紧急知识撤回 P95 <= 60 秒 |
| 性能、可靠性、可观测性 | 各子阶段持续测量，`P1-11` 最终关闭 | Search P95 <= 1 秒；Project 首个已验证片段 P95 <= 3 秒；Validator 单 Claim P95 <= 500 毫秒；Data Plane 月可用性 >= 99.9%；链路和成本 100% 可追踪 |

### 10.4 完整验收门禁映射

下表逐项映射 `tech-plan.md` 第 13 章的第一阶段门禁。目标值仍以 `tech-plan.md` 为权威来源；本表只确定由哪个交付批次建立证据并最终关闭。

| 门禁域 | 指标 | 目标 | 主要关闭批次 |
| --- | --- | --- | --- |
| 产品与集成 | 门户、项目页和 SDK 核心协议与交互一致 | 100% | `P1-07~P1-08` |
| 产品与集成 | Citation、范围、项目切换和错误组件复用 | 100% | `P1-07~P1-08` |
| 产品与集成 | 门户跨项目答案来源标注 | 100% | `P1-10~P1-11` |
| 产品与集成 | 项目 Embed 跨项目越权 | 0 | `P1-07~P1-08` |
| 产品与集成 | 管理全链路 | 导入、审批、增量发布、回滚、撤回和删除全部通过 | `P1-01~P1-05` |
| 知识与回答质量 | 已批准项目知识源覆盖率 | 不低于 95% | `P1-02~P1-05` |
| 知识与回答质量 | 已批准变更到可检索 P95 | 不超过 5 分钟 | `P1-04~P1-05` |
| 知识与回答质量 | Recall@10 | 不低于 90% | `P1-03~P1-05` |
| 知识与回答质量 | Top 3 存在有效 Evidence 比例 | 不低于 85% | `P1-03~P1-05` |
| 知识与回答质量 | 原子事实 Claim Citation 覆盖率 | 不低于 98% | `P1-03~P1-05` |
| 知识与回答质量 | Claim-Evidence 支持率 | 不低于 95% | `P1-03~P1-05` |
| 知识与回答质量 | 无支持事实输出率 | 不高于 1% | `P1-03~P1-05` |
| 知识与回答质量 | 有 Evidence 回答事实一致率 | 不低于 95% | `P1-03~P1-05` |
| 知识与回答质量 | 无证据拒答精确率 | 不低于 90% | `P1-03~P1-05` |
| 知识与回答质量 | 无证据拒答召回率 | 不低于 90% | `P1-03~P1-05` |
| 知识与回答质量 | 新 Revision 在活跃会话下一消息边界切换 | 100% | `P1-04~P1-05` |
| 知识与回答质量 | 超过 2 小时执行租约仍引用旧 Release | 0 | `P1-04~P1-05` |
| 路由、Session 与 Memory | 单项目归属路由准确率 | 不低于 95% | `P1-09~P1-11` |
| 路由、Session 与 Memory | 多项目拆分正确率 | 不低于 90% | `P1-10~P1-11` |
| 路由、Session 与 Memory | 固定项目请求的 Global Router 调用 | 0 | `P1-03`、`P1-09~P1-11` |
| 路由、Session 与 Memory | 固定项目简单问题的强 Planner 调用 | 0 | `P1-03~P1-05` |
| 路由、Session 与 Memory | 项目切换显式提示率 | 100% | `P1-09~P1-10` |
| 路由、Session 与 Memory | Project Memory 交叉污染 | 0 | `P1-06~P1-10` |
| 路由、Session 与 Memory | 双标签页、乱序重试或并发切换导致 Thread 串写 | 0 | `P1-06~P1-10` |
| 路由、Session 与 Memory | Memory 内容被作为无 Citation 事实使用 | 0 | `P1-06~P1-10` |
| 路由、Session 与 Memory | 跨项目回答 Generator 调用 | 每个用户问题 1 次 | `P1-10~P1-11` |
| 路由、Session 与 Memory | 跨项目部分失败未标记 `partial_coverage` | 0 | `P1-10~P1-11` |
| 路由、Session 与 Memory | 强 Router/Planner 触发率、P95 和单次成本 | 100% 可观测并按评测集设置门禁 | `P1-09~P1-11` |
| 身份与安全 | 匿名访问受限知识 | 0 | `P1-06~P1-08` |
| 身份与安全 | OAuth Scope 或 Token 伪造越权 | 0 | `P1-06~P1-08` |
| 身份与安全 | 跨 Project、Version、Access Segment 泄露 | 0 | `P1-03~P1-11` |
| 身份与安全 | 跨 User、Session、Client、Deployment IDOR | 0 | `P1-06~P1-08` |
| 身份与安全 | Bootstrap Token 跨 Origin 或重复使用成功 | 0 | `P1-07~P1-08` |
| 身份与安全 | OIDC CSRF、重放、Mix-up 和 Session Fixation | 0 | `P1-06~P1-08` |
| 身份与安全 | Grant/Client 撤销传播 | P95 不超过 30 秒，P99 不超过 60 秒 | `P1-06~P1-08` |
| 身份与安全 | 生产发布或扩大可见范围绕过双人审批 | 0 | `P1-02~P1-05` |
| 身份与安全 | 内部 Source Locator 出现在公开响应 | 0 | `P1-03~P1-11` |
| 身份与安全 | 发布前敏感信息检测和审核 | 100% | `P1-02~P1-05` |
| 身份与安全 | 紧急知识撤回生效 P95 | 不超过 60 秒 | `P1-04~P1-05` |
| 性能、可靠性与可观测性 | Search P95 | 不超过 1 秒 | `P1-03~P1-05`，`P1-11` 回归 |
| 性能、可靠性与可观测性 | Project 首个已验证片段 P95 | 不超过 3 秒 | `P1-03~P1-05`，`P1-11` 回归 |
| 性能、可靠性与可观测性 | Grounding Validator 单 Claim P95 | 不超过 500 毫秒 | `P1-03~P1-05`，`P1-11` 回归 |
| 性能、可靠性与可观测性 | 未验证事实进入 `message_delta` | 0 | `P1-03~P1-11` |
| 性能、可靠性与可观测性 | Validator 超时/异常泄露原始文本 | 0 | `P1-03~P1-11` |
| 性能、可靠性与可观测性 | Data Plane 月可用性 | 不低于 99.9% | `P1-11` |
| 性能、可靠性与可观测性 | 非用户输入导致的 Data Plane 错误率 | 低于 1% | `P1-11` |
| 性能、可靠性与可观测性 | 容量基线和月度成本预算 | 上线前完成压测和评审确认 | `P1-11` |
| 性能、可靠性与可观测性 | 所有回答记录 Project、Release、Evidence 和 Model Version | 100% | `P1-03~P1-11` |
| 性能、可靠性与可观测性 | Token 用量和估算成本按 Project/Deployment 归集 | 100% | `P1-03~P1-11` |
| 性能、可靠性与可观测性 | Router、OAuth、Retrieval、Generation、Grounding 和 Citation 链路可追踪 | 100% | `P1-06~P1-11` |

## 11. 外部选型关闭门禁

本计划只声明“何时必须完成选型”，不修改选型状态或替候选作决定。进入相应批次前，应在专项选型文档和 PoC 报告中关闭以下门禁：

| 进入批次前 | 必须关闭的选型域 | 相关 Decision ID |
| --- | --- | --- |
| `P1-01` 云联调环境 | 生产 Region、ACK 形态/节点与 KEDA 版本、OSS 参数、镜像仓库、Ingress/负载均衡、DNS、证书 | `CLOUD-003`、`CLOUD-006`、`CLOUD-007`、`CLOUD-008`、`CLOUD-009`、`CLOUD-010`、`CLOUD-011`、`CLOUD-012`、`CLOUD-013` |
| `P1-01` 业务权威数据与事件 | 托管 MySQL 产品/版本、Conversation 隔离、Flyway 版本、Kafka 兼容版本与托管产品、Redis 兼容版本与托管产品、Online/Celery 隔离参数 | `DATA-002`、`DATA-003`、`DATA-004`、`DATA-005`、`DATA-007`、`DATA-008`、`DATA-010`、`DATA-011`、`DATA-012`、`DATA-022` |
| `P1-02` 向量投影与迁移 | 托管 PostgreSQL/pgvector 产品、版本、扩展、索引、容量和 Alembic 版本 | `DATA-017`、`DATA-018`、`DATA-019`、`DATA-020`、`DATA-023`、`RET-011` |
| `P1-02` 文档治理 | Parser、版面/表格、文件识别、Malware/Secret Scanner、OCR、PII/DLP、内容安全和首批 Source Adapter | `GOV-001`、`GOV-002`、`GOV-003`、`GOV-004`、`GOV-005`、`GOV-009`、`MODEL-018`、`MODEL-019`、`IDSEC-006`、`IDSEC-007` |
| `P1-03` 检索与回答 | Elasticsearch BM25 主候选/挑战者真实实例、pgvector 联合召回、IK、Provider 合同、Generator、Grounding、Embedding Revision 和 Reranker Revision | `RET-001`、`RET-002`、`RET-003`、`RET-010`、`RET-011`、`MODEL-001`、`MODEL-002`、`MODEL-004`、`MODEL-005`、`MODEL-006`、`MODEL-007`、`MODEL-008`、`MODEL-009`、`MODEL-010`、`MODEL-011`、`MODEL-012`、`MODEL-013`、`MODEL-014`、`MODEL-015`、`MODEL-026`、`MODEL-027` |
| `P1-06` 身份与安全 | IdP/CIAM、Policy Engine、KMS、Secret 管理、WAF/DDoS 和审计归档 | `IDSEC-001`、`IDSEC-002`、`IDSEC-003`、`IDSEC-004`、`IDSEC-005`、`IDSEC-008` |
| `P1-07` 外部接入 | Public API Gateway 的 SSE、安全、容量、成本和退出方案 | `GATE-001` |
| `P1-09` Global 能力 | Global Router、Project Query Planner 的数据集、模型、Prompt、成本和回退策略 | `MODEL-016`、`MODEL-017` |
| `P1-11` 生产门禁 | Telemetry SDK/协议、日志、Metrics/告警、Trace、Dashboard 和 On-call 集成 | `OBS-001`、`OBS-002`、`OBS-003`、`OBS-004`、`OBS-005`、`OBS-006` |

产品未选定不阻止使用本地 Fake、容器兼容实现或合同夹具开发领域逻辑，但不得把开发替代品自动升级为生产选择，也不得用 Mock 结果关闭真实云产品、模型、容量、安全或合同门禁。

## 12. 发布、回滚与运行准备

- 每个批次使用短生命周期分支和单一职责提交；Schema、实现、测试和直接受影响文档在同一批次闭环。
- 开发、集成、预发布和生产使用独立配置与凭证；生产 Release 必须来自已验证的不可变构建产物。
- MySQL/Flyway 与 PostgreSQL/pgvector/Alembic 通过独立预部署 Migration Job 执行向前兼容迁移；跨版本滚动部署时才允许有删除条件的短期兼容合同。
- 每个 Migration 随实现、兼容测试和显式回滚/前向补偿方案一同合入；服务运行身份无 DDL 权限，迁移成功后才允许部署新应用 Revision。
- Knowledge Release 使用两套 Staging Projection 评测、人工审批和 Canary；只有联合准备完成后才由 MySQL Active Release 指针原子激活，失败继续服务旧 Release。
- 服务发布必须验证 SSE 排空、幂等重试、Worker Checkpoint、Kafka 重放、Redis 丢失、模型回退和两套检索投影重建。
- 在 [`../runbooks/`](../runbooks/) 中为发布、应用/Schema 回滚、迁移失败、紧急撤回、Grant/Client 撤销、Kafka/Celery 积压、模型故障、MySQL 恢复和两套检索投影重建分别建立经过演练的操作手册。
- 第一阶段上线前冻结容量输入、月度成本预算、数据保留、审计保留、RPO/RTO 和事故响应职责。

## 13. 执行交接

本方案已经完成审核。具体实施以 [`0002-phase-1-seven-day-execution-route.md`](0002-phase-1-seven-day-execution-route.md) 为当前执行入口，并遵守以下约束：

1. `P1-00~P1-11` 的范围、跨层所有权和验收门禁保持不变，七天路线只压缩等待与串行时间，不删减功能或安全不变量。
2. 开始第 1 天前必须通过执行路线的“开工前检查”；未满足时不能把等待外部资源的时间伪装成开发进度。
3. 每个交付批次必须保留输入、输出、Owner、依赖、验收命令和关联选型门禁的执行记录。
4. 改变阶段范围、系统边界或第一阶段完成定义时，先回到 `tech-plan.md`、ADR 和本方案评审，不在七天路线中暗改。
