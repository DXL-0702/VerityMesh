# 关系数据库选型

## 文档定位

本文件只记录 MySQL 业务权威库、PostgreSQL/pgvector 向量投影库、Conversation 持久存储、迁移工具及托管产品的外部依赖选型；详细设计以架构文档为准。

## 外部依赖选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 业务关系数据库技术 | 保存业务元数据、事务状态、权限、发布状态、审计和持久 Conversation | MySQL | 目标主版本未定 | `SELECTED` | Java `platform-api` Control Plane、Data Plane 和 Conversation Store | 1A | 无第一阶段异构业务库替代 | Java 业务事务和控制状态需要单一关系型所有者；与向量投影隔离 | 冻结目标 MySQL 主版本、字符集、排序规则和 SQL Mode |
| 托管 MySQL 形态 | 承载第一阶段 MySQL 权威写路径 | 阿里云托管 MySQL 兼容产品 | 产品、SKU、拓扑和版本未定 | `CONFIRMED_WITH_GATES` | 阿里云生产 Region | 1A | ACK 自建仅在托管产品无法满足硬门禁时重新评审 | 与主云一致并降低数据库 HA、备份、升级和运维负担 | 对 RDS MySQL 与 PolarDB MySQL 执行同条件 PoC |
| 托管 MySQL 候选 | MySQL 托管数据库候选 | 阿里云 RDS MySQL | 版本、规格和高可用拓扑未定 | `UNSELECTED` | 业务权威数据库 | 1A 上线前 | 阿里云 PolarDB MySQL | 兼容性、成熟托管能力、HA、PITR、迁移工具兼容和成本待验证 | 与 PolarDB 使用相同数据和事务场景评测，不预设主次 |
| 托管 MySQL 候选 | MySQL 兼容分布式云数据库候选 | 阿里云 PolarDB MySQL | 版本、规格和高可用拓扑未定 | `UNSELECTED` | 业务权威数据库 | 1A 上线前 | 阿里云 RDS MySQL | 弹性、读扩展和存储增长可能具备优势，但事务兼容与运维语义需实测 | 与 RDS 使用相同数据和事务场景评测，不预设主次 |
| Conversation 物理隔离形态 | 隔离持久 Conversation 与核心元数据的容量、保留和故障影响 | 未定 | MySQL 同实例独立 Schema 或独立实例 | `UNSELECTED` | MySQL Conversation Store | 1A 上线前 | 在选定 MySQL 产品内调整拓扑 | Conversation 已确定由 MySQL 持久化，但隔离强度取决于容量、加密、保留期和故障域 | 完成容量与数据治理评审后冻结拓扑 |
| ACK 自建 MySQL | 自行运行业务权威数据库 | 第一阶段不采用 | ACK 内自建 | `REJECTED` | 不进入第一阶段生产 | 条件重评 | 选定的阿里云托管 MySQL 产品 | 当前没有能力或合同缺口证明需要承担自建运维 | 仅在所有托管候选无法满足硬门禁时重新立项 |
| 向量投影数据库技术 | 保存可重建 Chunk、Citation、检索过滤元数据和 Dense Vector | PostgreSQL + pgvector | PostgreSQL 主版本与 pgvector 扩展版本未定 | `SELECTED` | Python Vector Serving Projection | 1A | Milvus 仅在量化硬门禁失败后评审 | 原生 SQL 过滤与向量索引适配冻结的数据边界；不保存业务权威状态 | 冻结 PostgreSQL/pgvector 版本、距离函数、索引类型和容量边界 |
| 托管 PostgreSQL/pgvector 形态 | 承载第一阶段 Vector Serving Projection | 支持 pgvector 的阿里云托管 PostgreSQL 兼容产品 | 产品、SKU、拓扑、版本与扩展支持未定 | `CONFIRMED_WITH_GATES` | 阿里云生产 Region | 1A | ACK 自建仅在托管产品无法满足向量硬门禁时重评 | 降低 HA、备份和升级运维，同时必须验证扩展与索引能力 | 对托管候选执行同数据、同索引、同过滤和同容量 PoC |
| 托管 PostgreSQL/pgvector 候选 | PostgreSQL 托管数据库候选 | 阿里云 RDS PostgreSQL | 版本、规格、pgvector 支持和高可用拓扑未定 | `UNSELECTED` | Vector Serving Projection | 1A 上线前 | 阿里云 PolarDB PostgreSQL | pgvector 扩展、HNSW/IVFFlat、备份恢复、扩容和成本待真实实例验证 | 与 PolarDB 使用相同 Vector 场景评测，不预设主次 |
| 托管 PostgreSQL/pgvector 候选 | PostgreSQL 兼容分布式云数据库候选 | 阿里云 PolarDB PostgreSQL | 版本、规格、pgvector 支持和高可用拓扑未定 | `UNSELECTED` | Vector Serving Projection | 1A 上线前 | 阿里云 RDS PostgreSQL | 必须先核实目标版本的 pgvector 与索引能力，不能从 PostgreSQL 兼容名称推定 | 与 RDS 使用相同 Vector 场景评测，不预设主次 |
| ACK 自建 PostgreSQL/pgvector | 自行运行 Vector Serving Projection | 第一阶段不采用 | ACK 内自建 | `REJECTED` | 不进入第一阶段生产 | 条件重评 | 选定的托管 PostgreSQL/pgvector 产品 | 当前没有托管能力缺口证明值得承担数据库运维 | 仅在所有托管候选无法满足向量硬门禁时重新立项 |
| Java Schema Migration | 版本化管理 MySQL DDL、索引、约束和迁移校验 | Flyway | `12.4.0`，由 Spring Boot `4.1.0` BOM 管理 | `SELECTED` | `platform-api` 独立 Migration Job | 1A | Liquibase 仅在 Flyway 出现明确能力缺口时重评 | Spring Boot 集成直接、SQL-first、迁移历史和校验语义清晰 | 验证空库、N-1 升级、中断重试和滚动兼容 |
| Python Schema Migration | 版本化管理 PostgreSQL `vector` 扩展、Projection 表和向量索引 | Alembic | `1.18.5`，由 `uv.lock` 锁定 | `SELECTED` | Python 独立 Migration Job | 1A | 无第一阶段替代 | 与 Python/SQLAlchemy 生态一致，支持显式 Migration Revision 和离线 SQL 审核 | 验证单一 Head、空库、N-1 升级、中断重试和滚动兼容 |
