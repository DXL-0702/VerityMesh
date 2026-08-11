# PoC 报告目录

本目录用于保存候选产品、模型和托管服务的评测证据。

每份报告应记录固定数据集与负载、环境、版本、指标口径、原始结果、结论和限制，并关联 [`../technology-selection/technology-selection.md`](../technology-selection/technology-selection.md) 中的 Decision ID。PoC 报告提供决策证据，不承担架构定义或产品状态登记。

| 报告 | 证据等级 | 生成时关联决策 | 当前适用性 |
| --- | --- | --- | --- |
| [文本检索栈本地合同报告](text-retrieval-poc-local-contract-2026-08-10.md) | `HARNESS_VALIDATION` | 当时的 `RET-001/002/003/010`、`MODEL-014/015/026/027/028`、`GOV-007` | RRF、Citation、过滤和降级 Harness 证据继续有效；单引擎 Dense Vector 与 Alias 结论已被 ADR-003 取代 |

本地合同报告只验证 harness、算法编排、Citation 和安全门禁，不提供云产品质量或性能结论。真实云端矩阵完成后使用独立文件建档，不覆盖本地证据等级。

2026-08-11 冻结 [`ADR-003`](../adr/0003-mysql-authority-and-pgvector-retrieval-projection.md) 后，目标链路改为 Elasticsearch BM25 + PostgreSQL/pgvector Vector。上述历史报告不能关闭当前 `RET-001/002/003/011` 的联合产品门禁；新报告必须使用拆分后的两套真实 Adapter、同一过滤合同和 Joint Projection Gate。
