# BM25 搜索引擎选型图

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 首期 BM25 搜索引擎 | 承载 BM25、严格过滤、正文、高亮和版本化文本投影，不保存 Dense Vector | 阿里云 Elasticsearch 8.17 | 托管服务；具体 SKU、拓扑和生产参数待定 | `CONFIRMED_WITH_GATES` | BM25 Serving Projection | 第一阶段上线前 | 阿里云 OpenSearch 文本检索产品挑战者；开源 OpenSearch 仅作基准/条件候选 | 与 PostgreSQL/pgvector 分工后职责单一，直接支持多字段 BM25、过滤、高亮和不可变 Release Projection；尚无真实企业语料和云实例证据 | 使用真实企业评测集和隔离云实例关闭 BM25 质量、权限、撤回、增量更新、容量、延迟、成本、物理索引布局与退出门禁 |
| 托管搜索主候选 | 提供 Elasticsearch 兼容的全文检索 | 阿里云 Elasticsearch 8.17 | 托管服务；具体 SKU、节点、分片、副本与参数待定 | `CONFIRMED_WITH_GATES` | BM25 Serving Projection | 第一阶段 PoC | 阿里云 OpenSearch 文本检索产品 | 现有 REST Adapter 已验证基本查询、过滤和 Release 隔离合同；旧 PoC 的 Dense Vector 与单引擎融合部分不再属于目标架构 | 完成真实实例 BM25 矩阵、写入型撤回/删除/回滚合同、容量成本与物理布局验证 |
| 托管搜索挑战者 | 提供阿里云托管文本检索能力 | 阿里云 OpenSearch，具体产品形态待定 | 产品版本、规格、表 Schema、Namespace 与拓扑待定 | `CHALLENGER_POC` | BM25 Serving Projection | 第一阶段 PoC | 阿里云 Elasticsearch 8.17 | 只比较文本召回、过滤、撤回、版本隔离、更新和成本，不再用其向量或原生 RRF 能力改变平台融合合同 | 与 Elasticsearch 使用同一 BM25 语料和门禁执行真实云实例 PoC，仅在质量、成本或运维存在明确优势时升级 |
| 自建搜索基准 | 验证托管产品的能力、成本和退出边界 | 开源 OpenSearch | ACK 自建；具体版本未定 | `BENCHMARK` | 非生产基准或托管产品硬门禁失败后的条件候选 | 第一阶段仅按需 PoC | 选择一个托管搜索产品 | 自建不应与托管候选拥有同等生产资格，但可帮助识别产品锁定或能力缺口 | 仅当托管产品存在明确硬缺口时升级为正式候选 |
| 中文 BM25 Analyzer 插件 | 为中文正文、标题和章节提供可配置分词，并保留英文、代码和标识符多字段 | Elasticsearch IK Analysis | 与阿里云 Elasticsearch 8.17 兼容的托管插件版本待真实实例确认；索引 `ik_max_word`、查询 `ik_smart` | `PRIMARY_POC` | Elasticsearch BM25 字段 | 第一阶段 PoC | `standard` + `keyword/whitespace` 多字段保守回退 | 企业术语和中文召回需要可控词典；项目词典、同义词和停用词必须随 Release 版本化，不能依赖全局热更新 | 核实托管插件版本、升级兼容、词典部署、重建行为，并与标准 Analyzer 做同语料质量和延迟对照 |
