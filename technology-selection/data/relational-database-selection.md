# 关系数据库选型

## 文档定位

本文件只记录权威关系数据库、Conversation 持久存储及托管产品的外部依赖选型；详细设计以架构文档为准。

## 外部依赖选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 关系数据库技术 | 保存权威元数据、事务状态、权限、发布状态、审计和持久 Conversation 数据 | PostgreSQL | 目标主版本未定 | `SELECTED` | Control Plane、Data Plane、Knowledge Plane 和 Conversation Store | 1A | 无第一阶段异构数据库替代 | 满足关系事务、约束、版本、权限和管理查询需求 | 冻结目标 PostgreSQL 主版本和扩展清单 |
| 托管关系数据库形态 | 承载第一阶段 PostgreSQL 权威写路径 | 阿里云托管 PostgreSQL 兼容产品 | 产品、SKU、拓扑和版本未定 | `CONFIRMED_WITH_GATES` | 阿里云生产 Region | 1A | ACK 自建仅在托管产品无法满足硬门禁时重新评审 | 与主云一致且降低数据库 HA、备份、升级和运维负担 | 对 RDS PostgreSQL 与 PolarDB PostgreSQL 执行同条件 PoC |
| 托管 PostgreSQL 候选 | PostgreSQL 托管数据库候选 | 阿里云 RDS PostgreSQL | 版本、规格和高可用拓扑未定 | `UNSELECTED` | 权威关系数据库 | 1A 上线前 | 阿里云 PolarDB PostgreSQL | PostgreSQL 兼容性、成熟托管能力、HA、PITR、扩展和成本待验证 | 与 PolarDB 使用相同数据和场景评测，不预设主次 |
| 托管 PostgreSQL 候选 | PostgreSQL 兼容分布式云数据库候选 | 阿里云 PolarDB PostgreSQL | 版本、规格和高可用拓扑未定 | `UNSELECTED` | 权威关系数据库 | 1A 上线前 | 阿里云 RDS PostgreSQL | 弹性、读扩展、存储增长和成本可能具备优势，但兼容和运维语义需实测 | 与 RDS 使用相同数据和场景评测，不预设主次 |
| Conversation 物理隔离形态 | 隔离持久 Conversation 与核心元数据的容量、保留和故障影响 | 未定 | 同集群独立命名空间/数据库或独立实例 | `UNSELECTED` | PostgreSQL Conversation Store | 1A 上线前 | 在选定 PostgreSQL 产品内调整拓扑 | Conversation 已确定由 PostgreSQL 持久化，但物理隔离强度需由容量、加密、保留期和故障域决定 | 完成容量与数据治理评审后冻结拓扑 |
| ACK 自建 PostgreSQL | 自行运行权威关系数据库 | 第一阶段不采用 | ACK 内自建 | `REJECTED` | 不进入第一阶段生产 | 条件重评 | 选定的阿里云托管 PostgreSQL 产品 | 托管优先，当前没有能力或合同缺口证明需要承担自建运维 | 仅在所有托管候选无法满足硬门禁时重新立项 |
