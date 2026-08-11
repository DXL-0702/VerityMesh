# assistant-runtime

| 属性 | 内容 |
| --- | --- |
| 类型 | Python/FastAPI 在线 AI Deployment |
| 包管理 | `uv` |
| 当前状态 | 仅建立目录边界，Python 应用尚未初始化 |

本目录负责不可变 Execution Context Guard、Project/Global Query Plan、Elasticsearch BM25 与 pgvector Vector Recall、RRF、Reranker、Evidence、Prompt、Model Access、Grounding、Citation 和已验证事件。

它不直接修改 MySQL 权威状态，不接受客户端自造 Scope，也不流出未验证模型 Token。受约束 RAG Domain Kernel 的详细边界见 [`ADR-001`](../../docs/adr/0001-constrained-rag-kernel-and-model-access.md)。
