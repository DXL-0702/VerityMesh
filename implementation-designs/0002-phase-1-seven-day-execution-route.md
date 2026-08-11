# 第一阶段七天执行路线

| 属性 | 内容 |
| --- | --- |
| 状态 | `ACCEPTED` |
| 执行状态 | `NOT_STARTED`；Day 0 入场门禁尚未核验 |
| 执行基线 | [0001-phase-1-execution-plan.md](0001-phase-1-execution-plan.md) |
| 执行范围 | 第一阶段 1A + 1B + 1C，对应 P1-00~P1-11 |
| 时间盒 | Day 0 入场门禁通过后连续 7 个自然日 |
| 目标状态 | 第一阶段功能开发完成、跨层集成完成并形成可审计 Release Candidate |
| 架构事实源 | [tech-plan.md](../tech-plan.md)、[architecture.md](../architecture.md) |
| 最后更新 | 2026-08-11 |

本文将已经接受的第一阶段执行方案压缩为七天关键路径。七天目标通过跨层合同先行、六条工作流并行、当天集成和每日硬门禁实现，不通过删除功能、跳过安全不变量或把 Mock 结果冒充真实产品验证实现。

## 1. 七天执行契约

### 1.1 Day 7 的“开发完成”

Day 7 只有同时满足以下条件，才能将第一阶段标记为开发完成：

1. portal-web、platform-api、assistant-runtime 和 batch-worker 四个 Deployment 的代码、构建、测试和部署定义全部进入可复现 Release Candidate。
2. Portal、项目页、Web Component 和 TypeScript Client 复用同一 OpenAPI、SSE、Session、Citation、错误和项目切换语义。
3. “导入 -> 治理 -> 审批 -> 增量发布 -> 单项目问答 -> 登录与 Embed -> 跨项目问答 -> 回滚/撤回 -> 删除传播”端到端链路全部通过。
4. PostgreSQL、OSS、Kafka、Redis Online、Redis Celery 和 Elasticsearch 的权威边界、幂等、失败恢复和重建路径经过真实集成验证。
5. [第一阶段执行方案](0001-phase-1-execution-plan.md) 第 10.4 节的 50 条门禁均有测试、评测、压测、配置或演练证据；零容忍安全指标不得豁免。
6. 发布、回滚、紧急撤回、授权撤销、Worker 积压、模型故障、数据恢复和索引重建 Runbook 已实际演练。
7. 工作区、主分支和 Release Candidate 均通过统一验证入口，不存在未登记的 Blocker/Critical 缺陷。

月可用性是上线后的持续 SLO，无法用七天观察窗口伪造一个月的运行事实。Day 7 必须完成可用性设计、故障注入、容量验证、SLO 指标和告警配置；真实月度结果从上线后持续计量。

### 1.2 七天目标的成立条件

当前仓库尚未包含四个运行时的产品代码，因此七天路线必须以并行工作流执行。七天不是单人顺序开发估算，也不是等待云账号、样本或产品选型的缓冲期。

- 每条工作流必须有可持续投入的执行 Owner；同一人可以承担多个 Owner，但不能把本应并行的工作重新串行后仍声称七天可完成。
- Day 0 未通过时七天时钟不启动。
- 执行中出现架构事实冲突、真实凭据缺失或外部产品硬缺口时，当天升级处理；未关闭的硬阻断不得用占位实现跨过日门禁。
- 为赶日期而删减第一阶段功能时，结果只能标记为范围缩减版本，不能标记为第一阶段完成。

## 2. Day 0 入场门禁

Day 0 是七天时钟的前置条件，不占用 Day 1。所有证据记录在执行看板并关联责任人。

| 入场条件 | 必须准备的证据 | 未满足时的处理 |
| --- | --- | --- |
| 六条工作流 Owner 已确定 | Contract、Frontend、Java、Online AI、Batch/Data、Quality/Infra 的 Owner 与替补 | 不启动 Day 1 |
| 代码与合并权限可用 | Monorepo 写权限、受保护 main、短分支规则和 CI 执行权限 | 先关闭仓库权限 |
| 工程工具链已冻结 | 前端包管理器与 Node 版本、Java 构建工具与 JDK 版本、Python/uv 版本、Schema 生成方式 | 不允许 Day 1 临时争论基础工具 |
| 本地与集成环境可用 | PostgreSQL、Kafka、双 Redis、Elasticsearch、对象存储兼容环境及隔离配置 | 只允许准备环境，不开始功能计时 |
| 真实云联调资源可用 | 执行方案第 11 章涉及的云、数据、网关、身份、安全、解析和可观测性选型门禁已关闭或已有被批准的真实 PoC 环境 | 不得用本地兼容实现关闭生产门禁 |
| 模型访问可用 | Embedding、Reranker、Generator、Grounding、Router/Planner 的账号、配额、固定 Revision、地域和数据合同 | 不启动依赖该模型的日门禁 |
| 代表性数据集可用 | Published 文档、ACL Matrix、Claim-Evidence Set、Global Route Set、Parser/OCR/安全样本及许可记录 | 先建设并密封评测资产 |
| 身份与安全测试条件可用 | Guest、平台用户、项目授权用户、编辑者、审批者、管理员、OAuth Client、Origin 和撤权场景 | 不关闭 1B 安全门禁 |
| 容量输入已冻结 | Project、Document、Chunk、QPS、SSE、Token、变更率、重建窗口和成本预算 | 不关闭性能与成本门禁 |
| 决策响应人已确定 | 产品范围、外部账号、不可逆数据操作和安全事件的当日响应人 | 阻断问题不允许悬空过夜 |

## 3. 并行工作流

| 工作流 | 主要所有权 | 七天持续产物 |
| --- | --- | --- |
| C - Contract / Integration | OpenAPI、SSE、Execution Context、Kafka、Celery、Evaluation Schema、生成类型、统一错误和跨服务测试 | 版本化合同、兼容测试、统一验证脚本和每日集成报告 |
| F - Frontend | portal-web、assistant-ui、Vue Web Component、TypeScript Client、治理和消费者体验 | Portal、项目页、治理台、Embed 包、组件/E2E 测试 |
| J - Java Platform | platform-api 模块化单体、PostgreSQL 权威模型、Identity、Session、Release、Outbox 和审计 | Java 服务、迁移、领域/集成/安全测试 |
| A - Online AI | assistant-runtime、受约束 RAG Domain Kernel、检索、Model Access、Evidence、Grounding、Citation 和 Global Router | Python 在线服务、Adapter 合同、质量与降级测试 |
| B - Batch / Data | Kafka Dispatcher、Celery、Scan、Parse/OCR、Chunk、Embedding、索引、评测、激活和 Tombstone | Python Worker、任务合同、Staging/Published 投影和恢复测试 |
| Q - Quality / Infra | CI、测试环境、部署、安全矩阵、性能、可观测性、故障注入、Runbook 和 Release Evidence | 可复现环境、质量报告、部署定义、演练记录和 Release Candidate |

工作流按领域所有权并行，不按“后端写完再通知前端”的瀑布方式串行。所有跨层依赖以 C 工作流的版本化合同和测试夹具交付。

## 4. 代码落点与关键路径

Day 1 建立以下 Monorepo 落点；具体前端和 Java 构建工具必须在 Day 0 冻结，Python 使用单一 uv Workspace 与 uv.lock：

~~~text
apps/portal-web
packages/assistant-ui
packages/typescript-client
services/platform-api
python/assistant-runtime
python/batch-worker
contracts/openapi
contracts/sse
contracts/internal
contracts/events
deploy
tests/e2e
tests/evaluation
tests/security
~~~

关键路径：

~~~text
合同与测试基座 P1-00
  -> Project / Source P1-01
  -> Governance / Staging P1-02
  -> Project RAG P1-03
  -> Release / Revoke P1-04
  -> 1A Gate P1-05
  -> Identity / Session P1-06
  -> UI / SDK / Embed P1-07
  -> 1B Gate P1-08
  -> Global Router P1-09
  -> Cross-project Aggregation P1-10
  -> Production Gate P1-11
~~~

| 日期 | 覆盖批次 | 当日集成目标 |
| --- | --- | --- |
| Day 1 | P1-00、P1-01 起步 | 合同、代码工作区、权威模型和 Source 接入形成可测试基线 |
| Day 2 | P1-01、P1-02 | Source 到 Staging Candidate 全链路 |
| Day 3 | P1-03、P1-04、P1-05 | 阶段 1A 完整闭环 |
| Day 4 | P1-06、P1-07、P1-08 | 阶段 1B 完整闭环 |
| Day 5 | P1-09、P1-10 | 阶段 1C 完整闭环 |
| Day 6 | P1-11 预验收 | 跨层安全、性能、恢复和失败注入 |
| Day 7 | P1-11 | 全量回归、证据归档和 Release Candidate |

## 5. Day 1：合同、工作区与 Source 基线

当日目标是让所有工作流在同一合同上开发，并交付真实的 Project/Source 最小链路，不建设无业务语义的空壳。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 Public OpenAPI v1、SSE v1、Immutable Execution Context v1、Kafka Event v1、Celery Task v1、统一错误与 Idempotency 合同；建立生成和兼容测试 |
| F | 建立 Portal、Assistant UI 和 TypeScript Client 工作区；生成 API 类型；实现 Project/Source 列表、上传入口和 SSE 状态机合同测试 |
| J | 建立模块化单体；实现 Project、Project Version、Knowledge Space、Source Object/Revision、Task、Outbox 基础模型和首批迁移 |
| A | 建立 uv Workspace、FastAPI 内部入口、领域 DTO/Port、Context Schema/Deadline Guard 和可替换 Provider Fake |
| B | 建立 Worker Workspace、Kafka Dispatcher、Celery JSON Task、幂等键、Queue 和本地 Source 读取边界 |
| Q | 建立 CI 和 tools/verify-all.sh；准备本地集成环境、密封夹具骨架、Trace ID 传播断言和分支保护检查 |

当日集成产物：

~~~text
Project / Knowledge Space
  -> Source 上传到隔离对象存储
  -> PostgreSQL 登记 SourceRevision + Task + Outbox
  -> Kafka SourceRevision Event
  -> Python Dispatcher 接收并生成 Celery JSON Task
~~~

Day 1 退出门禁：

- 所有 Workspace 能从干净 Checkout 完成构建、单元测试和合同测试。
- OpenAPI、SSE、Execution Context、Kafka 和 Celery Schema 均有版本、示例、错误和兼容测试。
- Source 对象先落隔离存储再登记事务状态，重复请求和重复事件不会生成重复 Revision。
- 浏览器、模型和 Worker 均不能自行构造 Project、Release 或 Source Locator。
- main 保持绿色，未完成分支不得作为次日集成依赖。

## 6. Day 2：治理、批处理与 Staging Candidate

当日目标是完成 Source -> Governance -> Staging Candidate，并让 Citation 可从 Chunk 精确重建。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 Worker Progress、CandidateReady、Evaluation Report、Release Manifest 和 Citation 内部合同 |
| F | 实现治理任务、扫描/解析结果、Knowledge Revision、失败处置、评测报告和 Candidate 状态界面 |
| J | 实现 Governance 状态、编辑/审批权限、Worker 结果投影、Knowledge Revision 和 Release Candidate 状态 |
| A | 实现 EmbeddingPort、模型 Revision 校验、批量限制、错误分类和最小化出站合同 |
| B | 实现 Scan、Parse/OCR、SHA-256 去重、MinHash/LSH 审核信号、结构感知 Chunk、Embedding、批量写 Staging 和增量评测 |
| Q | 执行恶意文件、Secret/PII、格式超限、解析失败、模型超时、重复/乱序事件和批量写部分失败测试 |

Day 2 退出门禁：

- Source/Governance 与 Published 使用独立凭证和网络路径；Data Plane 无访问 Source/Governance 的身份。
- prose、FAQ、API、Release Notes、Policy、Table 和 Code Profile 均能生成不超限 Chunk。
- 每个 Chunk 保留原文 Offset、标题、章节路径、Locale、Access Segment 和 Citation 重建字段。
- Staging Candidate 固定 Analyzer、Chunker、Embedding Space、模型/Tokenizer Revision、RRF、Reranker 和 Index Schema Version。
- 未通过扫描、治理或评测的内容无法进入 ActivationRequested。

## 7. Day 3：阶段 1A 闭环

当日目标是完成知识发布、固定项目公开问答、换版、回滚、撤回和删除传播。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 Search、Project Message、Validated SSE、Citation、Activation、Rollback、Revocation 和 Tombstone 合同 |
| F | 实现项目公开知识页、Search/Chat、Citation、Evidence-only、拒答、降级、审批、发布、换版、回滚和撤回界面 |
| J | 实现 PUBLIC 短期 Session、Execution Context、Release 状态机、双人审批、Activation、Rollback、Emergency Revoke、SSE 代理和审计 |
| A | 完成 Context/Revocation Guard、ProjectQueryPlan、BM25/Vector 独立召回、RRF、Reranker、Evidence Hub、Prompt、Generator、Grounding、Citation 和 Validated SSE |
| B | 完成发布评测、ActivationRequested 消费、Published Alias 原子切换、Tombstone、投影清理和索引重建 |
| Q | 执行阶段 1A E2E、检索/回答质量、未验证输出、降级、发布并发、回滚、撤回时延、删除传播和 Source 隔离测试 |

Day 3 退出门禁：

- “导入 -> 治理 -> 审批 -> 增量发布 -> 问答引用 -> 回滚/撤回 -> 删除传播”完整通过。
- BM25/Vector Filter 在各自 Top-K 前应用，Domain RRF 与 Reranker 行为符合合同。
- 未验证文本进入 message_delta 为 0，内部 Source Locator 出现在公开响应为 0。
- 新 Revision 在下一消息边界换版，超过两小时租约继续引用旧 Release 为 0。
- 紧急撤回 P95 不超过 60 秒；Worker 积压时继续服务旧 Release。
- P1-05 的 1A 质量、安全和性能证据归档。

## 8. Day 4：阶段 1B 闭环

当日目标是完成统一身份、Session、Portal、共享 UI、SDK 和外部 Embed。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 OIDC/Session、ProjectGrant、Bootstrap Token、Session Token、Thread、History、Favorite、Feedback 和 Embed 错误合同 |
| F | 实现企业 Portal、Guest/Login、Conversation、History、Favorite、Feedback、Vue Web Component、TypeScript Client、Token 内存保存和 Origin 校验 |
| J | 实现 OIDC Code + PKCE、第一方 Cookie、ProjectGrant/ABAC、三类 Access Segment、对象授权、Bootstrap JTI、防重放、Session/Thread 和撤权 |
| A | 重新应用 Subject/Client/Authz Context；实现 Project Memory Key、Successor Session、旧 Evidence 隔离和稳定错误映射 |
| B | 将 Access Segment、Audience Policy、有效期和 Citation URL 投影到 Chunk；完成权限收窄 Tombstone 和 ACL 评测 |
| Q | 执行 Token 类型混用、IDOR、CSRF、OIDC Mix-up、Session Fixation、跨 Origin、重复 Bootstrap、撤权、双标签页和 SSE 重连测试 |

Day 4 退出门禁：

- Portal、项目页和 Web Component 核心协议与交互一致，Citation、范围、项目切换和错误组件复用率为 100%。
- 匿名访问受限知识、Token 伪造越权、跨 User/Session/Client/Deployment IDOR 和 Embed 跨项目越权均为 0。
- Bootstrap Token 跨 Origin 或重复使用成功为 0。
- Grant/Client 撤销传播达到 P95 不超过 30 秒、P99 不超过 60 秒。
- 双标签页、乱序重试和并发切换导致 Thread 串写为 0；Memory 不作为无 Citation 事实。
- P1-08 的 1B 产品、身份和安全证据归档。

## 9. Day 5：阶段 1C 闭环

当日目标是完成授权项目路由、Project Thread 隔离和跨项目 Evidence 聚合。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 Authorized Candidate Set、GlobalRoutePlan、ProjectQueryPlan、EvidencePacket、GlobalResultReference 和 partial_coverage 合同 |
| F | 实现项目候选、路由状态、澄清、跨项目确认、显式切换、逐 Claim 来源和部分覆盖展示 |
| J | 实现 Global Deployment/Session、授权候选集、Project Thread、fan-out、GlobalResultReference、读取时重新授权和 Claim 遮蔽 |
| A | 实现规则/轻量/强模型三层 Router、Schema 复核、独立 Project Context、并发 EvidencePacket、Global Aggregator 和一次最终生成 |
| B | 建设并执行单项目归属、多项目拆分、歧义、超 fan-out、部分失败、跨项目 ACL 和 Memory 隔离评测集 |
| Q | 执行 Router 准确率、Planner 触发、跨项目 Citation、成本、并发、分支超时、Grant 失效和信息泄露测试 |

Day 5 退出门禁：

- 固定 Project 请求调用 Global Router 为 0，固定项目简单问题调用强 Planner 为 0。
- 单项目归属路由准确率不低于 95%，多项目拆分正确率不低于 90%。
- 项目切换显式提示率 100%，Project Memory 交叉污染为 0。
- 跨项目回答每个用户问题只调用一次 Generator。
- 跨项目部分失败未标记 partial_coverage 为 0。
- 每个 Claim 均保留实际 Project、Version、Release、Citation 和知识时间。

## 10. Day 6：跨层加固与预验收

当日不再增加产品功能，专门关闭跨层缺陷和生产门禁。

| 工作流 | 当日任务 |
| --- | --- |
| C | 冻结 v1 合同；执行向后兼容、未知字段、重复/乱序事件、Deadline 和统一错误矩阵 |
| F | 完成长内容、移动视口、键盘、可访问性、断连恢复、权限收窄、Session 换版和全入口回归 |
| J | 完成事务回滚、Outbox 原子性、并发审批、Token 撤销、Thread 乐观锁、审计完整性和优雅终止测试 |
| A | 完成 Provider 超时/限流/无效输出、BM25-only、RRF fallback、Evidence-only、拒答、模型回退和 Prompt Injection 测试 |
| B | 完成 Kafka 重放、Celery 重试/崩溃/DLQ、全量与增量隔离、Alias 失败、Tombstone 和 Elasticsearch 重建测试 |
| Q | 执行性能、容量、成本、安全、故障注入、备份恢复、Trace/Metric/Log 关联和 Runbook 演练 |

Day 6 退出门禁：

- 所有零容忍安全不变量通过，无 Blocker/Critical 缺陷。
- Search、首个已验证片段、Grounding、发布、撤权和撤回时延达到门禁。
- 每个回答的 Project、Release、Evidence、Model Version、Token 和成本记录完整率为 100%。
- Router、OAuth、Retrieval、Generation、Grounding、Citation、Release 和 Revocation 在同一 Trace 中可关联。
- PostgreSQL 恢复、Redis 丢失、Kafka 重放、模型故障和 Elasticsearch 重建演练通过。
- Day 7 只允许修复、复测、归档和发布准备，不再接受新增功能。

## 11. Day 7：全量验收与 Release Candidate

当日目标是用干净环境重跑全部证据并形成唯一 Release Candidate。

| 时间点 | 动作 | 产物 |
| --- | --- | --- |
| 上午 | 从干净 Checkout 构建四个 Deployment，重建本地/集成环境，执行单元、合同、组件和跨服务测试 | 可复现构建记录与完整测试报告 |
| 中午 | 执行管理全链路、Portal、项目页、Web Component、身份、Embed、Project RAG 和 Global RAG E2E | 第一阶段端到端报告 |
| 下午 | 执行密封质量评测、安全矩阵、性能容量、故障注入、恢复和成本评审 | 50 条门禁证据包 |
| 晚间 | 修复后只重建一次候选，复跑受影响矩阵并冻结版本 | Release Candidate、Manifest、变更记录和 Runbook |

Day 7 最终判定：

- 50 条门禁全部有当前 Revision 的证据。
- Blocker、Critical 和安全不变量失败数均为 0。
- 所有外部依赖使用已批准产品、版本、Region、配置和模型 Revision，不含未登记开发替代品。
- Release Candidate 可部署、可回滚、可重建且审计链完整。
- 任一硬门禁失败时状态保持 INCOMPLETE；可以记录已经完成的层次，但不得改写为“基本完成”或“待上线即完成”。

## 12. 每日集成节奏

| 节点 | 必做动作 |
| --- | --- |
| 当日开始 | Owner 同步上一日门禁、当日合同版本、关键路径和两小时内需要决策的阻断 |
| 首次合同窗口 | C 工作流发布当日 Schema/Fixture；消费者先跑合同测试再继续实现 |
| 中段集成 | 六条工作流合并第一批可验证变更，执行 Focused Test 和跨层冒烟 |
| 当日冻结 | 停止新增范围，只修复集成问题并运行当日退出门禁 |
| 当日结束 | 只有绿色提交进入 main；归档测试、评测、性能和安全证据，失败门禁转为次日最高优先级 |

合同在 Day 4 后进入 v1 冻结期。必须变更时使用兼容 Schema Version 和迁移测试，禁止前端、Java 与 Python 私下约定未登记字段。

## 13. 分支、提交与验证入口

所有工作使用仓库允许的短生命周期分支并当天合入，不建立持续七天的巨型功能分支：

| 交付域 | 分支示例 | 最晚合入 |
| --- | --- | --- |
| 合同与工具 | feat/p1-contracts、chore/p1-verification | Day 1 起每日小批合入 |
| 知识治理 | feat/p1-knowledge-governance | Day 2 |
| Project RAG / Release | feat/p1-project-rag、feat/p1-release-control | Day 3 |
| Identity / UI / Embed | feat/p1-identity-session、feat/p1-assistant-ui | Day 4 |
| Global Router | feat/p1-global-routing | Day 5 |
| 验收修复 | test/p1-release-gates、fix/p1-issue | Day 6~7 |

Day 1 必须建立统一入口：

~~~sh
./tools/verify-repository.sh
./tools/verify-all.sh
./tools/test-contracts.sh
./tools/test-e2e-phase1.sh
./tools/evaluate-phase1.sh
./tools/test-security-phase1.sh
./tools/test-performance-phase1.sh
~~~

除 verify-repository.sh 外，其余脚本是 Day 1 必须新增的工程产物。脚本负责调用各语言实际构建和测试工具，CI 与本地使用同一入口；真实云或模型测试必须显式配置，默认验证不得修改外部状态。

## 14. Day 7 交付清单

| 层次 | 必须交付 |
| --- | --- |
| 前端 | Portal、项目页、治理控制台、Assistant UI、Vue Web Component、TypeScript Client、组件与 E2E 测试 |
| Java 后端 | 模块化 platform-api、数据库迁移、身份/授权、Session/Thread、Knowledge/Release、Outbox、审计和测试 |
| 在线 AI | FastAPI Runtime、受约束 RAG Kernel、Model Adapter、Project/Global 路由、Evidence/Citation/Grounding 和质量测试 |
| 批处理 | Kafka Dispatcher、Celery Worker、解析/OCR、Chunk、Embedding、索引、评测、激活、撤回和恢复测试 |
| 数据与部署 | PostgreSQL、OSS、Kafka、双 Redis、Elasticsearch 配置；四个 Deployment、网络、身份、扩缩容和备份定义 |
| 合同与质量 | OpenAPI/SSE/Internal/Event Schema、生成类型、50 条门禁证据、容量成本报告、安全报告和评测 Manifest |
| 运行保障 | 发布、回滚、撤回、撤权、积压、模型故障、恢复和索引重建 Runbook 及演练记录 |

## 15. 阻断与降级规则

- 两小时内无法自行关闭且影响当日关键路径的问题，立即交给对应决策人；不等到日终才暴露。
- 外部 Provider 或云服务瞬时故障可以使用架构已定义的 BM25-only、RRF、备用模型、Evidence-only 或拒答降级验证系统行为，但降级成功不能替代主路径生产门禁。
- 权限、撤回、Release、Evidence 或 Grounding 状态不明时必须 fail closed，不允许用“七天时间紧”改变安全语义。
- 测试不稳定必须定位根因；重复运行碰巧通过不能作为门禁证据。
- Day 6 后发现范围缺失时，优先判定七天目标未达成，不以未经评审的范围删除换取表面按时。
