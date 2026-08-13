# batch-worker

| 属性 | 内容 |
| --- | --- |
| 类型 | Python/Celery 离线 Worker Deployment |
| 包管理 | `uv` |
| 当前状态 | P1-00 Kafka 事件到 Celery JSON Task 的 Dispatcher 与 Alembic Vector Projection 基线已实现；真实 Broker/数据库/解析链路仍待接入 |

本目录负责 Kafka 事件分发、Celery JSON Task、扫描、解析/OCR、去重、Chunk、Embedding、OSS Artifact、BM25/Vector Projection、发布评测、激活准备和删除传播。

Alembic Migration 归本服务所有，但必须由独立预部署 Migration Job 执行。本服务不决定审批或 Active Release 真相，也不接受 Java 直接写入 Celery 私有消息。当前 Dispatcher 只接受严格的 `SourceRevisionSubmitted v1`，输出 JSON-only `source_revision.process v1`，拒绝未知字段和非法幂等/内容元数据。具体边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。

当前尚未接入真实 Celery Worker、Kafka Consumer、解析/OCR、Embedding 或投影写入；已实现的 Dispatcher、Alembic Revision 和 Vector Schema 只提供严格的跨层基线。版本总览见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)，本地可执行版本以成员 `pyproject.toml` 和根 `uv.lock` 为准。
