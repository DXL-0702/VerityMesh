from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from hashlib import sha256
import math
import time
from typing import Any, Callable
from uuid import uuid4

from .chunking import StructureAwareChunker
from .domain import ContractError, Document, IndexedChunk, SearchScope
from .embeddings import EmbeddingAdapter
from .engines.aliyun_opensearch import AliyunOpenSearchVectorEngine
from .engines.elasticsearch import ElasticsearchRestEngine
from .gates import GateResult
from .retrieval import BindingKey, ReleaseRouter, ServingEngine
from .tokenization import OffsetTokenizer, UnicodeRegexTokenizer


def run_cloud_contract_gates(
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    *,
    operational_repetitions: int = 20,
    tokenizer: OffsetTokenizer | None = None,
) -> list[GateResult]:
    """Run mutating safety gates in a caller-authorized, uniquely named PoC scope.

    The caller must use a non-production PoC prefix/table policy. This function deliberately
    uses product operations rather than pretending that local contract tests prove cloud behavior.
    """

    nonce = uuid4().hex[:12]
    tokenizer = tokenizer or UnicodeRegexTokenizer()
    project_id = f"poc-contract-{nonce}"
    configuration_id = f"contract-{nonce}"
    release_one = f"release-{nonce}-r1"
    release_two = f"release-{nonce}-r2"
    documents = _fixture_documents(project_id, release_one, release_two, nonce)
    items_by_document = _index_items(documents, embedder, configuration_id, tokenizer)
    staged: list[IndexedChunk] = []
    try:
        baseline_groups = [values for name, values in items_by_document.items() if name != "mismatch"]
        staged = [item for values in baseline_groups for item in values]
        _stage_by_release(engine, baseline_groups, nonce)
        scope_one = _scope(project_id, release_one, configuration_id)
        scope_two = _scope(project_id, release_two, configuration_id)
        results = [
            _run("scope_isolation", lambda: _check_scope(engine, scope_one, nonce)),
            _run("citation_round_trip", lambda: _check_citation(engine, scope_one, documents["public"], nonce)),
            _run("embedding_space_compatibility", lambda: _check_embedding_space(engine, embedder, scope_one, items_by_document, nonce)),
            _run("release_atomic_switch_and_rollback", lambda: _check_release_switch(engine, scope_one, scope_two, configuration_id, nonce)),
            _run("revocation_exclusion", lambda: _check_revocation(engine, embedder, scope_one, items_by_document["revoked"], configuration_id, release_one, nonce)),
            _run("update_delete_replay_idempotency", lambda: _check_delete_and_replay(engine, embedder, scope_one, items_by_document, configuration_id, release_one, nonce)),
        ]
        results.extend(
            _run_operational_slo_gates(
                engine,
                embedder,
                project_id=project_id,
                nonce=nonce,
                repetitions=operational_repetitions,
                tokenizer=tokenizer,
            )
        )
        return results
    except Exception as error:
        return [
            GateResult(
                gate=name,
                passed=False,
                detail=f"fixture setup failed before gate execution: {type(error).__name__}: {error}",
            )
            for name in (
                "scope_isolation",
                "citation_round_trip",
                "embedding_space_compatibility",
                "release_atomic_switch_and_rollback",
                "revocation_exclusion",
                "update_delete_replay_idempotency",
                "approved_change_visibility_p95",
                "revocation_visibility_p95",
            )
        ]
    finally:
        _cleanup(engine, staged, configuration_id, {release_one, release_two}, nonce)


def _fixture_documents(project_id: str, release_one: str, release_two: str, nonce: str) -> dict[str, Document]:
    def make(
        name: str,
        *,
        release: str = release_one,
        project: str = project_id,
        version: str = "1.0",
        access: str = "PUBLIC",
        text: str,
    ) -> Document:
        return Document(
            document_id=f"{name}-{nonce}",
            knowledge_revision_id=f"{name}-revision-{nonce}",
            project_id=project,
            project_version=version,
            locale="zh-CN",
            access_segment=access,
            knowledge_release_id=release,
            knowledge_space_id=f"space-{project}",
            citation_url=f"https://poc.invalid/{nonce}/{name}",
            title=f"PoC {name}",
            text=text,
            document_type="prose",
        )

    scope_token = f"scopetoken{nonce}"
    return {
        "public": make("public", text=f"公开证据 {scope_token} visiblev1{nonce}"),
        "restricted": make("restricted", access="PROJECT_AUTHORIZED", text=f"受限证据 {scope_token}"),
        "other_project": make("other-project", project=f"other-{project_id}", text=f"跨项目证据 {scope_token}"),
        "other_version": make("other-version", version="2.0", text=f"跨版本证据 {scope_token}"),
        "release_two": make("release-two", release=release_two, text=f"公开证据 visiblev2{nonce}"),
        "revoked": make("revoked", text=f"应撤回证据 revoketoken{nonce}"),
        "deleted": make("deleted", text=f"应删除证据 deletetoken{nonce}"),
        "mismatch": make("mismatch", text=f"向量空间不兼容 mismatchtoken{nonce}"),
    }


def _index_items(
    documents: dict[str, Document],
    embedder: EmbeddingAdapter,
    configuration_id: str,
    tokenizer: OffsetTokenizer,
) -> dict[str, list[IndexedChunk]]:
    chunker = StructureAwareChunker(tokenizer)
    result: dict[str, list[IndexedChunk]] = {}
    for name, document in documents.items():
        chunks = chunker.chunk(document)
        vectors = embedder.embed_documents([chunk.search_text for chunk in chunks])
        result[name] = [
            IndexedChunk(chunk, vector, vectors.space.fingerprint, configuration_id)
            for chunk, vector in zip(chunks, vectors.vectors, strict=True)
        ]
    return result


def _stage_by_release(engine: ServingEngine, item_groups: list[list[IndexedChunk]], nonce: str) -> None:
    releases: dict[str, list[IndexedChunk]] = defaultdict(list)
    for group in item_groups:
        for item in group:
            releases[item.chunk.knowledge_release_id].append(item)
    for release_id, items in releases.items():
        digest = sha256("\n".join(item.chunk.chunk_id for item in items).encode("utf-8")).hexdigest()[:12]
        engine.stage(items, f"cloud-contract-stage-{nonce}-{release_id}-{digest}")


def _scope(project_id: str, release_id: str, configuration_id: str) -> SearchScope:
    return SearchScope(
        project_id=project_id,
        project_version="1.0",
        locale="zh-CN",
        allowed_access_segments=("PUBLIC",),
        knowledge_release_id=release_id,
        configuration_id=configuration_id,
    )


def _run(name: str, check: Callable[[], None]) -> GateResult:
    try:
        check()
    except Exception as error:
        return GateResult(name, False, f"{type(error).__name__}: {error}")
    return GateResult(name, True, "passed against caller-authorized cloud PoC fixture")


def _check_scope(engine: ServingEngine, scope: SearchScope, nonce: str) -> None:
    hits = engine.lexical_search(f"scopetoken{nonce}", scope, 20)
    document_ids = {hit.chunk.document_id for hit in hits}
    expected = f"public-{nonce}"
    if document_ids != {expected}:
        raise AssertionError(f"scope filtering returned {sorted(document_ids)}, expected only {expected}")


def _check_citation(engine: ServingEngine, scope: SearchScope, source: Document, nonce: str) -> None:
    hits = engine.lexical_search(f"visiblev1{nonce}", scope, 10)
    if len(hits) != 1:
        raise AssertionError("citation fixture was not retrieved exactly once")
    hit = hits[0].chunk
    if hit.citation_url != source.citation_url:
        raise AssertionError("citation URL changed in serving projection")
    if source.text[hit.start_char : hit.end_char] != hit.text:
        raise AssertionError("serving projection cannot round-trip the citation range")


def _check_embedding_space(
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    scope: SearchScope,
    items_by_document: dict[str, list[IndexedChunk]],
    nonce: str,
) -> None:
    mismatch_config = f"{scope.configuration_id}-mismatch"
    mismatch_items = [
        replace(item, configuration_id=mismatch_config, embedding_space_fingerprint="intentionally-incompatible")
        for item in items_by_document["mismatch"]
    ]
    try:
        engine.stage(mismatch_items, f"cloud-contract-mismatch-{nonce}")
        mismatch_scope = replace(scope, configuration_id=mismatch_config)
        query = embedder.embed_queries([f"mismatchtoken{nonce}"])
        try:
            hits = engine.vector_search(query.vectors[0], query.space, mismatch_scope, 10)
        except ContractError:
            return
        if hits:
            raise AssertionError("incompatible vector space returned Evidence")
    finally:
        try:
            _delete(
                engine,
                mismatch_items,
                mismatch_config,
                scope.knowledge_release_id,
                f"cloud-contract-mismatch-cleanup-{nonce}",
            )
            if isinstance(engine, ElasticsearchRestEngine):
                engine.delete_poc_index(mismatch_config, scope.knowledge_release_id)
        except Exception:
            pass


def _check_release_switch(
    engine: ServingEngine,
    scope_one: SearchScope,
    scope_two: SearchScope,
    configuration_id: str,
    nonce: str,
) -> None:
    router = ReleaseRouter()
    binding = BindingKey(scope_one.project_id, scope_one.project_version, scope_one.locale, "PUBLIC")
    router.activate(binding, scope_one.knowledge_release_id, f"cloud-contract-activate-r1-{nonce}")
    first = engine.lexical_search(f"visiblev1{nonce}", replace(scope_one, knowledge_release_id=router.resolve(binding)), 10)
    router.activate(binding, scope_two.knowledge_release_id, f"cloud-contract-activate-r2-{nonce}")
    second = engine.lexical_search(f"visiblev2{nonce}", replace(scope_two, knowledge_release_id=router.resolve(binding)), 10)
    router.activate(binding, scope_one.knowledge_release_id, f"cloud-contract-rollback-r1-{nonce}")
    rollback = engine.lexical_search(f"visiblev1{nonce}", replace(scope_one, knowledge_release_id=router.resolve(binding)), 10)
    if not first or not second or not rollback:
        raise AssertionError("release activation or rollback did not make the expected Evidence searchable")
    if any(hit.chunk.knowledge_release_id != scope_one.knowledge_release_id for hit in first + rollback):
        raise AssertionError("release-one search mixed releases")
    if any(hit.chunk.knowledge_release_id != scope_two.knowledge_release_id for hit in second):
        raise AssertionError("release-two search mixed releases")
    if isinstance(engine, ElasticsearchRestEngine):
        alias = f"poc-contract-{nonce}"
        engine.activate_alias(alias, configuration_id=configuration_id, release_id=scope_one.knowledge_release_id, idempotency_key=f"cloud-contract-alias-r1-{nonce}")
        engine.activate_alias(alias, configuration_id=configuration_id, release_id=scope_two.knowledge_release_id, idempotency_key=f"cloud-contract-alias-r2-{nonce}")
        engine.activate_alias(alias, configuration_id=configuration_id, release_id=scope_one.knowledge_release_id, idempotency_key=f"cloud-contract-alias-rollback-{nonce}")


def _check_revocation(
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    scope: SearchScope,
    items: list[IndexedChunk],
    configuration_id: str,
    release_id: str,
    nonce: str,
) -> None:
    revision_id = items[0].chunk.knowledge_revision_id
    _revoke(engine, revision_id, configuration_id, release_id, f"cloud-contract-revoke-{nonce}")
    hits = engine.lexical_search(f"revoketoken{nonce}", scope, 10)
    if hits:
        raise AssertionError("revoked Evidence remained searchable")


def _check_delete_and_replay(
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    scope: SearchScope,
    items_by_document: dict[str, list[IndexedChunk]],
    configuration_id: str,
    release_id: str,
    nonce: str,
) -> None:
    public = items_by_document["public"]
    replay_key = f"cloud-contract-replay-{nonce}"
    engine.stage(public, replay_key)
    engine.stage(public, replay_key)
    conflicting = replace(public[0], chunk=items_by_document["mismatch"][0].chunk)
    try:
        engine.stage([conflicting], replay_key)
    except ContractError:
        pass
    else:
        raise AssertionError("conflicting replay was accepted")

    deleted = items_by_document["deleted"]
    _delete(engine, deleted, configuration_id, release_id, f"cloud-contract-delete-{nonce}")
    _delete(engine, deleted, configuration_id, release_id, f"cloud-contract-delete-{nonce}")
    hits = engine.lexical_search(f"deletetoken{nonce}", scope, 10)
    if hits:
        raise AssertionError("deleted Evidence remained searchable")


def _run_operational_slo_gates(
    engine: ServingEngine,
    embedder: EmbeddingAdapter,
    *,
    project_id: str,
    nonce: str,
    repetitions: int,
    tokenizer: OffsetTokenizer,
) -> list[GateResult]:
    if repetitions < 5:
        return [
            GateResult("approved_change_visibility_p95", False, "at least 5 mutation samples are required"),
            GateResult("revocation_visibility_p95", False, "at least 5 mutation samples are required"),
        ]
    configuration_id = f"contract-slo-{nonce}"
    release_id = f"release-slo-{nonce}"
    scope = _scope(project_id, release_id, configuration_id)
    visibility_ms: list[float] = []
    revocation_ms: list[float] = []
    staged: list[IndexedChunk] = []
    chunker = StructureAwareChunker(tokenizer)
    try:
        for index in range(repetitions):
            token = f"slovisibility{nonce}{index}"
            document = Document(
                document_id=f"slo-{nonce}-{index}",
                knowledge_revision_id=f"slo-revision-{nonce}-{index}",
                project_id=project_id,
                project_version="1.0",
                locale="zh-CN",
                access_segment="PUBLIC",
                knowledge_release_id=release_id,
                knowledge_space_id=f"space-{project_id}",
                citation_url=f"https://poc.invalid/{nonce}/slo/{index}",
                title=f"SLO sample {index}",
                text=f"已批准变更 {token}",
                document_type="prose",
            )
            started = time.monotonic()
            chunks = chunker.chunk(document)
            batch = embedder.embed_documents([chunk.search_text for chunk in chunks])
            items = [
                IndexedChunk(chunk, vector, batch.space.fingerprint, configuration_id)
                for chunk, vector in zip(chunks, batch.vectors, strict=True)
            ]
            staged.extend(items)
            engine.stage(items, f"cloud-contract-slo-stage-{nonce}-{index}")
            _wait_until(
                lambda: any(hit.chunk.document_id == document.document_id for hit in engine.lexical_search(token, scope, 10)),
                timeout_seconds=300.0,
            )
            visibility_ms.append((time.monotonic() - started) * 1000.0)

            started = time.monotonic()
            _revoke(
                engine,
                document.knowledge_revision_id,
                configuration_id,
                release_id,
                f"cloud-contract-slo-revoke-{nonce}-{index}",
            )
            _wait_until(
                lambda: not engine.lexical_search(token, scope, 10),
                timeout_seconds=60.0,
            )
            revocation_ms.append((time.monotonic() - started) * 1000.0)
    except Exception as error:
        detail = f"{type(error).__name__}: {error}; completed {len(visibility_ms)}/{repetitions} samples"
        return [
            GateResult("approved_change_visibility_p95", False, detail),
            GateResult("revocation_visibility_p95", False, detail),
        ]
    finally:
        _cleanup(engine, staged, configuration_id, {release_id}, nonce)

    visibility_p95 = _nearest_rank_percentile(visibility_ms, 95)
    revocation_p95 = _nearest_rank_percentile(revocation_ms, 95)
    return [
        GateResult(
            "approved_change_visibility_p95",
            visibility_p95 <= 300_000.0,
            f"P95={visibility_p95:.2f} ms over {repetitions} end-to-end chunk/embed/index/visibility samples",
        ),
        GateResult(
            "revocation_visibility_p95",
            revocation_p95 <= 60_000.0,
            f"P95={revocation_p95:.2f} ms over {repetitions} revoke-to-exclusion samples",
        ),
    ]


def _wait_until(predicate: Callable[[], bool], *, timeout_seconds: float) -> None:
    deadline = time.monotonic() + timeout_seconds
    last_error: Exception | None = None
    while time.monotonic() < deadline:
        try:
            if predicate():
                return
        except Exception as error:
            last_error = error
        time.sleep(0.25)
    if last_error:
        raise TimeoutError(f"condition did not converge within {timeout_seconds}s; last error: {last_error}")
    raise TimeoutError(f"condition did not converge within {timeout_seconds}s")


def _nearest_rank_percentile(values: list[float], percent: int) -> float:
    if not values:
        raise ValueError("percentile requires at least one value")
    ordered = sorted(values)
    rank = max(1, math.ceil(percent / 100 * len(ordered)))
    return ordered[rank - 1]


def _revoke(engine: ServingEngine, revision_id: str, configuration_id: str, release_id: str, key: str) -> None:
    if isinstance(engine, (ElasticsearchRestEngine, AliyunOpenSearchVectorEngine)):
        engine.revoke_revision(
            revision_id,
            configuration_id=configuration_id,
            release_id=release_id,
            idempotency_key=key,
        )
        return
    raise TypeError(f"cloud gate suite does not know how to revoke through {type(engine).__name__}")


def _delete(engine: ServingEngine, items: list[IndexedChunk], configuration_id: str, release_id: str, key: str) -> None:
    document_id = items[0].chunk.document_id
    if isinstance(engine, ElasticsearchRestEngine):
        engine.delete_document(document_id, configuration_id=configuration_id, release_id=release_id, idempotency_key=key)
        return
    if isinstance(engine, AliyunOpenSearchVectorEngine):
        engine.delete_document(
            document_id,
            configuration_id=configuration_id,
            release_id=release_id,
            idempotency_key=key,
            chunk_ids=[item.chunk.chunk_id for item in items],
        )
        return
    raise TypeError(f"cloud gate suite does not know how to delete through {type(engine).__name__}")


def _cleanup(
    engine: ServingEngine,
    items: list[IndexedChunk],
    configuration_id: str,
    release_ids: set[str],
    nonce: str,
) -> None:
    by_document: dict[tuple[str, str], list[IndexedChunk]] = defaultdict(list)
    for item in items:
        by_document[(item.chunk.document_id, item.chunk.knowledge_release_id)].append(item)
    for index, ((_, release_id), group) in enumerate(by_document.items()):
        try:
            _delete(engine, group, configuration_id, release_id, f"cloud-contract-cleanup-{nonce}-{index}")
        except Exception:
            # The generated report records gate failures. Cleanup failures should not hide the original result.
            pass
    if isinstance(engine, ElasticsearchRestEngine):
        for release_id in release_ids:
            try:
                engine.delete_poc_index(configuration_id, release_id)
            except Exception:
                pass
