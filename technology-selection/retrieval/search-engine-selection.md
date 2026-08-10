# 搜索引擎选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 首期混合搜索引擎 | 在单一首期产品中承载 BM25、Vector、过滤、正文和高亮 | 阿里云 Elasticsearch 向量增强版 8.17 | 托管服务；具体 SKU、拓扑和生产参数待定 | `CONFIRMED_WITH_GATES` | Retrieval Serving Projection | 第一阶段上线前 | 阿里云 OpenSearch 向量检索版挑战者；开源 OpenSearch 仅作基准/条件候选 | 当前更直接满足独立 BM25/Vector 召回、严格过滤、正文高亮、Release 隔离的 Staging/Active Projection 与原子 Alias 切换；尚无真实企业语料和云实例证据，不能升级为 `SELECTED` | 使用真实企业评测集和隔离云实例关闭质量、权限、撤回、增量更新、容量、延迟、成本、物理索引布局与退出门禁 |
| 托管搜索主候选 | 提供 Elasticsearch 兼容的全文与向量搜索 | 阿里云 Elasticsearch 向量增强版 8.17 | 托管服务；具体 SKU、节点、分片、副本与参数待定 | `CONFIRMED_WITH_GATES` | Retrieval Serving Projection | 第一阶段 PoC | 阿里云 OpenSearch 向量检索版 | REST Adapter 已能表达独立召回、过滤、Release 隔离和 Alias 原子切换；PoC 使用独立 Release 索引只验证合同，不预先决定生产采用完整版本索引、Delta Segment 或分区索引 | 完成真实实例联合矩阵、写入型撤回/删除/回滚合同、容量成本与物理布局验证 |
| 托管搜索挑战者 | 提供阿里云托管搜索与向量能力 | 阿里云 OpenSearch 向量检索版 | 产品版本、规格、表 Schema、Namespace 与拓扑待定 | `CHALLENGER_POC` | Retrieval Serving Projection | 第一阶段 PoC | 阿里云 Elasticsearch 向量增强版 8.17 | SDK 能表达文本、向量和原生 RRF 请求，但过滤表达式、撤回投影、写入删除、Release 切换与接口锁定仍需真实实例关闭 | 与 Elasticsearch 使用同一语料和门禁执行真实云实例 PoC，仅在质量、成本或运维存在明确优势时升级 |
| 自建搜索基准 | 验证托管产品的能力、成本和退出边界 | 开源 OpenSearch | ACK 自建；具体版本未定 | `BENCHMARK` | 非生产基准或托管产品硬门禁失败后的条件候选 | 第一阶段仅按需 PoC | 选择一个托管搜索产品 | 自建不应与托管候选拥有同等生产资格，但可帮助识别产品锁定或能力缺口 | 仅当托管产品存在明确硬缺口时升级为正式候选 |
| 中文 BM25 Analyzer 插件 | 为中文正文、标题和章节提供可配置分词，并保留英文、代码和标识符多字段 | Elasticsearch IK Analysis | 与阿里云 Elasticsearch 8.17 兼容的托管插件版本待真实实例确认；索引 `ik_max_word`、查询 `ik_smart` | `PRIMARY_POC` | Elasticsearch BM25 字段 | 第一阶段 PoC | `standard` + `keyword/whitespace` 多字段保守回退 | 企业术语和中文召回需要可控词典；项目词典、同义词和停用词必须随 Release 版本化，不能依赖全局热更新 | 核实托管插件版本、升级兼容、词典部署、重建行为，并与标准 Analyzer 做同语料质量和延迟对照 |
