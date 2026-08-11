# Kubernetes 平台选型

## 文档定位

本文件只记录 Kubernetes 平台和弹性组件的外部依赖选型；工作负载划分、容量和运行规范不在本文件维护。

## 外部依赖选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 托管 Kubernetes | 承载平台计算工作负载 | 阿里云容器服务 ACK | 托管形态、Kubernetes 版本和服务等级未定 | `SELECTED` | Control Plane、Data Plane、Index Worker 及允许自托管的轻量模型 | 1A | 无第一阶段同级替代平台 | 与已选主云一致，降低 Kubernetes 控制面和基础运维负担 | 冻结 ACK 形态、版本、服务等级和升级支持周期 |
| Kubernetes 计算实例 | 为不同计算负载提供节点资源 | 未定 | 节点池实例族、CPU/GPU、磁盘和规格未定 | `UNSELECTED` | ACK 节点池 | 1A 上线前 | 按 Region 供给和容量测试选择兼容实例族 | 需以在线并发、索引吞吐和自托管模型需求确定 | 冻结实例族、规格和容量基线 |
| 事件驱动弹性组件 | 为异步工作负载提供事件驱动弹性 | KEDA | 具体版本未定 | `SELECTED` | ACK Index Worker | 1A | Kubernetes 原生弹性能力作为降级选择 | 与 ACK、Kafka 兼容并适合异步积压驱动的工作负载 | 冻结 KEDA 版本及 ACK/Kubernetes 兼容性 |
