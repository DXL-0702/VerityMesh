# 跨语言合同

本目录是 Java、Python 和 TypeScript 之间的共享协议边界。当前只建立目录所有权，第一版 Schema 和生成配置尚未创建。

第一阶段需要在这里版本化维护：

- Public OpenAPI。
- SSE Event Schema。
- Java 到 Python 的 Immutable Project Execution Context。
- Kafka Event Schema。
- Celery JSON Task Schema。
- 统一错误、幂等和 Trace 字段。
- Retrieval/Evidence 与 Evaluation Report Schema。

合同必须保持语言独立，不共享 ORM、进程内 DTO、框架 Message 或 Provider SDK 类型。合同范围与生产者/消费者所有权见 [`第一阶段执行方案`](../docs/implementation-designs/0001-phase-1-execution-plan.md)。
