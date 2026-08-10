from __future__ import annotations

from datetime import datetime, timezone, timedelta
import json
from pathlib import Path
from typing import Iterable

from .gates import HARD_GATES
from .matrix import select_chunk_challenger, select_embedding, select_reranker
from .runner import RunRecord


CHINA_STANDARD_TIME = timezone(timedelta(hours=8))


def write_reports(
    output_base: str | Path,
    *,
    records: Iterable[RunRecord],
    corpus_sha256: str,
    queries_sha256: str,
    execution_note: str,
) -> tuple[Path, Path]:
    records = list(records)
    base = Path(output_base)
    base.parent.mkdir(parents=True, exist_ok=True)
    generated_at = datetime.now(CHINA_STANDARD_TIME).isoformat(timespec="seconds")
    payload = {
        "report_schema_version": "1.1",
        "generated_at": generated_at,
        "evidence_boundary": _evidence_boundary(records),
        "dataset": {"corpus_sha256": corpus_sha256, "queries_sha256": queries_sha256},
        "execution_note": execution_note,
        "records": [record.to_dict() for record in records],
        "provisional_decision": _decision(records),
    }
    json_path = base.with_suffix(".json")
    markdown_path = base.with_suffix(".md")
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_path.write_text(_render_markdown(payload), encoding="utf-8")
    return markdown_path, json_path


def _evidence_boundary(records: list[RunRecord]) -> str:
    levels = {record.evidence_level.value for record in records}
    if levels == {"CLOUD_PRODUCT"}:
        return "CLOUD_PRODUCT: real provider APIs, configured product instances, and supplied evaluation corpus were exercised."
    if "CLOUD_PRODUCT" in levels:
        return "MIXED: only records explicitly marked CLOUD_PRODUCT are eligible for product conclusions."
    return "HARNESS_VALIDATION: deterministic local engine and synthetic or local fixture data only; this validates the harness contract, not production retrieval quality or cloud performance."


def _decision(records: list[RunRecord]) -> dict[str, object]:
    cloud_records = [record for record in records if record.evidence_level.value == "CLOUD_PRODUCT"]
    selected = _primary_stack_selected(cloud_records)
    status = "SELECTED" if selected else "CONFIRMED_WITH_GATES"
    return {
        "overall_status": status,
        "recommended_stack": [
            {
                "decision_ids": ["RET-001", "RET-002"],
                "choice": "阿里云 Elasticsearch 向量增强版 8.17",
                "status": status,
                "reason": "优先满足单引擎 BM25、Dense Vector、严格过滤、高亮、Release 隔离的 Staging/Active Projection 与原子 Alias 切换；PoC 独立 Release 索引不代表生产物理拓扑已冻结。",
            },
            {
                "decision_ids": ["RET-003"],
                "choice": "阿里云 OpenSearch 向量检索版",
                "status": "CHALLENGER_POC",
                "reason": "保留为同条件挑战者。其 SDK 已能表达文本、向量和 RRF 请求，但部署表 Schema、过滤表达式、撤回投影、写入删除和运行时能力仍须以真实实例关闭。",
            },
            {
                "decision_ids": ["RET-010"],
                "choice": "Elasticsearch IK Analysis；索引 ik_max_word、查询 ik_smart，并保留 standard/identifier 多字段",
                "status": "PRIMARY_POC",
                "reason": "中文与企业术语需要可控分词；插件版本、词典发布、升级兼容和相对标准 Analyzer 的质量收益仍须在真实 Elasticsearch 8.17 实例验证。",
            },
            {
                "decision_ids": ["MODEL-014"],
                "choice": "百炼 qwen3.7-text-embedding；1024 维 Dense、Cosine、L2 v1、float32、原生 Query/Document 角色",
                "status": status,
                "reason": "作为主候选；不可变模型 Revision、固定 Fast Offset Tokenizer 和完整空间指纹是生产硬门禁，任何变化均强制新 Release 重建。",
            },
            {
                "decision_ids": ["MODEL-026"],
                "choice": "百炼 text-embedding-v4，同输入合同、独立向量空间",
                "status": "CHALLENGER_POC",
                "reason": "只作同云质量、延迟和成本挑战者，不作为在线热备，也不与主候选混用。",
            },
            {
                "decision_ids": ["MODEL-015"],
                "choice": "百炼 qwen3-rerank；RRF Top 50 为降级路径",
                "status": status,
                "reason": "精排只作用于 RRF 后候选并输出 Top 10；故障时回退 RRF，不把 Rerank Score 当作 Grounding 置信度。",
            },
            {
                "decision_ids": ["MODEL-027"],
                "choice": "百炼 gte-rerank-v2",
                "status": "CHALLENGER_POC",
                "reason": "作为同云成熟基线，与 qwen3-rerank 使用完全相同的 RRF 候选和指标比较。",
            },
            {
                "decision_ids": ["MODEL-028"],
                "choice": "BAAI/bge-reranker-v2-m3 自托管",
                "status": "DEFERRED",
                "reason": "只有云端 Reranker 出现成本、容量、合规或稳定性硬缺口时，才与自托管推理运行时联合立项。",
            },
            {
                "decision_ids": ["GOV-007"],
                "choice": "不引入外部通用 Chunker；使用自有结构感知、分层且可回溯 Citation 的确定性 Chunker",
                "status": "REJECTED",
                "reason": "固定递归只作基准，Embedding Semantic Boundary 只作挑战者；生产仍需使用冻结的真实模型 Tokenizer 验证边界。",
            },
        ],
        "selection_condition": "只有真实企业语料、真实阿里云实例、真实百炼模型调用、质量/性能门槛和全部硬门禁均通过，才允许升级为 SELECTED。",
        "unclosed_gates": [
            "同一企业评测集上的 Recall@10 >= 90% 与 Top-3 有效 Evidence 比例 >= 85%。",
            "真实网络条件下 Search P95 <= 1 秒，已批准变更到可检索 P95 <= 5 分钟。",
            "真实实例中的跨 Project/Version/Locale/Access Segment 过滤、撤回、删除、幂等重放、Release 切换与回滚。",
            "Elasticsearch 8.17 中 IK 插件版本、项目词典/同义词随 Release 发布、Analyzer 升级和重建行为。",
            "Embedding 与 Reranker 的不可变 Provider Revision、固定 Tokenizer Artifact/Revision、漂移 Canary 和输入上限。",
            "阿里云地域、账号合同、日志/保留策略、配额、容量、成本与退出路径。",
        ],
    }


def _primary_stack_selected(records: list[RunRecord]) -> bool:
    eligible = [
        record
        for record in records
        if record.metrics is not None
        and record.error is None
        and record.hard_gates_passed
    ]
    phase_one_records = [record for record in eligible if record.candidate.phase == 1]
    if not _has_complete_primary_engine_comparison(
        phase_one_records,
        phase=1,
        variants=(
            ("qwen3_7_text_embedding", "structure_aware", "rrf_only"),
            ("text_embedding_v4", "structure_aware", "rrf_only"),
        ),
    ):
        return False
    try:
        winning_embedding = select_embedding(phase_one_records)
    except ValueError:
        return False
    if winning_embedding != "qwen3_7_text_embedding":
        return False

    structure_baseline = [
        record
        for record in phase_one_records
        if record.candidate.embedding == winning_embedding
    ]
    phase_two_records = [record for record in eligible if record.candidate.phase == 2]
    if not _has_complete_primary_engine_comparison(
        phase_two_records,
        phase=2,
        variants=(
            (winning_embedding, "structure_aware", "qwen3_rerank"),
            (winning_embedding, "structure_aware", "gte_rerank_v2"),
        ),
    ):
        return False
    if select_reranker(phase_two_records, structure_baseline) != "qwen3_rerank":
        return False

    phase_three_records = [record for record in eligible if record.candidate.phase == 3]
    if not _has_complete_primary_engine_comparison(
        phase_three_records,
        phase=3,
        variants=(
            (winning_embedding, "fixed_recursive", "rrf_only"),
            (winning_embedding, "semantic_boundary", "rrf_only"),
        ),
    ):
        return False
    winning_chunker = select_chunk_challenger(phase_three_records, structure_baseline)
    final_phase = 4 if winning_chunker else 2
    final_chunker = winning_chunker or "structure_aware"
    final_record = next(
        (
            record
            for record in eligible
            if record.candidate.phase == final_phase
            and record.candidate.engine == "aliyun_elasticsearch"
            and record.candidate.embedding == winning_embedding
            and record.candidate.chunker == final_chunker
            and record.candidate.reranker == "qwen3_rerank"
        ),
        None,
    )
    return bool(final_record and _meets_quality_and_latency(final_record))


def _has_complete_primary_engine_comparison(
    records: list[RunRecord],
    *,
    phase: int,
    variants: tuple[tuple[str, str, str], ...],
) -> bool:
    observed = {
        (record.candidate.embedding, record.candidate.chunker, record.candidate.reranker)
        for record in records
        if record.candidate.phase == phase
        and record.candidate.engine == "aliyun_elasticsearch"
    }
    return all(variant in observed for variant in variants)


def _meets_quality_and_latency(record: RunRecord) -> bool:
    metrics = record.metrics
    return bool(
        metrics
        and metrics.recall_at_10 >= 0.90
        and metrics.top3_valid_evidence_rate >= 0.85
        and metrics.search_p95_ms <= 1000.0
    )


def _render_markdown(payload: dict) -> str:
    lines = [
        "# 文本检索栈 PoC 报告",
        "",
        f"- 生成时间：`{payload['generated_at']}`",
        f"- 证据等级：{payload['evidence_boundary']}",
        f"- 语料 SHA-256：`{payload['dataset']['corpus_sha256']}`",
        f"- Query 集 SHA-256：`{payload['dataset']['queries_sha256']}`",
        f"- 执行说明：{payload['execution_note']}",
        "",
        "## 已执行配置",
        "",
        "| 配置 | 证据等级 | Recall@10 | NDCG@10 | MRR@10 | Top-3 有效 Evidence | Search P95 | 硬门禁 | 结果 |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for record in payload["records"]:
        candidate = record["candidate"]
        metrics = record["metrics"] or {}
        result = record["error"] or "passed"
        lines.append(
            "| {config} | {level} | {recall} | {ndcg} | {mrr} | {hit3} | {p95} ms | {gates} | {result} |".format(
                config=f"`{candidate['configuration_id']}`",
                level=record["evidence_level"],
                recall=_percent(metrics.get("recall_at_10")),
                ndcg=_percent(metrics.get("ndcg_at_10")),
                mrr=_percent(metrics.get("mrr_at_10")),
                hit3=_percent(metrics.get("top3_valid_evidence_rate")),
                p95=_number(metrics.get("search_p95_ms")),
                gates="PASS" if record["hard_gates_passed"] else "NOT_PRODUCT_VALIDATED",
                result=_escape_cell(str(result)),
            )
        )
    decision = payload["provisional_decision"]
    lines.extend(
        [
            "",
            "## 决策",
            "",
            f"当前结论：`{decision['overall_status']}`。这不是对技术选型正文的状态修改；它是本轮 PoC 的可追溯结论。",
            "",
            "| 决策对象 | 暂定选择 | 状态 | 判断 |",
            "| --- | --- | --- | --- |",
        ]
    )
    for recommendation in decision["recommended_stack"]:
        lines.append(
            f"| {', '.join(recommendation['decision_ids'])} | {recommendation['choice']} | `{recommendation['status']}` | {recommendation['reason']} |"
        )
    lines.extend(
        [
            "",
            "选择升级条件：" + decision["selection_condition"],
            "",
            "## 未关闭门禁",
            "",
        ]
    )
    for gate in decision["unclosed_gates"]:
        lines.append(f"- {gate}")
    lines.extend(
        [
            "",
            "## 本地合同范围",
            "",
            "以下项目由本地确定性合同夹具覆盖，覆盖结果只证明 harness 的行为，不证明云产品：",
            "",
        ]
    )
    for gate in HARD_GATES:
        lines.append(f"- `{gate}`")
    lines.extend(
        [
            "",
            "本报告没有把本地 Hash Embedding、合成夹具或未配置的云端 adapter 伪装成百炼或托管搜索结果。",
            "",
        ]
    )
    return "\n".join(lines)


def _percent(value: float | None) -> str:
    return "-" if value is None else f"{value * 100:.1f}%"


def _number(value: float | None) -> str:
    return "-" if value is None else f"{value:.2f}"


def _escape_cell(value: str) -> str:
    return value.replace("|", "\\|").replace("\n", " ")
