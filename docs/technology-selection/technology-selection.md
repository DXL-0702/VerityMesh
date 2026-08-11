# 外部技术选型总索引

| 属性 | 内容 |
| --- | --- |
| 文档版本 | 3.2 |
| 基线日期 | 2026-08-11 |
| 架构基线 | [`../tech-plan.md`](../tech-plan.md) |
| 文档定位 | 外部依赖选型图的统一导航、状态登记与下一决策索引 |

## 1. 边界

本目录只回答“依赖什么外部产品、服务、模型或第三方库，当前选了什么，决策到什么程度”。每份专项文档使用同一张选型表，不保存接口、数据结构、状态机、数据流、迁移步骤、服务目标、部署参数或故障处理。

详细内容按以下位置维护：

| 内容 | 唯一维护位置 |
| --- | --- |
| 系统边界、内部组件、跨域契约、安全不变量、全局服务目标 | [`../tech-plan.md`](../tech-plan.md) |
| 外部依赖选择、状态、阶段、备选和下一决策 | 本目录 |
| 接入、数据结构、流程、迁移和容量实现 | [`../implementation-designs/`](../implementation-designs/) |
| 质量、性能、容量和成本评测证据 | [`../poc-reports/`](../poc-reports/) |
| 部署、升级、恢复和排障步骤 | [`../runbooks/`](../runbooks/) |
| 改变架构边界的重大决策及权衡 | [`../adr/`](../adr/) |

内部服务、协议和算法不是外部依赖。例如 Model Access Service、Provider Adapter、REST/OpenAPI/SSE、BM25 + Vector + RRF、Grounding L0 只在架构中定义；专项选型图仅登记它们所依赖的外部产品。表格中的“备选/回退”可以引用这些内部能力，用于解释未引入外部产品时系统依靠什么运行，但不得把它们登记为已选外部产品。

## 2. 状态定义

| 状态 | 含义 |
| --- | --- |
| `SELECTED` | 当前阶段正式选型已确定 |
| `CONFIRMED_WITH_GATES` | 方向已确认，但固定版本、合同、容量或专项验证尚未关闭 |
| `PRIMARY_POC` | 当前首要验证候选，尚未形成生产结论 |
| `CHALLENGER_POC` | 与首要候选使用同一基准比较的挑战者 |
| `BENCHMARK` | 只用于建立质量、性能或成本对照，默认不进入生产 |
| `UNSELECTED` | 依赖职责已明确，但产品、版本或形态尚未确定 |
| `DEFERRED` | 当前阶段不引入，触发条件成立后重新评审 |
| `REJECTED` | 当前架构明确不采用；重评必须证明原前提已改变 |

状态绑定到精确 Decision ID，不能从上级类别推导。例如 `MySQL = SELECTED` 不代表 `RDS MySQL = SELECTED`，`PostgreSQL + pgvector = SELECTED` 也不代表某个托管产品已经通过真实实例门禁。

## 3. 选型索引

| Decision ID | 技术域 | 外部依赖 | 决策层级 | 当前状态 | 当前选择 | 专项文档 | 下一决策 | 最后更新 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `CLOUD-001` | 云平台 | 主云提供商 | Provider | `SELECTED` | 阿里云，中国大陆单主云 | [云厂商](cloud/cloud-provider-selection.md) | 冻结生产 Region、账号与合同 | 2026-08-05 |
| `CLOUD-002` | 云平台 | 地域与可用区范围 | Topology | `SELECTED` | 单 Region、多可用区 | [云厂商](cloud/cloud-provider-selection.md) | 选择具体 Region 和 AZ | 2026-08-05 |
| `CLOUD-003` | 云平台 | 具体生产 Region | Region | `UNSELECTED` | 阿里云中国大陆 Region 待选 | [云厂商](cloud/cloud-provider-selection.md) | 联合所有托管服务关闭地域门禁 | 2026-08-05 |
| `CLOUD-004` | 云平台 | 多地域灾备 | Strategy | `DEFERRED` | 第一阶段不引入 | [云厂商](cloud/cloud-provider-selection.md) | 触发监管或业务连续性条件后重评 | 2026-08-05 |
| `CLOUD-005` | 云平台 | 多云基础设施 | Strategy | `DEFERRED` | 第一阶段不引入 | [云厂商](cloud/cloud-provider-selection.md) | 出现云级故障域或监管要求后重评 | 2026-08-05 |
| `CLOUD-006` | 云平台 | Kubernetes | Product | `SELECTED` | 阿里云 ACK | [Kubernetes](cloud/kubernetes-platform-selection.md) | 冻结形态、版本、节点与支持周期 | 2026-08-05 |
| `CLOUD-007` | 云平台 | Kubernetes 计算实例 | Product / SKU | `UNSELECTED` | ACK 节点实例族待选 | [Kubernetes](cloud/kubernetes-platform-selection.md) | 冻结实例族、规格和容量 | 2026-08-05 |
| `CLOUD-008` | 云平台 | 事件驱动弹性 | Product | `SELECTED` | KEDA | [Kubernetes](cloud/kubernetes-platform-selection.md) | 冻结版本与兼容矩阵 | 2026-08-05 |
| `CLOUD-009` | 云平台 | 对象存储 | Product | `SELECTED` | 阿里云 OSS | [对象存储](cloud/object-storage-selection.md) | 冻结 Region、Bucket 与产品参数 | 2026-08-05 |
| `CLOUD-010` | 云平台 | 容器镜像仓库 | Product | `UNSELECTED` | 阿里云托管优先 | [云配套服务](cloud/cloud-supporting-services-selection.md) | 形成候选短名单 | 2026-08-05 |
| `CLOUD-011` | 云平台 | 负载均衡与 Ingress | Product | `UNSELECTED` | 托管或 ACK 兼容方案 | [云配套服务](cloud/cloud-supporting-services-selection.md) | 与 Public API Gateway 联合选型 | 2026-08-05 |
| `CLOUD-012` | 云平台 | DNS 服务 | Product | `UNSELECTED` | 阿里云托管优先 | [云配套服务](cloud/cloud-supporting-services-selection.md) | 明确域名清单后选择产品 | 2026-08-05 |
| `CLOUD-013` | 云平台 | 证书管理服务 | Product | `UNSELECTED` | 企业证书体系或托管服务 | [云配套服务](cloud/cloud-supporting-services-selection.md) | 冻结产品归属并选型 | 2026-08-05 |
| `CLOUD-014` | 云平台 | 云备份编排 | Product | `UNSELECTED` | 独立产品或原生能力组合 | [云配套服务](cloud/cloud-supporting-services-selection.md) | 明确覆盖对象后决定产品形态 | 2026-08-05 |
| `DATA-001` | 数据 | 业务关系数据库技术 | Technology | `SELECTED` | MySQL | [关系数据库](data/relational-database-selection.md) | 冻结主版本、字符集、排序规则和 SQL Mode | 2026-08-11 |
| `DATA-002` | 数据 | 托管 MySQL 形态 | Product Class | `CONFIRMED_WITH_GATES` | 阿里云托管 MySQL 兼容产品 | [关系数据库](data/relational-database-selection.md) | RDS 与 PolarDB 同条件 PoC | 2026-08-11 |
| `DATA-003` | 数据 | RDS MySQL 候选 | Product | `UNSELECTED` | 阿里云 RDS MySQL | [关系数据库](data/relational-database-selection.md) | 与 PolarDB 同条件 PoC | 2026-08-11 |
| `DATA-004` | 数据 | PolarDB MySQL 候选 | Product | `UNSELECTED` | 阿里云 PolarDB MySQL | [关系数据库](data/relational-database-selection.md) | 与 RDS 同条件 PoC | 2026-08-11 |
| `DATA-005` | 数据 | Conversation 物理隔离 | Topology | `UNSELECTED` | MySQL 同实例独立 Schema 或独立实例待选 | [关系数据库](data/relational-database-selection.md) | 结合容量、保留和故障域决定 | 2026-08-11 |
| `DATA-006` | 数据 | ACK 自建 MySQL | Product Form | `REJECTED` | 第一阶段不采用 | [关系数据库](data/relational-database-selection.md) | 所有托管候选存在硬缺口时重新立项 | 2026-08-11 |
| `DATA-007` | 数据 | 事件流技术 | Technology | `SELECTED` | Kafka | [消息队列](data/message-queue-selection.md) | 冻结兼容版本 | 2026-08-05 |
| `DATA-008` | 数据 | 托管 Kafka 产品 | Product | `UNSELECTED` | 阿里云托管优先 | [消息队列](data/message-queue-selection.md) | 形成产品短名单并 PoC | 2026-08-05 |
| `DATA-009` | 数据 | ACK 自建 Kafka | Product Form | `REJECTED` | 第一阶段不采用 | [消息队列](data/message-queue-selection.md) | 托管产品存在硬缺口时重新立项 | 2026-08-05 |
| `DATA-010` | 数据 | 缓存技术 | Technology | `SELECTED` | Redis 兼容服务 | [缓存](data/cache-selection.md) | 冻结兼容版本和命令范围 | 2026-08-05 |
| `DATA-011` | 数据 | 托管 Redis 产品 | Product | `UNSELECTED` | 阿里云托管优先 | [缓存](data/cache-selection.md) | 形成产品短名单并 PoC | 2026-08-05 |
| `DATA-012` | 数据 | Redis 实例隔离形态 | Topology | `CONFIRMED_WITH_GATES` | `Redis Online` 与 `Redis Celery` 两个逻辑角色，至少逻辑隔离 | [缓存](data/cache-selection.md) | 完成托管产品 PoC，冻结物理实例/分库、ACL、淘汰策略、容量和故障演练 | 2026-08-11 |
| `DATA-013` | 数据 | ACK 自建 Redis | Product Form | `REJECTED` | 第一阶段不采用 | [缓存](data/cache-selection.md) | 托管产品存在硬缺口时重新立项 | 2026-08-05 |
| `DATA-014` | 数据 | 流处理技术 | Technology | `DEFERRED` | Apache Flink | [流处理](data/stream-processing-selection.md) | Kafka Consumer 出现已证明能力缺口后重评 | 2026-08-05 |
| `DATA-015` | 数据 | 托管 Flink 产品 | Product | `DEFERRED` | 阿里云托管优先 | [流处理](data/stream-processing-selection.md) | Flink 触发后比较托管与自建 | 2026-08-05 |
| `DATA-016` | 数据 | ACK 自建 Flink | Product Form | `DEFERRED` | 第一阶段不引入 | [流处理](data/stream-processing-selection.md) | Flink 触发且托管存在缺口后评审 | 2026-08-05 |
| `DATA-017` | 数据 | 向量投影数据库技术 | Technology | `SELECTED` | PostgreSQL + pgvector | [关系数据库](data/relational-database-selection.md) | 冻结 PostgreSQL/pgvector 版本、距离函数、索引和容量边界 | 2026-08-11 |
| `DATA-018` | 数据 | 托管 PostgreSQL/pgvector 形态 | Product Class | `CONFIRMED_WITH_GATES` | 支持 pgvector 的阿里云托管 PostgreSQL 兼容产品 | [关系数据库](data/relational-database-selection.md) | 同条件真实 Vector 场景 PoC | 2026-08-11 |
| `DATA-019` | 数据 | RDS PostgreSQL/pgvector 候选 | Product | `UNSELECTED` | 阿里云 RDS PostgreSQL | [关系数据库](data/relational-database-selection.md) | 核实扩展、索引、HA、扩容和成本 | 2026-08-11 |
| `DATA-020` | 数据 | PolarDB PostgreSQL/pgvector 候选 | Product | `UNSELECTED` | 阿里云 PolarDB PostgreSQL | [关系数据库](data/relational-database-selection.md) | 先核实目标版本 pgvector 与索引能力，再做同条件 PoC | 2026-08-11 |
| `DATA-021` | 数据 | ACK 自建 PostgreSQL/pgvector | Product Form | `REJECTED` | 第一阶段不采用 | [关系数据库](data/relational-database-selection.md) | 所有托管候选存在硬缺口时重新立项 | 2026-08-11 |
| `DATA-022` | 数据 | Java Schema Migration | Library | `SELECTED` | Flyway | [关系数据库](data/relational-database-selection.md) | 锁定版本并关闭空库、N-1、重试和滚动兼容测试 | 2026-08-11 |
| `DATA-023` | 数据 | Python Schema Migration | Library | `SELECTED` | Alembic `1.18.5` | [关系数据库](data/relational-database-selection.md) | 关闭单一 Head、空库、N-1、重试和滚动兼容测试 | 2026-08-11 |
| `RET-001` | 检索 | 首期 BM25 搜索引擎 | Product Class | `CONFIRMED_WITH_GATES` | 阿里云 Elasticsearch 8.17 | [搜索引擎](retrieval/search-engine-selection.md) | 真实企业语料与隔离云实例关闭质量、权限、容量、成本和退出门禁 | 2026-08-11 |
| `RET-002` | 检索 | 阿里云 Elasticsearch 主候选 | Product | `CONFIRMED_WITH_GATES` | 阿里云 Elasticsearch 8.17，仅 BM25 Projection | [搜索引擎](retrieval/search-engine-selection.md) | 完成真实实例 BM25 矩阵及撤回、删除、回滚合同验证 | 2026-08-11 |
| `RET-003` | 检索 | 阿里云 OpenSearch 挑战者 | Product | `CHALLENGER_POC` | 阿里云 OpenSearch，具体文本检索产品形态待定 | [搜索引擎](retrieval/search-engine-selection.md) | 与 Elasticsearch 使用同一 BM25 语料和硬门禁完成真实实例 PoC | 2026-08-11 |
| `RET-004` | 检索 | 开源 OpenSearch 自建 | Product Form | `BENCHMARK` | ACK 自建，仅作基准或条件候选 | [搜索引擎](retrieval/search-engine-selection.md) | 托管方案存在硬缺口时再升级资格 | 2026-08-05 |
| `RET-005` | 检索 | 独立向量数据库 | Product | `DEFERRED` | Milvus | [向量数据库](retrieval/vector-database-selection.md) | PostgreSQL/pgvector 经调优仍不达向量硬门禁时启动 PoC | 2026-08-11 |
| `RET-006` | 检索 | 一体化替代引擎 | Product | `DEFERRED` | Weaviate | [向量数据库](retrieval/vector-database-selection.md) | 证明能整体替代并降低复杂度后重评 | 2026-08-05 |
| `RET-007` | 检索 | 向量双投影 | Topology | `REJECTED` | 不在 PostgreSQL/pgvector 与 Elasticsearch 永久双存 Dense Vector | [向量数据库](retrieval/vector-database-selection.md) | 仅检索架构正式重构且有量化收益时重评 | 2026-08-11 |
| `RET-008` | 检索 | GraphRAG 框架 | Framework | `DEFERRED` | 未选择 | [图检索](retrieval/graph-retrieval-selection.md) | 先证明多跳质量收益 | 2026-08-05 |
| `RET-009` | 检索 | 图数据库 | Product | `DEFERRED` | 未选择 | [图检索](retrieval/graph-retrieval-selection.md) | GraphRAG PoC 通过后形成短名单 | 2026-08-05 |
| `RET-010` | 检索 | 中文 BM25 Analyzer 插件 | Plugin | `PRIMARY_POC` | Elasticsearch IK Analysis；索引 `ik_max_word`、查询 `ik_smart` | [搜索引擎](retrieval/search-engine-selection.md) | 在阿里云 ES 8.17 真实实例验证插件、词典版本化、质量、延迟和升级兼容 | 2026-08-10 |
| `RET-011` | 检索 | 首期 Vector Recall 存储 | Product Class | `SELECTED` | PostgreSQL + pgvector Vector Serving Projection | [向量数据库](retrieval/vector-database-selection.md) | 关闭同过滤合同、HNSW/IVFFlat、容量、延迟、重建和迁移门禁 | 2026-08-11 |
| `MODEL-001` | 模型 | 主模型平台 | Provider | `SELECTED` | 阿里云百炼 | [模型供应商](models/model-provider-selection.md) | 关闭地域、合同、保留和配额条件 | 2026-08-05 |
| `MODEL-002` | 模型 | 跨云备供平台 | Provider | `SELECTED` | 火山方舟 | [模型供应商](models/model-provider-selection.md) | 关闭跨云数据与容量条件 | 2026-08-05 |
| `MODEL-003` | 模型 | 自托管推理运行时 | Product | `UNSELECTED` | ACK 内运行时待选 | [模型供应商](models/model-provider-selection.md) | 为 StructBERT PoC 选择服务化运行时 | 2026-08-05 |
| `MODEL-004` | 模型 | Generator 质量主模型 | Model Version | `CONFIRMED_WITH_GATES` | 百炼 `qwen3.8-max` | [Generator](models/generator-selection.md) | 固定版本、SLA、容量、RAG 质量/延迟/成本 | 2026-08-05 |
| `MODEL-005` | 模型 | Generator 同云稳定回退 | Model Version | `CONFIRMED_WITH_GATES` | 百炼 `qwen3.7-max-2026-06-08` | [Generator](models/generator-selection.md) | 同一真实 RAG 集关闭回退门禁 | 2026-08-05 |
| `MODEL-006` | 模型 | Generator 跨云灾备 | Model Version | `CONFIRMED_WITH_GATES` | 方舟 `doubao-seed-2-1-pro-260628` | [Generator](models/generator-selection.md) | 关闭跨云合同、容量和灾备门禁 | 2026-08-05 |
| `MODEL-007` | 模型 | Grounding Light 云端主候选 | Model Version | `PRIMARY_POC` | 百炼 `qwen3.7-flash-2026-07-15` | [Grounding](models/grounding-selection.md) | 企业 Claim-Evidence 集 PoC | 2026-08-05 |
| `MODEL-008` | 模型 | Grounding Light 自托管挑战者 | Model Version | `CHALLENGER_POC` | StructBERT Chinese NLI Base `v1.0.1` | [Grounding](models/grounding-selection.md) | 领域微调、Shadow、容量与可用性 PoC | 2026-08-05 |
| `MODEL-009` | 模型 | Grounding Light 跨云挑战者 | Model Version | `CHALLENGER_POC` | 方舟 `doubao-seed-2-0-mini-260428` | [Grounding](models/grounding-selection.md) | 核实结构化输出、容量、合同和质量 | 2026-08-05 |
| `MODEL-010` | 模型 | Grounding 云端质量对照 | Model Version | `BENCHMARK` | 百炼 `qwen3.7-plus-2026-05-26` | [Grounding](models/grounding-selection.md) | 建立云端质量上界 | 2026-08-05 |
| `MODEL-011` | 模型 | Grounding 自托管质量对照 | Model Version | `BENCHMARK` | StructBERT Chinese NLI Large `v1.0.1` | [Grounding](models/grounding-selection.md) | 比较 Base/Large 收益与成本 | 2026-08-05 |
| `MODEL-012` | 模型 | Grounding 云端延迟对照 | Model Version | `BENCHMARK` | 百炼 `qwen-turbo-2025-04-28` | [Grounding](models/grounding-selection.md) | 建立延迟与质量损失基线 | 2026-08-05 |
| `MODEL-013` | 模型 | Grounding Strong | Model Binding | `UNSELECTED` | 复用强模型或独立 Judge 待选 | [Grounding](models/grounding-selection.md) | 基于灰区和高风险样本选型 | 2026-08-05 |
| `MODEL-014` | 模型 | Embedding 主候选 | Model Binding | `CONFIRMED_WITH_GATES` | 百炼 `qwen3.7-text-embedding`；既定空间合同；不可变模型 Revision 为生产硬门禁 | [Embedding](models/embedding-selection.md) | 从真实 Provider 固定模型与 Tokenizer Revision，完成联合矩阵、漂移 Canary、迁移和回滚门禁 | 2026-08-10 |
| `MODEL-015` | 模型 | Reranker 主候选 | Model Binding | `CONFIRMED_WITH_GATES` | 百炼 `qwen3-rerank`；RRF Top 50 精排至 Top 10 | [Reranker](models/reranker-selection.md) | 与同云挑战者执行联合矩阵，固定 Revision 并关闭质量、延迟、吞吐和成本门禁 | 2026-08-10 |
| `MODEL-016` | 模型 | Global Router | Model Binding | `UNSELECTED` | 未选择 | [Routing / Planning](models/routing-planning-selection.md) | 建立真实 Global 查询集后选型 | 2026-08-05 |
| `MODEL-017` | 模型 | Project Query Planner | Model Binding | `UNSELECTED` | 未选择 | [Routing / Planning](models/routing-planning-selection.md) | 检索基线稳定后评估增益 | 2026-08-05 |
| `MODEL-018` | 模型 | OCR / 文档视觉模型 | Model Binding | `UNSELECTED` | 未选择 | [文档与安全模型](models/document-security-selection.md) | 与 Parser 使用同一文档集联合评审 | 2026-08-05 |
| `MODEL-019` | 模型 | PII / 受限信息检测模型 | Model Binding | `UNSELECTED` | 未选择 | [文档与安全模型](models/document-security-selection.md) | 与 DLP 产品和规则联合评审 | 2026-08-05 |
| `MODEL-020` | 模型 | 私有模型推理平台 | Product Class | `DEFERRED` | ACK 自托管或独立私有推理服务 | [模型供应商](models/model-provider-selection.md) | 量化触发条件成立后形成短名单 | 2026-08-05 |
| `MODEL-021` | 模型 | LangChain RAG 编排 | Framework | `REJECTED` | 不进入主 RAG；由受约束 Domain Kernel 编排 | [Model Access 与编排](models/model-access-orchestration-selection.md) | 仅整体 RAG 领域架构正式重构时重评 | 2026-08-10 |
| `MODEL-022` | 模型 | LangChain Provider Adapter | Library | `DEFERRED` | 第一阶段不引入；使用原生 SDK 或 REST Adapter | [Model Access 与编排](models/model-access-orchestration-selection.md) | Provider 或协议维护复杂度达到触发条件后专项 PoC | 2026-08-10 |
| `MODEL-023` | 模型 | LangGraph 主 RAG Workflow | Framework | `REJECTED` | 不进入第一阶段主 RAG | [Model Access 与编排](models/model-access-orchestration-selection.md) | 仅主 RAG 演变为长时动态工作流时重评 | 2026-08-10 |
| `MODEL-024` | 模型 | LangGraph 受限 Agent/Tool 子图 | Framework | `DEFERRED` | 第二阶段按 Tool Contract 条件评估 | [Model Access 与编排](models/model-access-orchestration-selection.md) | 冻结工具授权、幂等、补偿和人工确认需求后决定是否 PoC | 2026-08-10 |
| `MODEL-025` | 模型 | MaxKB Runtime / Workflow 复用 | Platform / Framework | `REJECTED` | 只参考思想并独立实现 | [Model Access 与编排](models/model-access-orchestration-selection.md) | 仅许可证和核心领域语义同时根本变化时重评 | 2026-08-10 |
| `MODEL-026` | 模型 | Embedding 同云挑战者 | Model Version | `CHALLENGER_POC` | 百炼 `text-embedding-v4`；采用相同输入合同但保持独立空间；不可变 Revision 为生产资格前提 | [Embedding](models/embedding-selection.md) | 固定独立 Revision，并与主候选执行同条件质量、延迟、成本、漂移和重建窗口评测 | 2026-08-10 |
| `MODEL-027` | 模型 | Reranker 同云挑战者 | Model Version | `CHALLENGER_POC` | 百炼 `gte-rerank-v2` | [Reranker](models/reranker-selection.md) | 与 `qwen3-rerank` 使用同一 RRF 候选完成质量、延迟、稳定性和成本评测 | 2026-08-10 |
| `MODEL-028` | 模型 | Reranker 自托管候选 | Model Version | `DEFERRED` | `BAAI/bge-reranker-v2-m3` | [Reranker](models/reranker-selection.md) | 云端方案出现量化硬缺口后，与自托管推理运行时联合立项 | 2026-08-10 |
| `GATE-001` | 网关 | Public API Gateway | Product | `UNSELECTED` | 托管网关、ACK Gateway/Ingress 或组合待选 | [Public API Gateway](gateway/api-gateway-selection.md) | 完成 SSE、安全、容量、成本和退出 PoC | 2026-08-05 |
| `GATE-002` | 网关 | AI Gateway 传输数据面 | Product | `DEFERRED` | 暂不引入；触发后首个 PoC 候选为 Higress | [AI Gateway](gateway/ai-gateway-selection.md) | Provider/连接/密钥池复杂度达到门槛后 PoC | 2026-08-05 |
| `GATE-003` | 网关 | Higress 领域编排扩展 | Product Capability | `REJECTED` | 不采用 RAG、Memory、Prompt、Intent、Agent、MCP 或语义缓存扩展 | [AI Gateway](gateway/ai-gateway-selection.md) | 仅整体领域架构正式变更时重评 | 2026-08-05 |
| `IDSEC-001` | 身份安全 | IdP / CIAM | Product | `UNSELECTED` | 现有账号体系、托管 CIAM 或独立 IdP | [身份提供方](identity-security/identity-provider-selection.md) | 先确认现有体系复用条件 | 2026-08-05 |
| `IDSEC-002` | 身份安全 | Policy Engine | Product | `UNSELECTED` | 自研规则或外部产品 | [策略引擎](identity-security/authorization-policy-engine-selection.md) | 冻结策略规模后形成短名单 | 2026-08-05 |
| `IDSEC-003` | 身份安全 | KMS | Product | `UNSELECTED` | 托管优先 | [密钥与凭证](identity-security/key-secret-management-selection.md) | 与 Region 和加密层级联合选型 | 2026-08-05 |
| `IDSEC-004` | 身份安全 | Secret 管理 | Product | `UNSELECTED` | 托管或 ACK 兼容方案 | [密钥与凭证](identity-security/key-secret-management-selection.md) | 与 Workload Identity 联合选型 | 2026-08-05 |
| `IDSEC-005` | 身份安全 | WAF / DDoS | Product | `UNSELECTED` | 托管能力或第三方服务 | [边缘安全](identity-security/edge-security-selection.md) | 与 Public API Gateway 联合选型 | 2026-08-05 |
| `IDSEC-006` | 身份安全 | DLP / PII 产品 | Product | `UNSELECTED` | 规则、产品与模型组合 | [数据安全](identity-security/data-security-selection.md) | 用代表性语料形成短名单 | 2026-08-05 |
| `IDSEC-007` | 身份安全 | 内容安全产品 | Product | `UNSELECTED` | 输入、发布与模型输出 | [数据安全](identity-security/data-security-selection.md) | 冻结内容分类后选型 | 2026-08-05 |
| `IDSEC-008` | 身份安全 | 审计防篡改归档 | Product | `UNSELECTED` | MySQL 审计的长期受控归档 | [审计归档](identity-security/audit-archive-selection.md) | 冻结范围、保留和不可篡改要求 | 2026-08-11 |
| `IDSEC-009` | 身份安全 | DPoP 能力 | Standard / Product Capability | `DEFERRED` | 高风险外部嵌入 | [边缘安全](identity-security/edge-security-selection.md) | 出现高风险 Deployment 后专项评审 | 2026-08-05 |
| `GOV-001` | 内容治理 | 文档 Parser | Product or Library | `UNSELECTED` | Governance 解析 | [文档解析](governance/document-parser-selection.md) | 冻结格式和样本集后 PoC | 2026-08-05 |
| `GOV-002` | 内容治理 | 表格与版面提取 | Product or Library | `UNSELECTED` | Governance 解析 | [文档解析](governance/document-parser-selection.md) | 与 Parser 联合 PoC | 2026-08-05 |
| `GOV-003` | 内容治理 | 文件类型识别与归档解包 | Product or Library | `UNSELECTED` | Source 接收 | [文档解析](governance/document-parser-selection.md) | 与 Malware Scanner 联合选型 | 2026-08-05 |
| `GOV-004` | 内容治理 | Malware Scanner | Product or Library | `UNSELECTED` | Source 隔离区 | [扫描工具](governance/malware-secret-scanner-selection.md) | 冻结文件类型和容量后 PoC | 2026-08-05 |
| `GOV-005` | 内容治理 | Secret Scanner | Product or Library | `UNSELECTED` | Source 与 Governance | [扫描工具](governance/malware-secret-scanner-selection.md) | 建立安全样本集后 PoC | 2026-08-05 |
| `GOV-006` | 内容治理 | 外部去重服务 | Product or Library | `DEFERRED` | 第一阶段不引入；内部 SHA-256 + MinHash/LSH 审核信号 | [去重与切分](governance/deduplication-chunking-selection.md) | 内部合同出现吞吐、内存或维护硬缺口后形成短名单 | 2026-08-10 |
| `GOV-007` | 内容治理 | 外部通用 Chunker 库/服务 | Product or Library | `REJECTED` | 不引入；使用自有确定性结构感知 Chunker | [去重与切分](governance/deduplication-chunking-selection.md) | 仅外部库能保持全部发布与 Citation 不变量且自有实现存在硬缺口时重评 | 2026-08-10 |
| `GOV-008` | 内容治理 | 无边界 Connector 平台 | Product | `REJECTED` | 第一阶段不建设 | [数据源 Connector](governance/source-connector-selection.md) | 出现明确规模收益后重新立项 | 2026-08-05 |
| `GOV-009` | 内容治理 | 具体数据源 Connector | Product or Adapter | `UNSELECTED` | Source 接入层 | [数据源 Connector](governance/source-connector-selection.md) | 按数据源独立登记和 PoC | 2026-08-05 |
| `GOV-010` | 内容治理 | 业务 API Connector / Tool Executor | Product or Adapter | `DEFERRED` | Assistant Tool Runtime | [数据源 Connector](governance/source-connector-selection.md) | 第二阶段专项评审 | 2026-08-05 |
| `OBS-001` | 可观测性 | Telemetry SDK / 协议 | Standard + SDK | `UNSELECTED` | 全平台 | [Telemetry](observability/telemetry-selection.md) | 冻结语言栈、信号量和采样要求 | 2026-08-05 |
| `OBS-002` | 可观测性 | 日志平台 | Product | `UNSELECTED` | 平台运行日志 | [观测后端](observability/observability-backend-selection.md) | 估算摄入量、保留和查询后形成短名单 | 2026-08-05 |
| `OBS-003` | 可观测性 | Metrics / 告警平台 | Product | `UNSELECTED` | 全平台指标与告警 | [观测后端](observability/observability-backend-selection.md) | 冻结指标规模后形成短名单 | 2026-08-05 |
| `OBS-004` | 可观测性 | Trace 后端 | Product | `UNSELECTED` | 在线与异步链路追踪 | [观测后端](observability/observability-backend-selection.md) | 冻结采样与保留要求 | 2026-08-05 |
| `OBS-005` | 可观测性 | Dashboard | Product | `UNSELECTED` | 运维与项目视图 | [事件响应集成](observability/incident-response-integration-selection.md) | 与观测后端联合选型 | 2026-08-05 |
| `OBS-006` | 可观测性 | On-call / 事件响应集成 | Product | `UNSELECTED` | 告警处置闭环 | [事件响应集成](observability/incident-response-integration-selection.md) | 先盘点企业现有系统 | 2026-08-05 |

## 4. 目录导航

| 技术域 | 专项文档 |
| --- | --- |
| 云平台 | [云厂商](cloud/cloud-provider-selection.md)、[Kubernetes](cloud/kubernetes-platform-selection.md)、[对象存储](cloud/object-storage-selection.md)、[云配套服务](cloud/cloud-supporting-services-selection.md) |
| 数据 | [关系数据库](data/relational-database-selection.md)、[消息队列](data/message-queue-selection.md)、[缓存](data/cache-selection.md)、[流处理](data/stream-processing-selection.md) |
| 检索 | [搜索引擎](retrieval/search-engine-selection.md)、[向量数据库](retrieval/vector-database-selection.md)、[图检索](retrieval/graph-retrieval-selection.md) |
| 模型 | [供应商](models/model-provider-selection.md)、[Model Access 与编排](models/model-access-orchestration-selection.md)、[Generator](models/generator-selection.md)、[Grounding](models/grounding-selection.md)、[Embedding](models/embedding-selection.md)、[Reranker](models/reranker-selection.md)、[Routing/Planning](models/routing-planning-selection.md)、[文档与安全模型](models/document-security-selection.md) |
| 网关 | [Public API Gateway](gateway/api-gateway-selection.md)、[AI Gateway](gateway/ai-gateway-selection.md) |
| 身份安全 | [身份提供方](identity-security/identity-provider-selection.md)、[策略引擎](identity-security/authorization-policy-engine-selection.md)、[密钥与凭证](identity-security/key-secret-management-selection.md)、[边缘安全](identity-security/edge-security-selection.md)、[数据安全](identity-security/data-security-selection.md)、[审计归档](identity-security/audit-archive-selection.md) |
| 内容治理 | [文档解析](governance/document-parser-selection.md)、[扫描工具](governance/malware-secret-scanner-selection.md)、[去重与切分](governance/deduplication-chunking-selection.md)、[数据源 Connector](governance/source-connector-selection.md) |
| 可观测性 | [Telemetry](observability/telemetry-selection.md)、[观测后端](observability/observability-backend-selection.md)、[事件响应集成](observability/incident-response-integration-selection.md) |

## 5. 更新规则

1. 每个可独立决策的外部依赖必须有唯一 Decision ID 和唯一专项选型图事实源。
2. 新候选、状态变化、版本冻结或淘汰时，先更新专项图，再同步本索引的一行。
3. PoC 数据只链接 [`../poc-reports/`](../poc-reports/)，不复制进选型图；实施细节只链接 [`../implementation-designs/`](../implementation-designs/)。
4. 改变系统边界、安全不变量或跨域职责时，必须先更新 `tech-plan.md`，必要时新增 ADR。
5. 每次修改必须更新“下一决策”和“最后更新”，不得用 `SELECTED` 掩盖尚未确定的版本、Region、SKU 或合同门禁。
