# Embedding 模型选型

| 外部依赖类型 | 主要职责 | 当前选择 | 形态/版本 | 状态 | 使用位置 | 引入阶段 | 备选/回退 | 选型依据 | 下一决策 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 文档与查询 Embedding 主候选 | 为 Published Knowledge Chunk 和用户查询生成主向量空间 | 百炼 `qwen3.7-text-embedding` | 云 API；`1024` 维 Dense、Cosine、平台 `L2 normalization v1`、float32；原生 `text_type=query/document`、空自定义指令；固定 Fast Offset Tokenizer；Document 输入 `1024`、Chunk 正文 `800`、Query `512` tokens；禁止静默截断；不可变模型 Revision 为生产硬门禁 | `CONFIRMED_WITH_GATES` | 离线索引构建与在线 Vector Recall | M3 | 在线不可用、Revision 不匹配或 Query 超限无法拆分时降级 BM25；不使用其他 Embedding 即时热切换 | 滚动 Alias、`latest`、`default` 或无法证明底层版本的模型不得承载正式空间；Provider、Region、API Mode、模型与 Tokenizer Revision、向量及预处理参数共同形成空间指纹，任何变化必须新建 Release 投影 | 从真实 Provider 固定不可变模型 Revision 与 Tokenizer Artifact/Revision，完成联合矩阵、漂移 Canary、迁移和回滚门禁 |
| 同云 Embedding 挑战者 | 建立主候选的成熟同云质量、延迟和成本基线 | 百炼 `text-embedding-v4` | 云 API；与主候选采用相同输入合同；独立向量空间；不可变模型 Revision 同样是生产资格前提 | `CHALLENGER_POC` | 离线联合评测，不作为在线热备 | M3 PoC | `qwen3.7-text-embedding` 主候选；生产故障时降级 BM25 | 即使输入合同相同也不能与主候选混用；若无法固定模型 Revision，只能保留评测资格，不能升级为生产选择 | 固定独立 Revision，与主候选执行同条件质量、延迟、成本、漂移和重建窗口评测，仅在明确胜出时升级 |
