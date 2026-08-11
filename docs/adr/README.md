# 架构决策记录目录

本目录用于保存会改变系统边界、关键不变量或长期演进方向的重大决策记录。

ADR 应说明背景、决策、备选、权衡、影响和替代条件。常规产品状态变化记录在 [`../technology-selection/technology-selection.md`](../technology-selection/technology-selection.md)；只有当选型变化同时改变架构边界时，才需要新增 ADR 并同步更新 [`../tech-plan.md`](../tech-plan.md)。

| ADR | 状态 | 决策 |
| --- | --- | --- |
| [`ADR-001`](0001-constrained-rag-kernel-and-model-access.md) | `ACCEPTED` | 采用受约束 RAG Domain Kernel、两层 Model Access，并限制 LangChain、LangGraph 与 MaxKB 的边界 |
| [`ADR-002`](0002-java-platform-and-python-ai-runtime.md) | `PARTIALLY_SUPERSEDED` | Java 平台与 Python AI Runtime/批处理边界；数据库和检索存储条款已由 ADR-003 取代 |
| [`ADR-003`](0003-mysql-authority-and-pgvector-retrieval-projection.md) | `ACCEPTED` | MySQL 业务权威、OSS 内容事实源、PostgreSQL/pgvector Vector Projection、Elasticsearch BM25 Projection 与迁移所有权 |
