# VerityMesh 文本检索栈 PoC

> 架构状态：本 Harness 在 2026-08-10 按 Elasticsearch/OpenSearch 单引擎文本+向量候选构建。2026-08-11 的 [`ADR-003`](../../docs/adr/0003-mysql-authority-and-pgvector-retrieval-projection.md) 已将目标链路冻结为 Elasticsearch BM25 + PostgreSQL/pgvector Vector。`local-validate` 的 RRF、Citation、过滤和降级合同仍有效；现有 `cloud-matrix` 与 Vector Adapter 只用于复现历史证据，在加入 pgvector Adapter、拆分 BM25/Vector Engine 和 Joint Projection Gate 前，不得关闭当前生产选型门禁。

这是 `RET-001`、`RET-002`、`RET-003`、`MODEL-014`、`MODEL-015` 与 `GOV-007` 的可重复评测 harness。它验证首期链路：

```text
可引用 Document JSONL
  -> Structure-aware / Fixed-recursive / Semantic-boundary Chunk
  -> Embedding
  -> BM25 Top 50 + Dense Vector Top 50
  -> RRF Top 50
  -> qwen3-rerank / gte-rerank-v2 Top 10，或 RRF-only 降级
  -> Citation、指标、硬门禁报告
```

这不是产品运行时，也不是 `docs/tech-plan.md` 的替代事实源。PoC 数据与结论写入 `docs/poc-reports/`；技术选型状态仍只由 `docs/technology-selection/` 维护。

## 已编码边界

| 项目 | 当前 PoC 约束 |
| --- | --- |
| 引擎 | 当前实现保留阿里云 Elasticsearch 向量增强版 8.17 与阿里云 OpenSearch 向量检索版的历史矩阵；目标架构所需 Elasticsearch BM25 + PostgreSQL/pgvector 联合矩阵尚待实现 |
| BM25 | Elasticsearch IK Analysis 主候选；`ik_max_word` 索引、`ik_smart` 查询，并保留 `standard` 与 identifier 多字段 |
| Embedding | `qwen3.7-text-embedding` 主候选、`text-embedding-v4` 挑战者；统一 1024 维、Dense、Cosine、平台 L2 v1、float32、原生 Query/Document 角色和空自定义指令 |
| Reranker | `qwen3-rerank` 主候选、`gte-rerank-v2` 同云挑战者；故障路径为 RRF-only |
| Chunk | 结构感知为主方案；固定递归和 Embedding 辅助语义边界为挑战者 |
| 排除项 | 不在首轮引入 GraphRAG、Milvus、Weaviate、多模态 Embedding 或检索框架编排 |

Harness 不依赖 LangChain。检索的 Project/Release/Locale/Access Segment 过滤、Citation 范围、Embedding 空间指纹和降级行为是确定性平台契约，不应被 Agent 链式封装吞掉。后续 Global Router 或 Planner 可以在独立 Agent Runtime 中使用需要的编排库，但不拥有本目录的检索安全边界。

运行时允许 Embedding/Vector 分支失败后继续使用 BM25，并允许 Reranker Provider 失败后回退 RRF；云候选矩阵会关闭这些降级包装，让候选错误直接记入报告，避免把降级结果误报成模型质量。

## 联合矩阵

| 阶段 | 配置数 | 内容 |
| --- | ---: | --- |
| 0 | 本地 4 条 | 只验证数据契约、算法编排和报告，不产生产品质量结论 |
| 1 | 4 条 | 2 引擎 x 2 Embedding x Structure-aware x RRF-only |
| 2 | 4 条 | 2 引擎 x 阶段 1 胜出 Embedding x 2 Reranker |
| 3 | 4 条 | 2 引擎 x 胜出 Embedding x 2 Chunk Challenger x RRF-only |
| 4 | 0 或 2 条 | 只有 Chunk Challenger 胜出时，使用阶段 2 胜出 Reranker 最终确认 |

云端核心矩阵是 12 至 14 条，而不是盲目全排列。阶段 1 先选择 Embedding；阶段 2 在胜出 Embedding 上比较两个 Reranker；阶段 3 比较 Chunk Challenger；阶段 4 只在 Chunk 与 Reranker 相对 Structure-aware/RRF-only 基线至少提升 1 个百分点且关键指标不回退时运行。候选全部不达标时保留现有基线，不强行宣布胜者。

## 输入契约

语料和 Query 集均为 UTF-8 JSONL，一行一个对象。输入的 SHA-256 会写入机器可读 JSON 和 Markdown 报告。

`corpus.jsonl` 的必填字段：

```text
document_id
knowledge_revision_id
project_id
project_version
locale
access_segment
knowledge_release_id
knowledge_space_id
citation_url
title
text
```

可选字段是 `document_type`、`effective_from`、`effective_to`、`metadata`。`document_type` 支持 `prose`、`faq`、`api`、`release_notes`、`policy`、`table` 和 `code`，每种类型都有独立 Chunk Profile。

`queries.jsonl` 的必填字段：

```text
query_id
text
project_id
project_version
locale
allowed_access_segments
knowledge_release_id
relevant_documents
```

`relevant_documents` 可以是 Document ID 数组，或 `{ "document_id": relevance_grade }` 对象。评测按 Document 去重，避免一个文档的多个 Chunk 伪造 Recall 或 MRR。

## 本地验证

下面的命令只运行合成夹具和内存引擎。它覆盖 Citation 范围、Project/Version/Locale/Access Segment 隔离、撤回、删除、向量空间混用、Release 切换/回滚和幂等重放。

```sh
PYTHONDONTWRITEBYTECODE=1 python3 tools/text-retrieval-poc/run_poc.py local-validate \
  --output docs/poc-reports/text-retrieval-poc-local-contract-2026-08-10

PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=src python3 -m unittest discover -s tests -v
```

第二条命令在 `tools/text-retrieval-poc/` 下运行。`fixtures/harness-validation/` 专门标记为 harness validation，不能替代企业评测语料。

## 云端运行

`config.example.json` 不含凭据。真实、已审批的评测集路径与环境变量就绪后，先检查缺失项，再运行矩阵：

```sh
python3 tools/text-retrieval-poc/run_poc.py check-env --config /absolute/path/to/poc-config.json
python3 tools/text-retrieval-poc/run_poc.py cloud-matrix --config /absolute/path/to/poc-config.json
python3 tools/text-retrieval-poc/run_poc.py cloud-matrix --config /absolute/path/to/poc-config.json --allow-cloud-mutations
```

Embedding 与 Reranker 的 `revision` 必须填写供应商可追溯的固定版本；`latest`、`default`、`configured` 和示例中的 `pin-at-run-time` 都会被预检拒绝。Embedding Provider、Region、API Mode、模型 Revision、Tokenizer 指纹、L2 归一化、Query/Document 角色、指令与截断策略共同进入向量空间指纹。

云矩阵同样要求一个冻结 revision、支持 offset mapping 的 Hugging Face fast tokenizer。Tokenizer 的实际序列化内容会参与 SHA-256 指纹并写入每条原始结果；`local_files_only=true`、`trust_remote_code=false`。Document Embedding 输入上限 1024 tokens、Chunk 正文硬上限 800 tokens、Query 上限 512 tokens，任何 Provider 静默截断均违反合同。本地 Unicode Regex Tokenizer 只允许产生 `HARNESS_VALIDATION` 证据。

需要的环境变量至少包括：

```text
DASHSCOPE_API_KEY
VERITYMESH_ES_ENDPOINT
VERITYMESH_ES_USERNAME / VERITYMESH_ES_PASSWORD 或 API Key 配置
VERITYMESH_OPENSEARCH_ENDPOINT
VERITYMESH_OPENSEARCH_INSTANCE_ID
VERITYMESH_OPENSEARCH_USERNAME
VERITYMESH_OPENSEARCH_PASSWORD
VERITYMESH_OPENSEARCH_DATA_SOURCE
VERITYMESH_OPENSEARCH_TABLE
```

OpenSearch Vector adapter 使用官方 `alibabacloud-ha3engine-vector` SDK。若运行环境未安装它，使用项目的可选依赖安装；本地合同验证不需要该依赖。

```sh
python3 -m pip install '.[aliyun-opensearch]'
```

### 云表 / 索引契约

两种候选都必须保存以下投影字段，不能只保存向量：

```text
chunk_id, chunker_version, document_id, knowledge_revision_id
project_id, project_version, locale, access_segment
knowledge_release_id, knowledge_space_id
citation_url, title, section, text, search_text
start_char, end_char, effective_from, effective_to
revoked, embedding_space_fingerprint, configuration_id
vector (1024-dimension dense vector)
```

Elasticsearch adapter 为每个 `configuration_id + knowledge_release_id` 创建独立 PoC 索引，并提供 `_aliases` 原子切换方法。该布局只用于验证 Release 隔离、激活和回滚合同；生产采用完整版本索引、Delta Segment 还是分区索引仍由容量 PoC 决定。OpenSearch Vector adapter 把 `knowledge_release_id`、`configuration_id`、撤回状态与访问字段写入表，并将同样的筛选条件放入文本、向量和原生 RRF 请求。`namespace` 必须按已创建的 OpenSearch 表实际 namespace 冻结，示例中的 `default` 只是默认值。

Elasticsearch PoC Mapping 使用 IK 主字段、`standard` 多字段和 identifier 多字段；标题、章节与正文使用不同权重执行 `multi_match`。Analyzer Profile、项目词典和同义词指纹写入 Mapping `_meta`。真实实例必须证明 IK 插件版本与 Elasticsearch 8.17 兼容，且词典或同义词变化通过新 Release 重建，不能全局热更新旧索引。

IK 的同引擎基准通过第二份配置运行：把 Elasticsearch 的 `index_analyzer` 与 `search_analyzer` 均设为 `standard`，把 `analysis_profile_version` 设为 `bm25-multifield-standard-benchmark-v1`，词典和同义词指纹均设为 `none`，并使用独立报告输出路径。Harness 会把 Analyzer Profile 指纹写入 PoC 索引名和 Mapping `_meta`，避免两个 Profile 复用同一索引；标准 Profile 只作 `BENCHMARK`，不能替代默认 IK 主候选。

云矩阵默认不执行写入型撤回/删除/回滚 mutation suite，因此即使质量指标通过也保持 `CONFIRMED_WITH_GATES`。只有在隔离 PoC 实例、Index Prefix 或表写入策略已经确认时才传 `--allow-cloud-mutations`；该模式使用随机 Project/Release/Configuration 写入合同夹具，并在结束时清理生成数据。

## 硬门禁与报告

以下项任一失败即淘汰，不参与平均分：

- Project、Version、Locale 或 Access Segment 越权。
- 已撤回 Evidence 被召回。
- Citation 不能回到原始范围。
- Query/Document 混用不兼容 Embedding 空间。
- Release 切换混用版本，或不能回滚。
- 更新、删除、重放不幂等。
- 已批准变更到可检索 P95 超过 5 分钟。
- 紧急撤回到不可召回 P95 超过 60 秒。

报告同时输出 `.md` 和 `.json`。只有明确标记为 `CLOUD_PRODUCT`，并同时满足 `Recall@10 >= 90%`、Top-3 有效 Evidence 比例 `>= 85%`、`Search P95 <= 1s` 与所有硬门禁的记录，才允许选型报告升级为 `SELECTED`。
