# 向量检索存储选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 首期 Vector Recall 存储 | 保存可重建 Chunk、Citation、过滤字段和 Dense Vector，并在召回前执行严格范围过滤 | PostgreSQL + pgvector | PostgreSQL 主版本、pgvector 扩展、托管产品、索引和拓扑待定 | `SELECTED` | Vector Serving Projection | 第一阶段 1A | Milvus 仅在 pgvector 出现量化硬缺口后评审 | 符合 Python RAG 数据所有权，支持 SQL 过滤与向量索引；不接触 MySQL 业务权威状态，不依赖 Elasticsearch 私有混合分数 | 关闭同过滤合同、HNSW/IVFFlat、召回质量、P95、容量、重建、迁移、备份恢复和成本门禁 |
| 独立 Vector Recall 数据库 | 在 PostgreSQL/pgvector 无法满足量化门禁时替换 Vector Adapter | Milvus | 托管或 ACK 自建形态、版本和拓扑未定 | `DEFERRED` | Vector Recall；不承载业务权威元数据或 BM25 | 后期条件引入 | 继续使用 PostgreSQL/pgvector | 当前没有质量、性能或成本证据证明需要承担额外产品与迁移面 | pgvector 经索引、分区、量化、扩容和托管产品调优后仍不达门禁时启动同条件 PoC |
| 一体化检索平台候选 | 尝试整体替代 BM25 与 Vector 两套检索投影 | Weaviate | 托管或自建形态、版本和拓扑未定 | `DEFERRED` | Retrieval Serving Projection | 后期替代性评审 | 维持 Elasticsearch BM25 + PostgreSQL/pgvector Vector | 只有整体替代并显著降低复杂度才有价值，不能作为第三套长期并存系统 | 证明可完整表达两路独立 Rank、严格过滤、发布、撤回和高亮且总体更优后重评 |
| 重叠向量投影或多检索系统长期并存 | 在 PostgreSQL/pgvector 与 Elasticsearch 永久双存 Dense Vector，或再长期叠加 Milvus/Weaviate | 不采用 | 不适用 | `REJECTED` | 不进入目标架构 | 全阶段 | 保持 Elasticsearch BM25 与 PostgreSQL/pgvector Vector 各自单一职责 | 重叠存储不增加有效能力，却放大漂移、权限、发布、撤回、删除、容量和重建复杂度 | 仅检索架构正式重构且量化收益超过一致性与运维成本时重评 |
