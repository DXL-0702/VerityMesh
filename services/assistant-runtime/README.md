# assistant-runtime

| 属性 | 内容 |
| --- | --- |
| 类型 | Python/FastAPI 在线 AI Deployment |
| 包管理 | `uv` |
| 当前状态 | 在线入口、Execution Context 与确定性 Project Query Plan 基线已建立；业务 RAG 尚未实现 |

本目录负责不可变 Execution Context Guard、Project/Global Query Plan、Elasticsearch BM25 与 pgvector Vector Recall、RRF、Reranker、Evidence、Prompt、Model Access、Grounding、Citation 和已验证事件。

它不直接修改 MySQL 权威状态，不接受客户端自造 Scope，也不流出未验证模型 Token。受约束 RAG Domain Kernel 的详细边界见 [`ADR-001`](../../docs/adr/0001-constrained-rag-kernel-and-model-access.md)。

当前已经建立 FastAPI 应用入口、Liveness/Readiness、严格不可变的 Project Execution Context、统一 Deadline Guard，以及只接受 `platform-api` mTLS 身份的内部 Context 校验入口。调用方身份必须由完成证书校验的 ASGI Server 或受信 Middleware 写入 `veritymesh.internal-caller` Scope Extension；Runtime 不信任任何客户端身份 Header，缺失或无效时 fail closed。

Project Execution Context 的正式跨语言 Schema 位于 [`contracts/internal/v1/`](../../contracts/internal/v1/)，Python 消费模型通过漂移测试与其保持一致。确定性 `ProjectQueryPlan` 已固定简单问题的查询归一化、可信过滤范围、混合检索参数和强制证据门禁，不调用模型；`QueryPlannerPort` 只暴露任务语义，离线可记录替身位于测试支持目录。当前仍不包含 Public Query Schema、Revocation Guard、检索 Adapter、模型 Provider Adapter、完整 RAG Kernel、Grounding 或 SSE。版本总览见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)，后续交付边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。本地可执行版本以成员 `pyproject.toml` 和根 `uv.lock` 为准。

应用入口为 `veritymesh_assistant_runtime.app:app`。在仓库根目录使用现有锁文件离线验证：

```sh
UV_OFFLINE=1 ./tools/verify-python.sh
```
