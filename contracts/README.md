# 跨语言合同

本目录是 Java、Python 和 TypeScript 之间的共享协议边界。合同格式固定为 OpenAPI 3.1、JSON Schema 2020-12 和 AsyncAPI 3。当前已经冻结第一份内部合同 [`Project Execution Context v1`](internal/v1/project-execution-context.schema.json) 及其[有效示例](internal/v1/examples/project-execution-context.valid.json)；其他合同和代码生成配置仍待后续批次建立。

第一阶段需要在这里版本化维护：

- Public OpenAPI。
- SSE Event Schema。
- Java 到 Python 的 Immutable Project Execution Context。
- Kafka Event Schema。
- Celery JSON Task Schema。
- 统一错误、幂等和 Trace 字段。
- Retrieval/Evidence 与 Evaluation Report Schema。

合同必须保持语言独立，不共享 ORM、进程内 DTO、框架 Message 或 Provider SDK 类型。合同范围与生产者/消费者所有权见 [`第一阶段执行方案`](../docs/implementation-designs/0001-phase-1-execution-plan.md)。

TypeScript、Python 和 Java 必须消费同一版本化 Schema。当前 Python 消费模型通过合同漂移测试与 Context Schema 保持一致；Java 与 TypeScript 代码生成器和统一生成命令仍需使用该正式 Schema 完成兼容性验证后固定。合同格式和当前工程技术栈见 [`技术栈与外部选型总览`](../docs/technology-selection/technology-selection.md)。
