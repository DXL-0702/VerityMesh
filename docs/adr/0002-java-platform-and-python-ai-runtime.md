# ADR-002：Java 平台业务边界与 Python AI Runtime

| 属性 | 内容 |
| --- | --- |
| 状态 | `PARTIALLY_SUPERSEDED` |
| 决策日期 | 2026-08-11 |
| 架构基线 | [`../tech-plan.md`](../tech-plan.md) 5.3 |
| 相关 ADR | [`0001-constrained-rag-kernel-and-model-access.md`](0001-constrained-rag-kernel-and-model-access.md) |
| 部分取代 | [`0003-mysql-authority-and-pgvector-retrieval-projection.md`](0003-mysql-authority-and-pgvector-retrieval-projection.md) |

> ADR-003 已取代本文关于 PostgreSQL 保存业务权威状态、Elasticsearch 同时承载 BM25/Vector 的存储条款。本文关于 Java/Python 领域边界、Kafka/Celery 分工、双 Redis 隔离、`uv` 和四个 Deployment 的决策继续有效。

## 1. 背景

第一阶段前端采用 React 19 + TypeScript，平台业务后端采用 Java/Spring Boot，模型、检索、文档处理和批任务采用 Python。若 Java 与 Python 分别持有 Session、Release、Scope、Evidence 或 Citation 的部分规则，会形成两个领域控制面，无法可靠证明发布、撤回、引用和输出门禁始终一致。

Kafka 已承担可重放领域事件，Redis 用于在线临时状态。Python Celery 适合文档解析、切分、Embedding、批量索引和评测，但不能成为业务状态机或可靠事件日志。

## 2. 决策

1. 采用 Monorepo，包含 React 前端、Java `platform-api`、Python `assistant-runtime`、Python `batch-worker` 与共享 OpenAPI/SSE/Kafka Schema。
2. `platform-api` 使用 Java/Spring Boot 模块化单体实现 `public-api`、`identity-access`、`knowledge-control`、Session/Thread、Release、审计和 Transactional Outbox。PostgreSQL 中的业务、权限、Session、Release 和任务状态由它唯一拥有。
3. Python `assistant-runtime` 使用 FastAPI 实现受约束 RAG Domain Kernel、Model Access、检索适配、Evidence、Citation、Grounding 和已验证 SSE 事件。它不直接修改 PostgreSQL 权威状态。
4. `platform-api` 完成身份、Grant、Binding 和 Release 元数据解析后，经内部 mTLS REST 传递不可由客户端构造的不可变 Project Execution Context。Python Runtime 在检索和 Evidence 处理中重新应用该 Context，Java 不复制 RAG Kernel 规则。
5. Python `batch-worker` 使用 Celery 执行解析、OCR、Chunk、Embedding、批量索引和评测。Kafka Consumer 将领域事件转换为 Celery JSON Task；任务进度和完成结果重新发布为 Kafka Event。
6. Redis Online 用于 Session、短期 Memory、限流、授权缓存和撤回清单；Redis Celery 仅用于 Broker 与短期 Result。二者必须至少逻辑隔离，生产实例数、SKU 和持久化策略由 Redis 产品 PoC 决定。
7. Python 依赖和工作区统一使用 `uv` 与单一 `uv.lock`。前端不保留旧框架兼容实现；Web Component 由 React 主实现直接注册。

## 3. 所有权与通信

```text
Browser / Host Backend
  -> platform-api: REST / SSE / Bootstrap Token
  -> assistant-runtime: internal mTLS REST + immutable execution context

platform-api PostgreSQL Outbox
  -> Kafka durable domain event
  -> Python dispatcher
  -> Celery / Redis Celery
  -> batch-worker
  -> Kafka progress or completion event
  -> platform-api state projection
```

- 外部 API 的事实合同是 OpenAPI 和 SSE Event Schema；Java 与 Python 不共享进程内 DTO 或 ORM。
- Celery 使用 JSON 序列化、幂等键、有限重试和失败事件；禁止 Java 直接生产 Celery 私有消息，禁止使用 `pickle`。
- Kafka 保存可重放领域事件；Celery 只负责短生命周期任务执行。PostgreSQL 始终保存任务、Release 和激活状态真相。
- `assistant-runtime` 只接收已认证的内部调用，返回经过 Citation 与 Grounding 门禁的事件；`platform-api` 只转发已验证事件并记录审计。

## 4. 部署粒度

第一阶段固定四个 Deployment：

| Deployment | 运行时 | 主要扩缩容信号 |
| --- | --- | --- |
| `portal-web` | React 19 + TypeScript | Web 请求和静态资源负载 |
| `platform-api` | Java/Spring Boot | 请求并发、SSE 连接和延迟 |
| `assistant-runtime` | Python/FastAPI | RAG 请求、模型等待和 SSE 连接 |
| `batch-worker` | Python/Celery | Kafka Lag、Celery Queue 等待时间和任务资源类型 |

逻辑模块不是独立 Deployment 的理由。只有独立扩缩容、独立发布、明显故障隔离或安全域要求出现时，才重新评估拆分。

## 5. 备选与取舍

| 方案 | 结论 | 原因 |
| --- | --- | --- |
| Java 实现全部 RAG Kernel，Python 只调用模型 | 不采用 | 使检索、Tokenizer、Provider Adapter 和评测与 Python PoC 分裂，领域规则会跨语言复制 |
| Java 与 Python 各实现一部分 RAG Kernel | 不采用 | Scope、Release、Evidence、Citation 和 Grounding 会形成双控制面 |
| Java 直接写 Celery Redis | 不采用 | 依赖 Python 私有任务协议，无法保证幂等、兼容和演进 |
| Kafka 直接替代全部批任务执行 | 不采用 | Kafka 适合可靠事件与消费，不提供 Celery 的 Python Task、组批、重试和资源队列能力 |
| 共享一个 Redis 容纳在线缓存和 Celery Broker | 不采用 | 批任务堆积、淘汰和访问边界会影响在线 Session、撤回和限流 |

## 6. 替代条件

- Java/Python 跨服务延迟、错误映射或上下文合同经压测证明无法满足在线目标。
- Celery 的任务重试、资源隔离或运维边界出现量化硬缺口。
- 出现新的前端框架且有明确需求和维护者；届时以 Web Component 公开合同为基础单独评审兼容层。
- 运行时需要独立发布、独立扩缩容、强安全隔离或团队边界，且当前四 Deployment 无法满足。
