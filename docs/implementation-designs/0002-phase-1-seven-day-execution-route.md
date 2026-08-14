# 第一阶段七天执行路线

| 属性 | 内容 |
| --- | --- |
| 路线文档状态 | ACCEPTED，表示本路线已经批准 |
| 项目执行状态 | NOT_STARTED，表示开工前检查尚未完成，七天倒计时还没有开始 |
| 计划范围 | 第一阶段 1A、1B、1C |
| 计划周期 | 开工前检查全部通过后，连续 7 个自然日 |
| 第 7 天输出 | 第一阶段开发完成，生成可部署、可回滚、可验证的待发布候选版本 |
| 当前下一步 | 先完成本地集成环境与真实数据库/消息/对象存储适配，再关闭第 3 节“开工前检查”；七天倒计时仍未开始 |
| 详细范围与门禁 | [第一阶段执行方案](0001-phase-1-execution-plan.md) |
| 工作区工具链 | [技术栈与外部选型总览](../technology-selection/technology-selection.md)；前端、Python 与 Java 工程基线已初始化 |
| 架构依据 | [tech-plan.md](../tech-plan.md)、[architecture.md](../architecture.md) |
| 最后更新 | 2026-08-13 |

## 1. 先读懂这条路线

这条路线按下面的顺序执行：

~~~text
开工前检查
  -> 第 1 天：建立代码工程、跨层接口和知识接入入口
  -> 第 2 天：打通知识治理、文档处理和待发布索引
  -> 第 3 天：完成阶段 1A，交付单项目公开问答
  -> 第 4 天：完成阶段 1B，交付身份、统一 UI 和项目嵌入
  -> 第 5 天：完成阶段 1C，交付跨项目路由和问答
  -> 第 6 天：停止新增功能，集中处理安全、性能和故障恢复
  -> 第 7 天：全量验收，生成待发布候选版本
~~~

### 1.1 文档中的几个状态分别表示什么

| 术语 | 明确含义 |
| --- | --- |
| ACCEPTED | 这份路线已经通过审核，可以作为执行依据；不表示开发已经开始 |
| NOT_STARTED | 开工前检查还没有全部通过，七天倒计时没有开始 |
| IN_PROGRESS | 开工前检查已经全部通过，项目正在执行第 1 天到第 7 天的任务 |
| BLOCKED | 外部账号、环境、产品能力或必须由人决定的事项阻断了关键路径 |
| INCOMPLETE | 已到计划检查点，但规定功能或验收条件没有全部完成 |
| DEVELOPMENT_COMPLETE | 第 7 天最终条件全部通过，第一阶段开发完成 |
| 开工前检查 | 开发需要的人员、工具、环境、账号、数据集和容量输入已经就绪；不计入 7 天 |
| 当天完成 | 当天列出的系统行为和检查项全部通过；只写完代码不算完成 |
| 第一阶段开发完成 | 第一阶段所有功能已经编码、联调和验证，50 条验收门禁均有当前版本证据 |
| 待发布候选版本 | 已完成开发验收、可以部署和回滚的固定版本，但还没有自动发布到生产 |
| 生产上线 | 对待发布候选版本执行正式发布审批和生产部署；不由本路线自动触发 |

月可用性需要上线后按月持续统计，七天内无法产生一个月的真实运行数据。第 7 天需要完成可用性设计、故障演练、监控和告警配置；上线后的真实月度数据继续按 SLO 统计。

### 1.2 七天计划采用什么执行方式

七天计划要求前端、Java 后端、在线 AI、知识批处理、基础设施和测试并行推进。它不是单人顺序开发工期，也不包含等待云账号、模型权限、产品选型或测试数据的时间。

为赶日期而删除第一阶段功能时，结果只能标记为范围缩减版本，不能标记为第一阶段完成。

## 2. 每个层次负责什么

| 层次 | 本阶段负责的工作 | 明确不负责的工作 |
| --- | --- | --- |
| 跨层接口与集成 | 维护 OpenAPI、SSE、Java 到 Python 的执行上下文、Kafka 事件、Celery 任务、统一错误和测试夹具 | 不在各服务之间口头约定未登记字段 |
| 前端 | 企业门户、项目知识页、治理控制台、统一聊天组件、React Web Component 和 TypeScript Client | 不计算授权范围，不指定 Release、Access Segment 或模型 |
| Java 后端 | Project、Identity、Grant、Session、Thread、Release、任务状态、审计、Outbox 和公开 API | 不实现检索融合、Evidence、Grounding 或模型编排 |
| 在线 AI | 项目范围校验、查询计划、Elasticsearch BM25、pgvector Vector、RRF、Reranker、Evidence、生成、Grounding、Citation 和跨项目路由 | 不修改 MySQL 权威业务状态，不接受客户端自造范围 |
| 知识批处理 | 扫描、解析/OCR、去重、Chunk、Embedding、索引构建、发布评测、索引激活和删除传播 | 不决定审批结果，不保存 Release 或任务状态真相 |
| 基础设施与测试 | 本地和集成环境、CI、部署配置、安全测试、性能测试、可观测性、恢复演练和发布证据 | 不用 Mock 结果代替真实云服务和真实模型门禁 |

## 3. 开工前检查，不计入 7 天

所有检查项必须有负责人、证据和明确状态。全部通过后记录实际开始日期，并将当前执行状态改为 IN_PROGRESS。

| 检查项 | 通过条件 | 未通过时怎么办 |
| --- | --- | --- |
| 执行责任 | 前端、Java 后端、在线 AI、知识批处理、基础设施与测试均有负责人和替补 | 不启动第 1 天 |
| 仓库权限 | 可以创建短分支、运行 CI、合并到受保护 main | 先解决权限 |
| 工具版本 | 前端包管理器、Node、Java 构建工具、JDK、Python、uv、Flyway、Alembic 和 Schema 生成方式已经固定 | 先完成工具选型和版本冻结 |
| 本地集成环境 | MySQL、PostgreSQL/pgvector、Kafka、Redis Online、Redis Celery、Elasticsearch 和对象存储兼容环境可以访问；两个独立 Migration Job 可以运行 | 先搭建环境 |
| 真实云联调环境 | MySQL、PostgreSQL/pgvector、Kafka、Redis、Elasticsearch、网关、身份、安全、解析和可观测性产品已有批准的联调环境 | 只能继续本地开发，不能关闭生产门禁 |
| 模型权限 | Embedding、Reranker、Generator、Grounding、Router 和 Planner 的账号、配额、模型 Revision 与地域条件可用 | 不能开始依赖该模型的验收 |
| 测试数据 | Published 文档、权限矩阵、Claim-Evidence 数据集、路由数据集、Parser/OCR/安全样本已经准备并冻结版本 | 先建设评测集 |
| 测试身份 | Guest、平台用户、项目授权用户、编辑者、审批者、管理员、OAuth Client 和跨 Origin 场景可用 | 不能关闭身份安全门禁 |
| 容量输入 | 项目数、文档数、Chunk 数、QPS、SSE 并发、Token、变更率、重建窗口和成本预算已确定 | 不能关闭性能和成本门禁 |
| 当日决策人 | 产品范围、外部账号、安全事件和不可逆操作均有当天可以响应的决策人 | 阻断问题不得悬空过夜 |

通过规则只有一条：十项全部通过才开始计算七天。部分通过不等于已经开工。

截至 2026-08-14，Node/pnpm、Python/uv 与 Java/Maven 工作区版本已经固定并初始化；`P1-00` 已交付最小 Public OpenAPI、SSE envelope、SourceRevision Kafka Event、Celery JSON Task、统一错误/幂等字段，以及 Flyway/Alembic 首个迁移基线。`P1-01` 已建立 Java SourceRevision/Task/Outbox 领域骨架、上传完成后的内容元数据校验和基于 AWS SDK for Java v2 的 S3-compatible Source Storage Adapter；Python Dispatcher 已通过严格合同测试；`infra/local` 已建立覆盖 MySQL、PostgreSQL/pgvector、Kafka、双 Redis、Elasticsearch 和 OSS 兼容存储的 Compose 定义、独立对象存储初始化 Job、独立 Migration Job 与验证脚本，但当前 Docker daemon 不可用，真实容器启动、MinIO 上传和迁移执行证据仍未形成。MySQL 业务连接、Kafka Outbox Publisher、Celery Worker、PostgreSQL/pgvector 投影写入和跨语言代码生成方式仍未完成。因此十项开工条件尚未全部关闭，项目状态继续保持 `NOT_STARTED`，七天倒计时没有开始。

当前已完成但不等于端到端完成的边界：

```text
已完成：合同文件 + 有效示例 + Python 消费测试
已完成：Flyway MySQL V1 / Alembic pgvector V1 离线迁移基线与独立 Migration Job 入口
已完成：本地 Compose 依赖、数据库身份边界、健康检查和重复迁移验证脚本
已完成：Java 上传预约/完成校验/幂等与 Outbox 持久化骨架
已完成：S3-compatible Source Storage Adapter、服务端 Source Zone key、MinIO bucket/最小对象身份初始化 Job
已完成：Python SourceRevisionSubmitted -> Celery JSON Task 转换
未完成：本地容器实际启动证据、MinIO 实际上传、MySQL 业务连接、Kafka 发布、Celery Worker、Portal 页面和跨服务 E2E
```

## 4. 七天总览

| 天数 | 当天唯一主目标 | 当天结束后必须能看到的结果 | 对应交付批次 |
| --- | --- | --- | --- |
| 第 1 天 | 建立工程和知识接入入口 | 上传一个文件后，系统保存源文件、登记修订记录并可靠发出处理事件 | P1-00、P1-01 |
| 第 2 天 | 生成可审核的知识候选 | 一个源文件经过扫描、解析、Chunk、Embedding 和评测后成为待发布候选 | P1-01、P1-02 |
| 第 3 天 | 完成阶段 1A | 管理员可以发布、回滚和撤回；匿名用户可以在固定项目中搜索、问答并查看引用 | P1-03、P1-04、P1-05 |
| 第 4 天 | 完成阶段 1B | 用户可以登录、保存会话；宿主项目可以通过 Web Component 和 TypeScript Client 接入 | P1-06、P1-07、P1-08 |
| 第 5 天 | 完成阶段 1C | 门户可以在授权项目中路由、切换项目并生成带项目来源的跨项目答案 | P1-09、P1-10 |
| 第 6 天 | 完成生产前加固 | 主要故障、越权、并发、恢复和性能场景全部通过，无新增功能 | P1-11 预验收 |
| 第 7 天 | 完成第一阶段开发验收 | 从干净环境构建并验证全部功能，生成唯一待发布候选版本和证据包 | P1-11 |

最后一列的 P1 编号只用于回查[第一阶段执行方案](0001-phase-1-execution-plan.md)中的详细范围和验收指标。执行人员不需要先解释这些编号，按本表和对应日期章节执行即可。

任何一天没有通过结束检查时：

1. 该日不得标记为完成。
2. 与失败项无依赖的工作可以继续。
3. 依赖失败项的后续功能不得标记为完成。
4. 外部账号、环境或产品能力缺失时，将执行状态改为 BLOCKED。

## 5. 第 1 天：建立工程、接口和知识接入入口

### 当天目标

所有层使用同一组接口定义开始开发，并打通“上传文件 -> 保存源文件 -> 登记修订 -> 发出处理事件”。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 在 `contracts/` 定义 Public OpenAPI、SSE 事件、Java 到 Python 执行上下文、Kafka 事件、Celery JSON 任务、统一错误和幂等规则 | 第一版接口文件、示例和兼容测试 |
| 前端 | 在 `apps/portal-web/`、`packages/assistant-ui/` 和 `packages/typescript-client/` 创建正式工程；接入生成的 API 类型；实现项目列表、知识空间、上传和任务状态页面 | 可以选择项目并上传文件的页面 |
| Java 后端 | 在 `services/platform-api/` 创建模块化工程；实现 Project、Project Version、Knowledge Space、Source Object、Source Revision、Task 和 Outbox；建立 Flyway MySQL 基线 | MySQL Migration、上传 API、SourceRevision 和 Outbox 事务 |
| 在线 AI | 在 `services/assistant-runtime/` 创建 uv Workspace 成员和 FastAPI 内部入口；实现执行上下文格式校验、Deadline 和 Provider 测试替身 | 只接受内部已认证请求的 Runtime 入口 |
| 知识批处理 | 在 `services/batch-worker/` 创建 uv Workspace 成员、Kafka Dispatcher 和 Celery Worker；实现 JSON 任务、幂等键和 Source Revision 消费；建立 Alembic PostgreSQL/pgvector 基线 | 可以迁移 Vector Schema、接收 SourceRevision 事件并创建任务 |
| 基础设施与测试 | 在 `infra/` 和 `tests/` 创建本地集成环境、CI 和统一验证脚本；建立独立 MySQL/pgvector Migration Job 与 Trace ID 传播检查 | 干净 Checkout 可构建并运行合同和 Migration 测试 |

### 当天结束后必须能演示

~~~text
用户在治理页面上传文件
  -> 文件进入隔离对象存储
  -> Java 在 MySQL 登记 SourceRevision、Task 和 Outbox
  -> Outbox 发布 Kafka 事件
  -> Python Dispatcher 接收事件并创建 Celery JSON 任务
~~~

### 当天结束检查

- 从干净 Checkout 可以构建前端、Java 和 Python 工作区。
- OpenAPI、SSE、内部执行上下文、Kafka 和 Celery Schema 均有版本、示例和合同测试。
- Flyway 与 Alembic 可以分别从空库建到唯一当前版本，运行应用的身份没有 DDL 权限。
- 同一个上传请求或事件重复执行时，不产生重复 Source Revision 或重复任务。
- 浏览器、模型和 Worker 不能指定 Project、Release 或内部 Source Locator。
- 当日合入 main 的提交全部通过统一验证。

## 6. 第 2 天：生成可审核的知识候选

### 当天目标

打通“Source Revision -> 安全扫描 -> 解析/OCR -> 去重 -> Chunk -> OSS Manifest -> Embedding -> BM25/Vector Staging Projection -> 发布评测”。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 定义 Worker Progress、CandidateReady、Evaluation Report、Release Manifest 和内部 Citation 格式 | Worker 到 Java 的进度与候选合同 |
| 前端 | 实现治理任务、扫描结果、解析结果、失败原因、Knowledge Revision、评测报告和候选状态页面 | 内容人员可以查看并处理治理结果 |
| Java 后端 | 实现治理状态、编辑/审批权限、Worker 结果投影、Knowledge Revision 和 Release Candidate | MySQL 中可追踪的治理与候选状态 |
| 在线 AI | 实现 EmbeddingPort、模型 Revision 校验、批量限制、错误分类和出站最小化 | 可替换且可审计的 Embedding Adapter |
| 知识批处理 | 实现扫描、解析/OCR、SHA-256 去重、MinHash/LSH 审核信号、结构感知 Chunk、OSS Chunk Manifest、Embedding、Elasticsearch BM25 Staging、pgvector Vector Staging 和增量评测 | 从同一 Manifest 生成两套待发布投影 |
| 基础设施与测试 | 测试恶意文件、Secret/PII、超限文件、解析失败、模型超时、重复事件、两套投影批量写部分失败和 Alembic 中断重试 | 批处理、投影与迁移失败恢复报告 |

### 当天结束后必须能演示

上传一个受支持文件后，治理页面可以看到：

1. 扫描与解析状态。
2. 每个 Chunk 的标题、章节路径和原文位置。
3. 使用的 Chunker、Embedding 模型 Revision、BM25 Index Schema 和 Vector Projection Schema 版本。
4. 检索、ACL 和泄露评测结果。
5. 候选是否具备提交审批的资格。

### 当天结束检查

- Data Plane 没有访问 Source/Governance Zone 的凭证和网络路径。
- prose、FAQ、API、Release Notes、Policy、Table 和 Code 均使用明确的 Chunk Profile。
- 每个 Chunk 可以还原到原文位置并生成 Citation。
- Release Candidate 固定 Analyzer、Chunker、Embedding Space、模型 Revision、RRF、Reranker、BM25 Index Schema Version 和 Vector Projection Schema Version。
- Elasticsearch 与 PostgreSQL/pgvector 的 Chunk 数、Manifest Hash 和 Project/Release/Access 过滤元数据一致，两套 Watermark 均指向同一 Release/Manifest。
- 未通过扫描、治理或评测的内容不能进入发布审批。

## 7. 第 3 天：完成阶段 1A，交付单项目公开问答

### 当天目标

打通知识发布和固定项目问答，并完成回滚、紧急撤回和删除传播。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 定义 Search、Project Message、Validated SSE、Citation、Activation、Rollback、Revocation 和 Tombstone | 单项目问答与发布接口 v1 |
| 前端 | 实现项目公开知识页、搜索、聊天、Citation、Evidence-only、拒答、降级、审批、发布、换版、回滚和撤回界面 | 匿名用户问答页面与发布控制界面 |
| Java 后端 | 实现 PUBLIC 短期 Session、不可变执行上下文、Release 状态机、双人审批、激活、回滚、撤回、SSE 代理和审计 | 已发布 Release 的权威状态和问答入口 |
| 在线 AI | 实现范围/撤回校验、ProjectQueryPlan、Elasticsearch BM25 和 PostgreSQL/pgvector Vector 独立召回、RRF、Reranker、Evidence Hub、Prompt、Generator、Grounding、Citation 和已验证 SSE | 固定项目 RAG 全链路 |
| 知识批处理 | 实现发布评测、ActivationRequested、Joint Projection Gate、ActivationPrepared、Tombstone、两套投影清理和重建 | 可准备、可回滚、可撤回的 BM25/Vector Published Projection |
| 基础设施与测试 | 运行阶段 1A E2E、检索质量、回答质量、降级、发布并发、回滚、撤回时延、删除传播和 Source 隔离测试 | 阶段 1A 验收报告 |

### 当天结束后必须能演示

~~~text
内容人员提交并由另一名审批者批准
  -> 新 Release 激活
  -> 匿名用户在固定项目提问
  -> 系统只检索该项目已发布知识
  -> 用户看到经过 Grounding 的回答和 Citation
  -> 管理员回滚或紧急撤回
  -> 下一次检索不再引用已撤回内容
~~~

### 当天结束检查

- 完整通过“导入、治理、审批、发布、问答引用、回滚、撤回、删除传播”。
- Project、Release、Locale、Access Segment 和撤回过滤在 BM25 与 Vector Top-K 前生效。
- 两套投影没有全部准备完成时，MySQL Active Release 不得切换；切换后两路查询都使用同一固定 `knowledge_release_id`。
- 未验证文本进入 message_delta 的数量为 0。
- 公开响应中出现内部 Source Locator 的数量为 0。
- 新 Revision 在下一条消息边界生效；超过两小时租约仍引用旧 Release 的数量为 0。
- 紧急撤回 P95 不超过 60 秒。

## 8. 第 4 天：完成阶段 1B，交付身份、统一 UI 和项目嵌入

### 当天目标

让用户可以登录、保存会话和访问授权知识，让宿主项目可以安全嵌入统一聊天组件。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 定义 OIDC/Session、ProjectGrant、Bootstrap Token、Session Token、Thread、History、Favorite、Feedback 和 Embed 错误 | 身份、会话和 Embed 接口 v1 |
| 前端 | 实现企业门户、Guest/Login、Conversation、History、Favorite、Feedback、React Web Component、TypeScript Client、Token 内存保存和 Origin 校验 | Portal 与可发布的前端接入包 |
| Java 后端 | 实现 OIDC Code + PKCE、第一方 Cookie、ProjectGrant/ABAC、三类 Access Segment、对象授权、Bootstrap JTI、防重放、Session/Thread 和撤权 | 身份、授权和会话闭环 |
| 在线 AI | 重新校验 Subject、Client、Session、Binding、Release 和授权上下文；实现 Project Memory Key、Successor Session 和旧 Evidence 隔离 | 受身份和项目范围约束的问答 |
| 知识批处理 | 将 Access Segment、Audience Policy、有效期和 Citation URL 投影到 Chunk；处理权限收窄 Tombstone | 三类访问范围的 Published Projection |
| 基础设施与测试 | 测试 Token 混用、IDOR、CSRF、OIDC Mix-up、Session Fixation、跨 Origin、Bootstrap 重放、撤权、双标签页和 SSE 重连 | 阶段 1B 安全与集成报告 |

### 当天结束后必须能演示

1. 匿名用户只能访问 PUBLIC 知识。
2. 平台登录用户可以保存并恢复 Conversation。
3. 项目授权用户可以访问 PROJECT_AUTHORIZED 知识。
4. 宿主后端签发一次性 Bootstrap Token。
5. Web Component 创建绑定 Subject、Client、Origin 和 Deployment 的 Session。
6. Grant 被撤销后，历史消息和下一次问答都按当前权限收窄。

### 当天结束检查

- Portal、项目页和 Web Component 使用相同消息、Citation、范围和错误组件。
- 匿名访问受限知识、Token 伪造越权和跨对象 IDOR 均为 0。
- Bootstrap Token 跨 Origin 或重复使用成功均为 0。
- Grant/Client 撤销传播达到 P95 不超过 30 秒、P99 不超过 60 秒。
- 双标签页、乱序重试和并发切换导致 Thread 串写为 0。
- Memory 被当作无 Citation 事实使用的数量为 0。

## 9. 第 5 天：完成阶段 1C，交付跨项目问答

### 当天目标

让企业门户只在用户已授权项目中完成项目识别、澄清、显式切换和跨项目 Evidence 聚合。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 定义授权项目候选集、GlobalRoutePlan、ProjectQueryPlan、EvidencePacket、GlobalResultReference 和 partial_coverage | 跨项目路由与聚合接口 v1 |
| 前端 | 实现项目候选、路由中、需要澄清、跨项目确认、显式切换、逐 Claim 来源和部分覆盖展示 | Global Assistant 用户界面 |
| Java 后端 | 实现 Global Deployment/Session、授权候选集、Project Thread、fan-out、GlobalResultReference、读取时重新授权和 Claim 遮蔽 | 跨项目会话与结果状态 |
| 在线 AI | 实现规则、轻量分类、强模型三层 Router；复核 Router Schema；为每个项目建立独立执行上下文；聚合 EvidencePacket 并只做一次最终生成 | Global Router 与 Global Aggregator |
| 知识批处理 | 建设单项目归属、多项目拆分、歧义、超 fan-out、部分失败、跨项目 ACL 和 Memory 隔离评测集 | 版本化路由评测数据 |
| 基础设施与测试 | 测试 Router 准确率、Planner 触发、跨项目 Citation、成本、并发、分支超时、Grant 失效和信息泄露 | 阶段 1C 验收报告 |

### 当天结束后必须能演示

~~~text
用户在企业门户提问
  -> Java 先计算用户有权访问的项目
  -> Router 只能从这些项目中选择
  -> 每个项目使用独立 Release、权限、Thread 和 Memory 检索
  -> Global Aggregator 合并 EvidencePacket
  -> Generator 只调用一次
  -> 每个 Claim 显示实际项目、版本和 Citation
  -> 某个项目失败时明确显示 partial_coverage
~~~

### 当天结束检查

- 固定项目请求调用 Global Router 的次数为 0。
- 固定项目简单问题调用强 Planner 的次数为 0。
- 单项目归属路由准确率不低于 95%。
- 多项目拆分正确率不低于 90%。
- 项目切换显式提示率为 100%。
- Project Memory 交叉污染为 0。
- 每个跨项目问题只调用一次最终 Generator。
- 跨项目部分失败未标记 partial_coverage 的数量为 0。

## 10. 第 6 天：停止新增功能，完成生产前加固

### 当天目标

不再增加产品功能，只验证失败场景、安全边界、性能、容量、可观测性和恢复能力。

### 各层具体任务

| 层次 | 要做的事情 | 当天必须交付 |
| --- | --- | --- |
| 跨层接口与集成 | 冻结 v1 接口；测试兼容字段、未知字段、重复/乱序事件、Deadline 和统一错误 | v1 合同冻结记录 |
| 前端 | 测试长内容、移动视口、键盘、可访问性、断连恢复、权限收窄和 Session 换版 | 全入口前端回归报告 |
| Java 后端 | 测试 MySQL 事务回滚、Outbox 原子性、Flyway 空库/N-1/中断重试/滚动兼容、并发审批、Token 撤销、Thread 乐观锁、审计完整性和优雅终止 | Java、MySQL Migration 可靠性与安全报告 |
| 在线 AI | 测试 Provider 超时、限流、无效输出、BM25-only、RRF fallback、Evidence-only、拒答、模型回退和 Prompt Injection | AI 降级与安全报告 |
| 知识批处理 | 测试 Kafka 重放、Celery 重试/崩溃/DLQ、Alembic 空库/N-1/中断重试/单一 Head、全量与增量隔离、Joint Projection Gate 失败、Tombstone 和两套检索投影重建 | 批处理、pgvector Migration 与投影恢复报告 |
| 基础设施与测试 | 执行性能、容量、成本、安全、故障注入、MySQL 备份恢复、pgvector/Elasticsearch 重建、Trace/Metric/Log 关联和 Runbook 演练 | 生产前预验收报告 |

### 当天结束检查

- 所有零容忍安全指标通过。
- Blocker 和 Critical 缺陷数量为 0。
- Search、首个已验证片段、Grounding、发布、撤权和撤回时延达到执行方案目标。
- 每个回答都记录 Project、Release、Evidence、Model Version、Token 和成本。
- Router、OAuth、Retrieval、Generation、Grounding、Citation、Release 和 Revocation 可以通过同一个 Trace 关联。
- MySQL PITR、Flyway/Alembic 迁移失败、PostgreSQL/pgvector 与 Elasticsearch 重建、Redis 丢失、Kafka 重放和模型故障演练通过。

第 6 天结束后禁止新增功能。第 7 天只允许修复、复测、归档和发布准备。

## 11. 第 7 天：完成全量验收并生成待发布候选版本

### 当天目标

从干净环境重新构建和验证所有产物，确保最终证据属于同一个代码 Revision。

### 当天执行顺序

| 顺序 | 要做的事情 | 必须得到的产物 |
| --- | --- | --- |
| 1 | 从干净 Checkout 构建四个 Deployment，重建本地和集成环境 | 可复现构建记录 |
| 2 | 运行单元、合同、组件、跨服务、MySQL/Flyway 和 PostgreSQL/pgvector/Alembic 迁移测试 | 完整自动化测试报告 |
| 3 | 运行导入、治理、发布、Project RAG、身份、Embed、Global RAG、回滚、撤回和删除传播 E2E | 第一阶段端到端报告 |
| 4 | 运行密封质量评测、权限矩阵、安全测试、性能容量、故障注入和恢复演练 | 50 条门禁证据包 |
| 5 | 修复失败项后，只重新生成一次候选版本并复跑受影响测试 | 唯一待发布候选版本 |
| 6 | 固定代码、Schema、模型、Prompt、索引和配置 Revision | Release Manifest、变更记录和 Runbook |

### 第一阶段开发完成的最终条件

- 50 条第一阶段验收门禁均有当前 Revision 的证据。
- Blocker、Critical 和零容忍安全失败数量均为 0。
- 四个 Deployment 可以部署、回滚和重建。
- 所有外部依赖都使用已批准的产品、版本、Region、配置和模型 Revision。
- 待发布候选版本没有混入未登记的 Mock、测试账号或本地替代品。

任一条件失败时，执行状态保持 INCOMPLETE。禁止使用“基本完成”“只差上线”或“后续补测”替代明确状态。

## 12. 每天如何开发和合并

| 时间节点 | 固定动作 |
| --- | --- |
| 当天开始 | 确认上一日状态、当天唯一目标、接口版本和阻断项 |
| 接口确认后 | 前端、Java、Python 使用同一份 Schema 和测试夹具并行开发 |
| 当天中段 | 合并第一批可运行改动，进行跨层冒烟测试 |
| 当天冻结 | 停止新增范围，只修复当天集成问题 |
| 当天结束 | 运行当天结束检查；只有通过验证的提交才能进入 main |

所有工作使用当天可以合入的短生命周期分支，不建立持续七天的巨型分支。Day 4 结束后冻结 v1 接口；确需变更时必须增加兼容版本和迁移测试。

## 13. 统一验证入口

当前已经存在：

~~~sh
./tools/verify-repository.sh
~~~

第 1 天必须创建以下统一入口，供本地和 CI 使用：

~~~sh
./tools/verify-all.sh
./tools/test-contracts.sh
./tools/test-e2e-phase1.sh
./tools/evaluate-phase1.sh
./tools/test-security-phase1.sh
./tools/test-performance-phase1.sh
~~~

这些脚本在当前仓库尚不存在，不能在创建前被写入验证结果。真实云或模型测试必须显式配置；默认验证不得访问或修改外部环境。

## 14. 第 7 天必须交付什么

| 层次 | 必须交付的产物 |
| --- | --- |
| 前端 | Portal、项目页、治理控制台、Assistant UI、React Web Component、TypeScript Client、组件测试和 E2E |
| Java 后端 | platform-api、MySQL/Flyway Migration、身份授权、Session/Thread、Knowledge/Release、Outbox、审计和测试 |
| 在线 AI | FastAPI Runtime、受约束 RAG Kernel、Elasticsearch BM25 Adapter、pgvector Vector Adapter、Model Adapter、Project/Global 路由、Evidence/Citation/Grounding 和质量测试 |
| 知识批处理 | Kafka Dispatcher、Celery Worker、Alembic Migration、解析/OCR、Chunk、OSS Manifest、Embedding、BM25/Vector 投影、评测、准备、撤回和恢复测试 |
| 数据与部署 | MySQL、PostgreSQL/pgvector、OSS、Kafka、双 Redis、Elasticsearch 配置，两个独立 Migration Job，以及四个 Deployment 的网络、身份、扩缩容和备份定义 |
| 合同与质量 | OpenAPI、SSE、内部接口、事件 Schema、生成类型、50 条门禁证据、容量成本报告、安全报告和评测 Manifest |
| 运行保障 | 发布、应用/Schema 回滚、迁移失败、撤回、撤权、积压、模型故障、MySQL 恢复和两套检索投影重建 Runbook 及演练记录 |

## 15. 阻断和降级怎么处理

- 一个问题持续两小时仍影响当天主目标时，立即提交给对应决策人，不等到日终。
- 外部 Provider 瞬时故障时，可以验证 BM25-only、RRF、备用模型、Evidence-only 或拒答等既定降级行为，但降级成功不能替代主路径验收。
- 权限、撤回、Release、Evidence 或 Grounding 状态不明时必须拒绝继续，不能为了赶工放宽安全语义。
- 不稳定测试必须定位根因；重复运行碰巧通过不能作为验收证据。
- 第 6 天后发现功能范围缺失时，直接判定七天目标未完成，不通过删除范围制造按时完成的假象。
