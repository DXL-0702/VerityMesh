# Reranker 模型选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 检索精排主候选 | 对 RRF Top 50 候选进行相关性精排并输出 Top 10 | 百炼 `qwen3-rerank` | 云 API；不可变模型 Revision、地域、配额和容量待真实环境固定 | `CONFIRMED_WITH_GATES` | RRF 后、Evidence Hub 前 | M3 | RRF Top 10；同云 `gte-rerank-v2` 挑战者 | 新一代中文与混合文档精排主候选；必须相对 RRF-only 产生显著、可复现的 NDCG/MRR/Top-3 Evidence 收益，Score 不能替代 Grounding | 与两个 Embedding、两个搜索引擎和同云挑战者执行阶段化联合矩阵，关闭版本、质量、延迟、吞吐和成本门禁 |
| 同云精排挑战者 | 建立成熟同云 Reranker 的质量、延迟和成本基线 | 百炼 `gte-rerank-v2` | 云 API；不可变模型 Revision 待固定 | `CHALLENGER_POC` | 离线联合评测及条件备选 | M3 PoC | `qwen3-rerank`；RRF-only | 与主候选共享供应商、地域和调用面，可把比较重点限制在模型质量与成本，不把跨云变量混入结果 | 使用相同 RRF 候选、Query 和 Top-N 比较质量、长文本能力、延迟、稳定性与价格，仅在明确胜出时升级 |
| 自托管精排候选 | 在云端模型出现成本、容量、合规或稳定性硬缺口时提供替代 | `BAAI/bge-reranker-v2-m3` | ACK 自托管；推理运行时、模型 Revision、节点和批处理未定 | `DEFERRED` | Reranker 条件替代 | 后期 | 百炼主候选与同云挑战者；RRF-only | 首轮引入会把模型质量比较与推理运行时、硬件和运维选型混在一起，当前没有足够收益证据 | 云端方案触发量化硬门禁后，与自托管推理运行时一起专项立项 |
