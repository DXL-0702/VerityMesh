# batch-worker

| 属性 | 内容 |
| --- | --- |
| 类型 | Python/Celery 离线 Worker Deployment |
| 包管理 | `uv` |
| 当前状态 | 仅建立目录边界，Python Worker 尚未初始化 |

本目录负责 Kafka 事件分发、Celery JSON Task、扫描、解析/OCR、去重、Chunk、Embedding、OSS Artifact、BM25/Vector Projection、发布评测、激活准备和删除传播。

Alembic Migration 归本服务所有，但必须由独立预部署 Migration Job 执行。本服务不决定审批或 Active Release 真相，也不接受 Java 直接写入 Celery 私有消息。具体边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。
