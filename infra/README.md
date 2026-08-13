# 基础设施

本目录负责可执行的本地集成环境、ACK/Kubernetes 资源、网络与身份策略，以及 MySQL/Flyway 和 PostgreSQL/pgvector/Alembic 的独立预部署 Migration Job。

`local/` 已提供仅用于开发与集成验证的 Docker Compose 底座，覆盖 MySQL、PostgreSQL/pgvector、Kafka、双 Redis、Elasticsearch 和 OSS 兼容对象存储；对象存储由独立初始化 Job 创建 bucket 和最小对象身份，两个 Migration Job 直接挂载或构建服务目录中的唯一迁移源。它不代表生产部署编排，也不把本地替代品写成生产选型。使用方式见 [`local/README.md`](local/README.md)。

Schema Migration 本身分别归 `platform-api` 和 `batch-worker` 所有；本目录只负责以独立身份运行它们，不复制迁移文件。应用运行身份没有 DDL 权限。

部署与数据边界见 [`架构基线`](../docs/tech-plan.md) 和 [`ADR-003`](../docs/adr/0003-mysql-authority-and-pgvector-retrieval-projection.md)。
