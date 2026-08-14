# 跨服务测试

本目录负责必须跨越两个及以上组件才能验证的合同、端到端、密封评测、安全、性能和恢复测试。单个组件的单元测试与局部集成测试留在对应应用、服务或包中。

当前只建立跨服务测试所有权；P1-00 已在 Python Worker 局部测试中覆盖 SourceRevision 事件到 Celery JSON Task 的严格转换，并以 Alembic 离线 SQL 检查 Vector Projection 迁移。`infra/local` 已提供真实 Kafka/MySQL/OSS 兼容依赖、双 Redis、Elasticsearch 和两个独立 Migration Job；使用 [`../tools/verify-local-integration.sh`](../tools/verify-local-integration.sh) 验证时，脚本还会检查应用身份 DDL 被拒绝。Java 工具链验证入口仍为服务目录 Wrapper。第一阶段验收范围见 [`执行方案`](../docs/implementation-designs/0001-phase-1-execution-plan.md)，逐日验证入口见 [`七天执行路线`](../docs/implementation-designs/0002-phase-1-seven-day-execution-route.md)。
