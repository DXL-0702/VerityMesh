# ADR-003：MySQL 业务权威与 PostgreSQL/pgvector 向量投影

| 属性 | 内容 |
| --- | --- |
| 状态 | `ACCEPTED` |
| 决策日期 | 2026-08-11 |
| 架构基线 | [`../tech-plan.md`](../tech-plan.md) 5.4 |
| 取代范围 | [`0002-java-platform-and-python-ai-runtime.md`](0002-java-platform-and-python-ai-runtime.md) 中的数据库与检索存储条款 |
| 相关 ADR | [`0001-constrained-rag-kernel-and-model-access.md`](0001-constrained-rag-kernel-and-model-access.md)、[`0002-java-platform-and-python-ai-runtime.md`](0002-java-platform-and-python-ai-runtime.md) |

## 1. 背景

ADR-002 已冻结 Java 平台与 Python AI Runtime 的领域边界，但当时把业务权威状态放在 PostgreSQL，并让 Elasticsearch 同时承载 BM25 与 Vector。现进一步冻结数据所有权：Java 业务数据进入 MySQL，RAG Embedding 与 Vector Recall 进入 PostgreSQL/pgvector。

若仅替换数据库名称而不重新定义内容资产、检索投影、发布提交点和迁移所有权，会形成三类问题：MySQL 与检索库争夺 Release 真相、向量在 PostgreSQL 与 Elasticsearch 永久双写、不同服务使用同一迁移权限修改彼此 Schema。

当前仓库尚未进入业务数据落库阶段，因此本决策建立首个生产 Schema 基线，不包含虚构的 PostgreSQL 到 MySQL 存量搬迁任务。

## 2. 决策

1. Java `platform-api` 唯一拥有 MySQL 业务权威库。Project、Identity 映射、Grant、Access Policy、SourceRevision 元数据、治理状态、Task、Session/Thread、Conversation、Release、Binding、Deployment Revision、Outbox 和业务审计只能由 Java 通过 MySQL 事务修改。
2. OSS 是原始文件、治理内容、解析/OCR 产物、不可变 Knowledge Revision、Chunk Manifest、评测资产和发布资产的内容事实源。大对象和可重建正文不进入 MySQL 关系表。
3. Python `batch-worker` 拥有 PostgreSQL/pgvector Vector Serving Projection。投影保存 `chunk_id`、最小正文、Citation 描述、Project/Release/Locale/Access 过滤字段、Embedding Space/Model Revision、内容 Hash 和向量；它不保存可独立修改的业务真相。
4. Elasticsearch 只保存 BM25 Serving Projection，包括正文、标题、章节、高亮字段和同一组检索过滤字段；第一阶段不再向 Elasticsearch 写入 Dense Vector。
5. PostgreSQL/pgvector 与 Elasticsearch 中的 Project、Release 和 Access 字段都是从 MySQL/OSS 投影出的不可变过滤副本。它们不能反向修改授权、审批、任务或 Release 状态，也不与 MySQL 执行跨库 Join。
6. 两套检索投影按 `knowledge_release_id` 不可变构建。Python 先证明 BM25 与 Vector Projection 均完整且通过评测，Java 再在 MySQL 单事务中切换 Active Release；MySQL 的 Active Release 指针是唯一发布提交点，搜索 Alias 只可作为运维优化，不能成为正确性事实源。
7. 在线请求由 Java 从 MySQL 解析固定 Release 和授权上下文，再将不可由客户端构造的 Execution Context 传给 Python。Python 使用完全相同的过滤条件分别查询 Elasticsearch BM25 与 PostgreSQL/pgvector Vector Top-K，并在 Domain Kernel 内按 `chunk_id` 执行 RRF。
8. Redis Online、Redis Celery 和 Kafka 的既有职责不变：Redis 只保存可丢失临时状态，Kafka 保存可重放领域事件，业务最终状态仍以 MySQL 为准。

## 3. Schema 迁移所有权

| 目标 | 工具与执行者 | 约束 |
| --- | --- | --- |
| MySQL 业务 Schema | Java `platform-api` 仓库内的 Flyway Migration | 只管理 Java 权威表、索引、约束、Outbox 和审计；Python 运行身份没有 DDL 或业务写权限 |
| PostgreSQL/pgvector Schema | Python `uv` Workspace 内的 Alembic Migration | 只管理 `vector` 扩展、Vector Projection、过滤索引和向量索引；Java 运行身份没有访问权限 |
| Elasticsearch Schema | 版本化 Index Template、影子索引与重建切换 | 不对在线索引执行破坏性原地字段迁移；新 Schema 使用新 Release Projection 验证后启用 |
| OSS Artifact Schema | Manifest Schema Version | 资产不可变；新格式生成新 Revision，消费者按明确兼容窗口升级 |
| Kafka Event Schema | 版本化事件合同 | 保持生产者/消费者兼容；未知版本进入失败事件或 DLQ，不静默解释 |

MySQL 与 PostgreSQL 迁移使用独立的预部署 Migration Job，不由每个应用副本在启动时竞争执行。生产运行身份默认只有 DML 或只读权限，没有 DDL 权限。

迁移采用 expand/contract：先增加兼容结构，再执行幂等、可续跑的数据回填和读写切换，确认旧应用 Revision 已排空后才删除旧结构。生产回退优先回滚应用并使用前向补偿 Migration，不依赖未经验证的破坏性 Down Migration。

每个发布候选至少验证空库初始化、上一已发布 Schema 升级、中断后重试、旧/新应用滚动兼容、备份恢复后升级、Flyway Validate、Alembic 单一 Head 和迁移版本审计。

## 4. 所有权与发布流程

```text
OSS Source / Chunk Manifest
  -> Python batch-worker
  -> Elasticsearch BM25 Projection
  -> PostgreSQL/pgvector Vector Projection
  -> Kafka CandidateReady / ActivationPrepared
  -> Java platform-api
  -> MySQL 原子提交 Active Release
  -> Immutable Execution Context 固定 knowledge_release_id
  -> Python 并行 BM25 / Vector Recall + RRF
```

紧急撤回先在 MySQL 提交权威撤回状态并同步更新 Redis Online Revocation List，再通过 Kafka Tombstone 清理 PostgreSQL/pgvector 与 Elasticsearch。任何投影清理延迟都不能重新放行已撤回 Evidence。

## 5. 备选与取舍

| 方案 | 结论 | 主要取舍 |
| --- | --- | --- |
| PostgreSQL 同时保存业务权威与向量 | 不采用 | 组件更少，但违反已冻结的 Java/MySQL 业务数据边界，并扩大 Python 对业务库的接触面 |
| Elasticsearch 同时保存 BM25 与 Vector | 不采用 | 单产品查询简单，但不符合向量进入 PostgreSQL 的边界 |
| PostgreSQL 保存向量权威副本，Elasticsearch 再保存向量投影 | 不采用 | 保留旧检索栈，但形成无收益的向量双写、漂移、撤回和重建复杂度 |
| MySQL 权威 + OSS 内容事实源 + pgvector Vector + Elasticsearch BM25 | 采用 | 多一个检索存储与联合发布门禁，但所有权清楚，两路召回可独立评测、降级和替换 |

Chunk 正文和少量过滤字段会在 PostgreSQL/pgvector 与 Elasticsearch 中重复。这是为了让两路召回可独立服务和降级的受控投影冗余，不等于复制业务权威状态。

## 6. 替代条件

- PostgreSQL/pgvector 经索引、分区、容量和托管产品调优后仍无法满足 Vector Recall 的质量、延迟、吞吐、重建窗口或成本门禁，届时只替换 Vector Adapter，不改变 MySQL、OSS 或 RAG Kernel 所有权。
- Elasticsearch BM25 无法满足中文检索、过滤、高亮、隔离或成本门禁，届时只替换 BM25 Adapter。
- 未来确有存量系统接入，需要 PostgreSQL 到 MySQL 或其他数据库的数据搬迁时，必须单独设计源目标对账、双读/双写窗口、校验、回退和停写策略，不能把 Schema Migration 当作数据搬迁方案。
