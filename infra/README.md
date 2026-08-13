# 基础设施

本目录负责可执行的本地集成环境、ACK/Kubernetes 资源、网络与身份策略，以及 MySQL/Flyway 和 PostgreSQL/pgvector/Alembic 的独立预部署 Migration Job。

当前只建立目录所有权，尚未选择具体本地编排方式，也尚未创建生产资源定义。Schema Migration 本身分别归 `platform-api` 和 `batch-worker` 所有；本目录只负责以独立身份运行它们，不复制迁移文件。P1-00 已提供两套可以离线生成 SQL 的迁移源，但尚未声称本地 MySQL/PostgreSQL/Kafka/Redis/Elasticsearch/OSS 集成环境已经就绪。

部署与数据边界见 [`架构基线`](../docs/tech-plan.md) 和 [`ADR-003`](../docs/adr/0003-mysql-authority-and-pgvector-retrieval-projection.md)。
