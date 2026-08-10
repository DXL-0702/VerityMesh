from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any

from .data import file_sha256, load_documents, load_queries
from .cloud_gates import run_cloud_contract_gates
from .domain import EvidenceLevel
from .embeddings import DashScopeEmbeddingAdapter, DashScopeEmbeddingConfig
from .engines.aliyun_opensearch import AliyunOpenSearchVectorEngine, OpenSearchVectorConfig
from .engines.elasticsearch import ElasticsearchConfig, ElasticsearchRestEngine
from .gates import GateResult
from .matrix import (
    RERANKER_CANDIDATES,
    phase_four,
    phase_one,
    phase_three,
    phase_two,
    planned_matrix,
    select_chunk_challenger,
    select_embedding,
    select_reranker,
)
from .report import write_reports
from .rerankers import DashScopeReranker, DashScopeRerankerConfig
from .runner import execute_candidate, run_local_validation
from .tokenization import HuggingFaceOffsetTokenizer


HARNESS_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_FIXTURE_DIR = HARNESS_ROOT / "fixtures" / "harness-validation"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="veritymesh-retrieval-poc")
    commands = parser.add_subparsers(dest="command", required=True)

    plan_parser = commands.add_parser("plan", help="render the agreed staged joint matrix")
    plan_parser.add_argument("--winning-embedding", choices=("qwen3_7_text_embedding", "text_embedding_v4"))
    plan_parser.add_argument("--winning-chunker", choices=("fixed_recursive", "semantic_boundary"))
    plan_parser.add_argument("--winning-reranker", choices=RERANKER_CANDIDATES)

    local_parser = commands.add_parser("local-validate", help="run deterministic harness and contract validation")
    local_parser.add_argument("--corpus", type=Path, default=DEFAULT_FIXTURE_DIR / "corpus.jsonl")
    local_parser.add_argument("--queries", type=Path, default=DEFAULT_FIXTURE_DIR / "queries.jsonl")
    local_parser.add_argument("--output", type=Path, required=True, help="report path without .md/.json suffix")

    cloud_parser = commands.add_parser("cloud-matrix", help="run the cloud candidate matrix from a credential-free JSON config")
    cloud_parser.add_argument("--config", type=Path, required=True)
    cloud_parser.add_argument("--output", type=Path, help="override report output path without .md/.json suffix")
    cloud_parser.add_argument(
        "--allow-cloud-mutations",
        action="store_true",
        help="run isolated write/revoke/delete/rollback gates and clean generated PoC data",
    )

    environment_parser = commands.add_parser("check-env", help="report missing cloud configuration variables without printing their values")
    environment_parser.add_argument("--config", type=Path, required=True)

    args = parser.parse_args(argv)
    if args.command == "plan":
        print(
            json.dumps(
                [
                    candidate.to_dict()
                    for candidate in planned_matrix(
                        args.winning_embedding,
                        args.winning_chunker,
                        args.winning_reranker,
                    )
                ],
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0
    if args.command == "local-validate":
        return _run_local(args)
    if args.command == "cloud-matrix":
        return _run_cloud(args)
    if args.command == "check-env":
        return _check_environment(args.config)
    raise AssertionError(f"unknown command: {args.command}")


def _run_local(args: argparse.Namespace) -> int:
    documents = load_documents(args.corpus)
    queries = load_queries(args.queries)
    records = run_local_validation(documents, queries)
    markdown, raw = write_reports(
        args.output,
        records=records,
        corpus_sha256=file_sha256(args.corpus),
        queries_sha256=file_sha256(args.queries),
        execution_note="本地 Unicode Regex Tokenizer、确定性 Hash Embedding 和内存检索引擎。仅用于验证数据契约、算法编排、Citation 与硬门禁 harness。",
    )
    print(json.dumps({"markdown_report": str(markdown), "raw_report": str(raw), "successful_records": sum(record.error is None for record in records)}, ensure_ascii=False))
    return 0 if all(record.error is None for record in records) else 1


def _run_cloud(args: argparse.Namespace) -> int:
    settings = _load_config(args.config)
    documents = load_documents(_path_value(settings, "corpus", args.config.parent))
    queries = load_queries(_path_value(settings, "queries", args.config.parent))
    records = []
    try:
        cloud_tokenizer = _build_tokenizer(settings)
        tokenizer_error = None
    except Exception as error:
        cloud_tokenizer = None
        tokenizer_error = f"tokenizer configuration error: {type(error).__name__}: {error}"
    not_executed_gates = tuple(
        GateResult(gate, False, "cloud hard-gate mutation suite is not enabled by this command")
        for gate in (
            "scope_isolation",
            "revocation_exclusion",
            "citation_round_trip",
            "embedding_space_compatibility",
            "release_atomic_switch_and_rollback",
            "update_delete_replay_idempotency",
            "approved_change_visibility_p95",
            "revocation_visibility_p95",
        )
    )
    gates_by_engine = {name: not_executed_gates for name in ("aliyun_elasticsearch", "aliyun_opensearch_vector")}
    if args.allow_cloud_mutations:
        for engine_name in gates_by_engine:
            try:
                if tokenizer_error:
                    raise ValueError(tokenizer_error)
                gate_engine = _build_engine(engine_name, settings)
                gate_embedder = _build_embedder(
                    "qwen3_7_text_embedding",
                    settings,
                    tokenizer=cloud_tokenizer,
                )
                gates_by_engine[engine_name] = tuple(
                    run_cloud_contract_gates(
                        gate_engine,
                        gate_embedder,
                        operational_repetitions=int(settings.get("cloud_gate_repetitions", 20)),
                        tokenizer=cloud_tokenizer,
                    )
                )
            except Exception as error:
                gates_by_engine[engine_name] = tuple(
                    GateResult(gate.gate, False, f"cloud gate setup failed: {type(error).__name__}: {error}")
                    for gate in not_executed_gates
                )

    def run(candidate):
        try:
            if tokenizer_error:
                raise ValueError(tokenizer_error)
            engine = _build_engine(candidate.engine, settings)
            embedder = _build_embedder(candidate.embedding, settings, tokenizer=cloud_tokenizer)
            reranker = _build_reranker(candidate.reranker, settings, tokenizer=cloud_tokenizer)
        except Exception as error:
            from .runner import RunRecord

            return RunRecord(
                candidate=candidate,
                evidence_level=EvidenceLevel.CLOUD_PRODUCT,
                metrics=None,
                measurements=(),
                indexed_document_count=0,
                indexed_chunk_count=0,
                embedding_space_fingerprint=None,
                reranker_version=None,
                tokenizer_fingerprint=None,
                gate_results=gates_by_engine[candidate.engine],
                error=f"configuration error: {type(error).__name__}: {error}",
            )
        return execute_candidate(
            candidate=candidate,
            documents=documents,
            queries=queries,
            engine=engine,
            embedder=embedder,
            reranker=reranker,
            evidence_level=EvidenceLevel.CLOUD_PRODUCT,
            gate_results=gates_by_engine[candidate.engine],
            tokenizer=cloud_tokenizer,
        )

    first = [run(candidate) for candidate in phase_one()]
    records.extend(first)
    successful_first = [record for record in first if record.metrics is not None and record.error is None]
    if successful_first:
        winning_embedding = select_embedding(successful_first)
        second = [run(candidate) for candidate in phase_two(winning_embedding)]
        third = [run(candidate) for candidate in phase_three(winning_embedding)]
        records.extend(second)
        records.extend(third)
        successful_second = [record for record in second if record.metrics is not None and record.error is None]
        structure_baseline = [
            record
            for record in first
            if record.candidate.embedding == winning_embedding
            and record.metrics is not None
            and record.error is None
        ]
        winning_chunker = select_chunk_challenger(third, structure_baseline)
        winning_reranker = select_reranker(successful_second, structure_baseline)
        if winning_chunker and winning_reranker:
            records.extend(
                run(candidate)
                for candidate in phase_four(winning_embedding, winning_chunker, winning_reranker)
            )

    output = args.output or _path_value(settings, "output", args.config.parent)
    markdown, raw = write_reports(
        output,
        records=records,
        corpus_sha256=file_sha256(_path_value(settings, "corpus", args.config.parent)),
        queries_sha256=file_sha256(_path_value(settings, "queries", args.config.parent)),
        execution_note=(
            "云矩阵调用已配置的产品实例与百炼 API，并执行隔离写入、撤回、删除、Release 切换/回滚及清理。"
            if args.allow_cloud_mutations
            else "云矩阵调用已配置的产品实例与百炼 API；本次未启用写入型云端硬门禁，因此报告不会升级为 SELECTED。"
        ),
    )
    print(json.dumps({"markdown_report": str(markdown), "raw_report": str(raw), "successful_records": sum(record.error is None for record in records)}, ensure_ascii=False))
    return 0 if records and all(record.error is None for record in records) else 1


def _check_environment(config_path: Path) -> int:
    settings = _load_config(config_path)
    missing: list[str] = []
    invalid_config: list[str] = []
    for group_name in ("engines", "embeddings", "rerankers"):
        for _, definition in (settings.get(group_name) or {}).items():
            if not isinstance(definition, dict):
                continue
            for key, value in definition.items():
                if key.endswith("_env") and isinstance(value, str) and not os.environ.get(value):
                    missing.append(value)
    for group, kind in (("embeddings", "embedding"), ("rerankers", "reranker")):
        for name, definition in (settings.get(group) or {}).items():
            if not isinstance(definition, dict):
                continue
            try:
                resolved = _resolve_environment(definition)
                _pinned_revision(resolved, kind)
                if group == "embeddings":
                    _validate_embedding_contract(resolved)
                else:
                    _validate_reranker_contract(resolved)
            except ValueError as error:
                invalid_config.append(f"{group}.{name}: {error}")
    for name, definition in (settings.get("engines") or {}).items():
        if name != "aliyun_elasticsearch" or not isinstance(definition, dict):
            continue
        try:
            _validate_elasticsearch_contract(_resolve_environment(definition))
        except ValueError as error:
            invalid_config.append(f"engines.{name}: {error}")
    try:
        _build_tokenizer(settings)
    except Exception as error:
        invalid_config.append(f"tokenizer: {type(error).__name__}: {error}")
    ready = not missing and not invalid_config
    print(
        json.dumps(
            {
                "missing_environment_variables": sorted(set(missing)),
                "invalid_config": invalid_config,
                "ready": ready,
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0 if ready else 2


def _load_config(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise SystemExit(f"config does not exist: {path}") from error
    except json.JSONDecodeError as error:
        raise SystemExit(f"config is not valid JSON: {path}: {error}") from error
    if not isinstance(value, dict):
        raise SystemExit("config root must be a JSON object")
    return value


def _build_engine(name: str, settings: dict[str, Any]):
    definition = _named_definition(settings, "engines", name)
    if name == "aliyun_elasticsearch":
        _validate_elasticsearch_contract(definition)
        return ElasticsearchRestEngine(
            ElasticsearchConfig(
                endpoint=_required(definition, "endpoint"),
                index_prefix=str(definition.get("index_prefix", "veritymesh-poc")),
                username=_optional(definition, "username"),
                password=_optional(definition, "password"),
                api_key=_optional(definition, "api_key"),
                timeout_seconds=float(definition.get("timeout_seconds", 30.0)),
                verify_tls=bool(definition.get("verify_tls", True)),
                index_analyzer=str(definition.get("index_analyzer", "ik_max_word")),
                search_analyzer=str(definition.get("search_analyzer", "ik_smart")),
                analysis_profile_version=str(definition.get("analysis_profile_version", "bm25-multifield-ik-v1")),
                dictionary_fingerprint=str(definition.get("dictionary_fingerprint", "none")),
                synonym_fingerprint=str(definition.get("synonym_fingerprint", "none")),
            )
        )
    if name == "aliyun_opensearch_vector":
        return AliyunOpenSearchVectorEngine(
            OpenSearchVectorConfig(
                endpoint=_required(definition, "endpoint"),
                instance_id=_required(definition, "instance_id"),
                access_user_name=_required(definition, "access_user_name"),
                access_pass_word=_required(definition, "access_pass_word"),
                data_source_name=_required(definition, "data_source_name"),
                table_name=_required(definition, "table_name"),
                key_field=str(definition.get("key_field", "chunk_id")),
                vector_field=str(definition.get("vector_field", "vector")),
                namespace=str(definition.get("namespace", "default")),
                timeout_seconds=float(definition.get("timeout_seconds", 30.0)),
            )
        )
    raise ValueError(f"no engine factory for {name}")


def _build_embedder(name: str, settings: dict[str, Any], *, tokenizer):
    definition = _named_definition(settings, "embeddings", name)
    revision = _pinned_revision(definition, "embedding")
    _validate_embedding_contract(definition)
    return DashScopeEmbeddingAdapter(
        DashScopeEmbeddingConfig(
            model=_required(definition, "model"),
            dimension=int(definition.get("dimension", 1024)),
            region=str(definition.get("region", "cn-beijing")),
            api_key_env=str(definition.get("api_key_env", "DASHSCOPE_API_KEY")),
            endpoint=str(definition.get("endpoint", DashScopeEmbeddingConfig.endpoint)),
            api_mode=str(definition.get("api_mode", "native")),
            batch_size=int(definition.get("batch_size", 16)),
            timeout_seconds=float(definition.get("timeout_seconds", 30.0)),
            revision=revision,
            query_instruction=str(definition.get("query_instruction", "")),
            document_instruction=str(definition.get("document_instruction", "")),
            query_max_tokens=int(definition.get("query_max_tokens", 512)),
            document_max_tokens=int(definition.get("document_max_tokens", 1024)),
        ),
        tokenizer=tokenizer,
    )


def _build_reranker(name: str, settings: dict[str, Any], *, tokenizer):
    if name == "rrf_only":
        from .rerankers import RRFOnlyReranker

        return RRFOnlyReranker()
    if name in RERANKER_CANDIDATES:
        definition = _named_definition(settings, "rerankers", name)
        revision = _pinned_revision(definition, "reranker")
        _validate_reranker_contract(definition)
        return DashScopeReranker(
            DashScopeRerankerConfig(
                model=_required(definition, "model"),
                revision=revision,
                region=str(definition.get("region", "cn-beijing")),
                api_key_env=str(definition.get("api_key_env", "DASHSCOPE_API_KEY")),
                endpoint=str(definition.get("endpoint", DashScopeRerankerConfig.endpoint)),
                api_mode=str(definition.get("api_mode", "native")),
                timeout_seconds=float(definition.get("timeout_seconds", 1.0)),
                query_max_tokens=int(definition.get("query_max_tokens", 512)),
                document_max_tokens=int(definition.get("document_max_tokens", 1024)),
                max_documents=int(definition.get("max_documents", 50)),
            ),
            tokenizer=tokenizer,
        )
    raise ValueError(f"no reranker factory for {name}")


def _build_tokenizer(settings: dict[str, Any]):
    definition = settings.get("tokenizer")
    if not isinstance(definition, dict):
        raise ValueError("missing tokenizer config")
    if definition.get("type") != "huggingface":
        raise ValueError("cloud matrix tokenizer.type must be 'huggingface'")
    revision = _pinned_revision(definition, "tokenizer")
    return HuggingFaceOffsetTokenizer(
        _required(definition, "pretrained_name_or_path"),
        revision=revision,
        local_files_only=bool(definition.get("local_files_only", True)),
        trust_remote_code=bool(definition.get("trust_remote_code", False)),
    )


def _named_definition(settings: dict[str, Any], group: str, name: str) -> dict[str, Any]:
    definitions = settings.get(group)
    if not isinstance(definitions, dict) or not isinstance(definitions.get(name), dict):
        raise ValueError(f"missing {group}.{name} in cloud config")
    return _resolve_environment(definitions[name])


def _resolve_environment(definition: dict[str, Any]) -> dict[str, Any]:
    resolved = dict(definition)
    for key, value in list(definition.items()):
        if key.endswith("_env") and key != "api_key_env":
            target = key[: -len("_env")]
            if isinstance(value, str):
                resolved[target] = os.environ.get(value)
    return resolved


def _required(definition: dict[str, Any], key: str) -> str:
    value = definition.get(key)
    if value is None or value == "":
        raise ValueError(f"missing required config value: {key}")
    return str(value)


def _optional(definition: dict[str, Any], key: str) -> str | None:
    value = definition.get(key)
    return None if value is None or value == "" else str(value)


def _pinned_revision(definition: dict[str, Any], kind: str) -> str:
    revision = _required(definition, "revision")
    if revision.lower() in {"configured", "pin-at-run-time", "latest", "default"}:
        raise ValueError(f"{kind} revision must be a real immutable provider version, not {revision!r}")
    return revision


def _validate_embedding_contract(definition: dict[str, Any]) -> None:
    expected = {
        "dimension": 1024,
        "api_mode": "native",
        "query_instruction": "",
        "document_instruction": "",
        "query_max_tokens": 512,
        "document_max_tokens": 1024,
    }
    for key, value in expected.items():
        actual = definition.get(key, value)
        if actual != value:
            raise ValueError(f"embedding contract requires {key}={value!r}, got {actual!r}")


def _validate_reranker_contract(definition: dict[str, Any]) -> None:
    expected = {
        "api_mode": "native",
        "query_max_tokens": 512,
        "document_max_tokens": 1024,
        "max_documents": 50,
    }
    for key, value in expected.items():
        actual = definition.get(key, value)
        if actual != value:
            raise ValueError(f"reranker contract requires {key}={value!r}, got {actual!r}")


def _validate_elasticsearch_contract(definition: dict[str, Any]) -> None:
    profile = (
        str(definition.get("index_analyzer", "ik_max_word")),
        str(definition.get("search_analyzer", "ik_smart")),
        str(definition.get("analysis_profile_version", "bm25-multifield-ik-v1")),
    )
    allowed_profiles = {
        ("ik_max_word", "ik_smart", "bm25-multifield-ik-v1"),
        ("standard", "standard", "bm25-multifield-standard-benchmark-v1"),
    }
    if profile not in allowed_profiles:
        raise ValueError(
            "Elasticsearch analysis profile must be the IK primary or explicit standard benchmark contract"
        )
    for key in ("dictionary_fingerprint", "synonym_fingerprint"):
        value = str(definition.get(key, "none"))
        if value != "none" and re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise ValueError(f"{key} must be 'none' or a lowercase SHA-256 fingerprint")
        if profile[2] == "bm25-multifield-standard-benchmark-v1" and value != "none":
            raise ValueError(f"{key} must be 'none' for the standard Analyzer benchmark")


def _path_value(settings: dict[str, Any], key: str, base: Path) -> Path:
    value = settings.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing required path config value: {key}")
    path = Path(value)
    return path if path.is_absolute() else base / path
