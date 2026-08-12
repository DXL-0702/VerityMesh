# assistant-runtime

| 属性 | 内容 |
| --- | --- |
| 类型 | Python/FastAPI 在线 AI Deployment |
| 包管理 | `uv` |
| 当前状态 | 在线入口、Execution Context、Revocation Guard、确定性 Project Query Plan、混合召回、Domain RRF、Reranker、Evidence Hub 与 Prompt Builder 领域基线已建立；Generator、Grounding、已验证 Claim Stream 与 SSE 尚未实现 |

本目录负责不可变 Execution Context Guard、Project/Global Query Plan、Elasticsearch BM25 与 pgvector Vector Recall、RRF、Reranker、Evidence、Prompt、Model Access、Grounding、Citation 和已验证事件。

它不直接修改 MySQL 权威状态，不接受客户端自造 Scope，也不流出未验证模型 Token。受约束 RAG Domain Kernel 的详细边界见 [`ADR-001`](../../docs/adr/0001-constrained-rag-kernel-and-model-access.md)。

当前已经建立 FastAPI 应用入口、Liveness/Readiness、严格不可变的 Project Execution Context、统一 Deadline Guard，以及只接受 `platform-api` mTLS 身份的内部 Context 校验入口。调用方身份必须由完成证书校验的 ASGI Server 或受信 Middleware 写入 `veritymesh.internal-caller` Scope Extension；Runtime 不信任任何客户端身份 Header，缺失或无效时 fail closed。

Project Execution Context 的正式跨语言 Schema 位于 [`contracts/internal/v1/`](../../contracts/internal/v1/)，Python 消费模型通过漂移测试与其保持一致。`RevocationGuard` 要求 `RevocationCheckerPort` 返回完整 Scope、三态结果、快照版本和受限有效窗口；已撤回、状态未知、调用失败、Scope 错配、未来或陈旧结果均 fail closed，统一 Deadline 在调用前后重新校验。只有 `RevocationClearedExecutionContext` 可以进入确定性 `ProjectQueryPlan`，Plan 会继续携带撤回快照版本和有效期，并固定简单问题的查询归一化、可信过滤范围、混合检索参数与强制证据门禁，不调用模型。

`HybridRetrievalKernel` 只接受已清场 Context、已验证 Plan 和服务端解析的联合 Projection 元数据。BM25 与 Query Embedding/Vector Recall 并发启动，Vector 分支内部按 Embedding 后 Recall 的顺序执行；三类任务端口只暴露平台 DTO、统一 Deadline、审计上下文、过滤条件、Manifest、Watermark、配置指纹和 Embedding Space，不暴露 Elasticsearch DSL、SQL、索引名或 Provider SDK 类型。两路结果在 RRF 前重新校验 Scope、Release、Access Segment、有效期、撤回快照、Projection 和 Embedding Space，按稳定 `chunk_id` 去重并保留原始 Rank/Score；同一 Chunk 的内容或 Citation 投影不一致时 fail closed。Vector 失败可带稳定原因降级为 BM25-only，BM25 失败不启用未冻结的 Vector-only 行为。

`RerankingKernel` 在任何正文出站前重新构造并复核检索结果，只向任务端口发送 Query 与最小候选正文；结果必须回显可信模型 Binding、Execution 和候选集指纹。Provider 不可用或响应无效时不在在线 Deadline 内重试，而是保留稳定降级原因并回退 RRF Top 10。`EvidenceHub` 再次复核执行 Scope，并通过独立任务端口批量检查候选内容撤回状态；已撤回候选被排除，未知、陈旧、错配或不完整结果整体 fail closed。输出 `EvidencePacket` 保留执行与内容撤回快照、完整检索/精排 Provenance、确定性 Evidence ID，以及只允许 Citation Proxy 或服务端白名单 HTTPS Origin 的公开 Citation，不包含内部 Source Locator。

`PromptBuilder` 只接收经过 Evidence Hub 校验的 `EvidencePacket`，在再次复核执行租约、Project/Version/Locale/Release/Access Segment 和 Memory 项目边界后，按固定的 `Policy -> Memory -> Evidence -> User Query` 顺序输出不可变 Provider-neutral Prompt DTO。Policy、Memory 和 Evidence 使用不同的领域类型与消息段；Memory 只用于连续性，不具备事实或 Citation 语义。Evidence 输出仅保留安全的项目、版本、Release、标题、章节、正文和 Citation 信息，不携带 Access Context Hash、内部 Source Locator、索引名或物理存储路径。Prompt Builder 不调用模型、不执行网络请求、不生成答案；字符/估算 Token 预算不足、Scope 不匹配、Packet 非法或 Evidence 缺失时 fail closed，不静默截断事实证据。空 Evidence 生成显式受限拒答 Prompt，并保留 Pipeline Provenance 与 Prompt Fingerprint。

当前仍不包含 Public Query Schema、Redis Online Revocation Adapter、真实 Elasticsearch/pgvector Adapter、Reranker Provider Adapter、内容撤回状态 Adapter、其他模型 Provider Adapter、Generator、Grounding、已验证 Claim Stream 或 SSE。版本总览见 [`技术栈与外部选型总览`](../../docs/technology-selection/technology-selection.md)，后续交付边界见 [`第一阶段执行方案`](../../docs/implementation-designs/0001-phase-1-execution-plan.md)。本地可执行版本以成员 `pyproject.toml` 和根 `uv.lock` 为准。

应用入口为 `veritymesh_assistant_runtime.app:app`。在仓库根目录使用现有锁文件离线验证：

```sh
UV_OFFLINE=1 ./tools/verify-python.sh
```
