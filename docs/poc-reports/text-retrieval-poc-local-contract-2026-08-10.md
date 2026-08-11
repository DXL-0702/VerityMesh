# 文本检索栈 PoC 报告

- 生成时间：`2026-08-10T20:15:01+08:00`
- 证据等级：HARNESS_VALIDATION: deterministic local engine and synthetic or local fixture data only; this validates the harness contract, not production retrieval quality or cloud performance.
- 语料 SHA-256：`e33c3d09fd5232392131ce6915a6c0b624d324acc9f5f65278dda1e6c061cf91`
- Query 集 SHA-256：`647d754daff087df402aaa8c8d591b5b91ea55627f89ae8f2551d474fe4537a7`
- 执行说明：本地 Unicode Regex Tokenizer、确定性 Hash Embedding 和内存检索引擎。仅用于验证数据契约、算法编排、Citation 与硬门禁 harness。

## 已执行配置

| 配置 | 证据等级 | Recall@10 | NDCG@10 | MRR@10 | Top-3 有效 Evidence | Search P95 | 硬门禁 | 结果 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |
| `p0-in-memory-contract-deterministic-hash-structure-aware-rrf-only` | HARNESS_VALIDATION | 100.0% | 100.0% | 100.0% | 100.0% | 0.45 ms | PASS | passed |
| `p0-in-memory-contract-deterministic-hash-fixed-recursive-rrf-only` | HARNESS_VALIDATION | 100.0% | 100.0% | 100.0% | 100.0% | 0.31 ms | PASS | passed |
| `p0-in-memory-contract-deterministic-hash-semantic-boundary-rrf-only` | HARNESS_VALIDATION | 100.0% | 100.0% | 100.0% | 100.0% | 0.31 ms | PASS | passed |
| `p0-in-memory-contract-deterministic-hash-structure-aware-local-lexical-rerank` | HARNESS_VALIDATION | 100.0% | 100.0% | 100.0% | 100.0% | 0.39 ms | PASS | passed |

## 决策

当前结论：`CONFIRMED_WITH_GATES`。这不是对技术选型正文的状态修改；它是本轮 PoC 的可追溯结论。

| 决策对象 | 暂定选择 | 状态 | 判断 |
| --- | --- | --- | --- |
| RET-001, RET-002 | 阿里云 Elasticsearch 向量增强版 8.17 | `CONFIRMED_WITH_GATES` | 优先满足单引擎 BM25、Dense Vector、严格过滤、高亮、Release 隔离的 Staging/Active Projection 与原子 Alias 切换；PoC 独立 Release 索引不代表生产物理拓扑已冻结。 |
| RET-003 | 阿里云 OpenSearch 向量检索版 | `CHALLENGER_POC` | 保留为同条件挑战者。其 SDK 已能表达文本、向量和 RRF 请求，但部署表 Schema、过滤表达式、撤回投影、写入删除和运行时能力仍须以真实实例关闭。 |
| RET-010 | Elasticsearch IK Analysis；索引 ik_max_word、查询 ik_smart，并保留 standard/identifier 多字段 | `PRIMARY_POC` | 中文与企业术语需要可控分词；插件版本、词典发布、升级兼容和相对标准 Analyzer 的质量收益仍须在真实 Elasticsearch 8.17 实例验证。 |
| MODEL-014 | 百炼 qwen3.7-text-embedding；1024 维 Dense、Cosine、L2 v1、float32、原生 Query/Document 角色 | `CONFIRMED_WITH_GATES` | 作为主候选；不可变模型 Revision、固定 Fast Offset Tokenizer 和完整空间指纹是生产硬门禁，任何变化均强制新 Release 重建。 |
| MODEL-026 | 百炼 text-embedding-v4，同输入合同、独立向量空间 | `CHALLENGER_POC` | 只作同云质量、延迟和成本挑战者，不作为在线热备，也不与主候选混用。 |
| MODEL-015 | 百炼 qwen3-rerank；RRF Top 50 为降级路径 | `CONFIRMED_WITH_GATES` | 精排只作用于 RRF 后候选并输出 Top 10；故障时回退 RRF，不把 Rerank Score 当作 Grounding 置信度。 |
| MODEL-027 | 百炼 gte-rerank-v2 | `CHALLENGER_POC` | 作为同云成熟基线，与 qwen3-rerank 使用完全相同的 RRF 候选和指标比较。 |
| MODEL-028 | BAAI/bge-reranker-v2-m3 自托管 | `DEFERRED` | 只有云端 Reranker 出现成本、容量、合规或稳定性硬缺口时，才与自托管推理运行时联合立项。 |
| GOV-007 | 不引入外部通用 Chunker；使用自有结构感知、分层且可回溯 Citation 的确定性 Chunker | `REJECTED` | 固定递归只作基准，Embedding Semantic Boundary 只作挑战者；生产仍需使用冻结的真实模型 Tokenizer 验证边界。 |

选择升级条件：只有真实企业语料、真实阿里云实例、真实百炼模型调用、质量/性能门槛和全部硬门禁均通过，才允许升级为 SELECTED。

## 未关闭门禁

- 同一企业评测集上的 Recall@10 >= 90% 与 Top-3 有效 Evidence 比例 >= 85%。
- 真实网络条件下 Search P95 <= 1 秒，已批准变更到可检索 P95 <= 5 分钟。
- 真实实例中的跨 Project/Version/Locale/Access Segment 过滤、撤回、删除、幂等重放、Release 切换与回滚。
- Elasticsearch 8.17 中 IK 插件版本、项目词典/同义词随 Release 发布、Analyzer 升级和重建行为。
- Embedding 与 Reranker 的不可变 Provider Revision、固定 Tokenizer Artifact/Revision、漂移 Canary 和输入上限。
- 阿里云地域、账号合同、日志/保留策略、配额、容量、成本与退出路径。

## 本地合同范围

以下项目由本地确定性合同夹具覆盖，覆盖结果只证明 harness 的行为，不证明云产品：

- `scope_isolation`
- `revocation_exclusion`
- `citation_round_trip`
- `embedding_space_compatibility`
- `release_atomic_switch_and_rollback`
- `update_delete_replay_idempotency`

本报告没有把本地 Hash Embedding、合成夹具或未配置的云端 adapter 伪装成百炼或托管搜索结果。
