# 跨语言合同

本目录是 Java、Python 和 TypeScript 之间的共享协议边界。合同格式固定为 OpenAPI 3.1、JSON Schema 2020-12 和 AsyncAPI 3。当前已经冻结内部 `Project Execution Context v1`、Public API 的最小 Source Revision 接入面、SSE 基础事件、`SourceRevisionSubmitted v1` Kafka 事件和 `source_revision.process v1` Celery JSON 任务；每份合同都配有有效示例或消费者测试。领域问答、发布和身份合同继续按后续批次扩展，不能把当前最小接入面误认为第一阶段全部 API。

第一阶段需要在这里版本化维护：

- Public OpenAPI（当前为 Source Revision 上传/完成和任务状态最小面）。
- SSE Event Schema（当前为统一事件 envelope）。
- Java 到 Python 的 Immutable Project Execution Context。
- Kafka Event Schema。
- Celery JSON Task Schema。
- 统一错误、幂等和 Trace 字段。
- Retrieval/Evidence 与 Evaluation Report Schema。

合同必须保持语言独立，不共享 ORM、进程内 DTO、框架 Message 或 Provider SDK 类型。合同范围与生产者/消费者所有权见 [`第一阶段执行方案`](../docs/implementation-designs/0001-phase-1-execution-plan.md)。

TypeScript、Python 和 Java 必须消费同一版本化 Schema。当前 Python Dispatcher 已将 `SourceRevisionSubmitted` 严格转换为 JSON-only Celery 任务，并通过合同测试拒绝未知字段、错误版本、非法哈希、时间戳和幂等键；Java 侧以 Flyway 迁移和持久化 Outbox 生成同一事件字段。OpenAPI/JSON Schema 代码生成器仍需在 P1-00 后续批次完成正式兼容性验证后固定，当前不手写跨语言生成产物。合同格式和当前工程技术栈见 [`技术栈与外部选型总览`](../docs/technology-selection/technology-selection.md)。

## 当前 P1-00 合同目录

| 路径 | 用途 | 当前状态 |
| --- | --- | --- |
| `internal/v1/` | Java 创建、Python 校验的不可变 Project Execution Context | 已冻结并有 Python 合同测试 |
| `public/v1/openapi.yaml` | 上传预约、上传完成、任务状态和统一错误的 Public API 最小面 | 已冻结 v1 最小面 |
| `events/v1/` | Java Transactional Outbox 发布的 Source Revision 领域事件 | 已冻结 `SourceRevisionSubmitted v1` |
| `tasks/v1/` | Python Dispatcher 投递给 Celery 的 JSON 任务 envelope | 已冻结 `source_revision.process v1` |
| `sse/v1/` | Runtime/Platform 共享的事件 envelope | 已冻结 envelope，业务事件按阶段扩展 |
| `common/v1/` | 错误、Trace 和幂等字段的共享语义 | 已冻结基础字段 |

上传链路的状态顺序固定为：

```text
POST upload reservation
  -> OSS-compatible Source Zone 写入（预签名 PUT；Source Storage Adapter 使用服务端生成的 key）
  -> POST source-revisions/{id}/complete
  -> 校验 SHA-256 / Content-Type / Content-Length
  -> MySQL SourceRevision + Task 转为 QUEUED
  -> 同一事务写 Outbox
  -> Kafka SourceRevisionSubmitted
  -> Python Dispatcher
  -> Celery JSON task
```

预约阶段不得发布领域事件；对象未通过 Source Zone 校验时不得进入 Worker。Java 不直接写 Celery Redis 私有消息，Celery 禁止 `pickle`。
