from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from .chunking import StructureAwareChunker
from .domain import Chunk, ContractError, Document, IndexedChunk, SearchScope
from .embeddings import DeterministicHashEmbedding
from .retrieval import BindingKey, InMemoryServingEngine, ReleaseRouter


@dataclass(frozen=True)
class GateResult:
    gate: str
    passed: bool
    detail: str

    def to_dict(self) -> dict[str, str | bool]:
        return {"gate": self.gate, "passed": self.passed, "detail": self.detail}


HARD_GATES = (
    "scope_isolation",
    "revocation_exclusion",
    "citation_round_trip",
    "embedding_space_compatibility",
    "release_atomic_switch_and_rollback",
    "update_delete_replay_idempotency",
)


def run_in_memory_contract_gates() -> list[GateResult]:
    checks: tuple[tuple[str, Callable[[], None]], ...] = (
        ("scope_isolation", _check_scope_isolation),
        ("revocation_exclusion", _check_revocation),
        ("citation_round_trip", _check_citation),
        ("embedding_space_compatibility", _check_embedding_space),
        ("release_atomic_switch_and_rollback", _check_release_switch),
        ("update_delete_replay_idempotency", _check_idempotency),
    )
    results: list[GateResult] = []
    for name, check in checks:
        try:
            check()
        except Exception as error:  # Gate reports must preserve all failures rather than stop at the first one.
            results.append(GateResult(name, False, f"{type(error).__name__}: {error}"))
        else:
            results.append(GateResult(name, True, "passed by deterministic in-memory contract fixture"))
    return results


def all_gates_pass(results: list[GateResult]) -> bool:
    return len(results) == len(HARD_GATES) and all(result.passed for result in results)


def _document(
    *,
    document_id: str,
    revision: str,
    project: str = "project-alpha",
    version: str = "1.0",
    locale: str = "zh-CN",
    access: str = "PUBLIC",
    release: str = "release-1",
    text: str = "Alpha 产品支持导出审计日志。",
) -> Document:
    return Document(
        document_id=document_id,
        knowledge_revision_id=revision,
        project_id=project,
        project_version=version,
        locale=locale,
        access_segment=access,
        knowledge_release_id=release,
        knowledge_space_id=f"space-{project}",
        citation_url=f"https://example.invalid/docs/{document_id}",
        title=document_id,
        text=text,
        document_type="prose",
    )


def _indexed(document: Document, configuration_id: str = "contract") -> tuple[IndexedChunk, DeterministicHashEmbedding]:
    embedder = DeterministicHashEmbedding()
    chunks = StructureAwareChunker().chunk(document)
    if not chunks:
        raise AssertionError("fixture document generated no chunks")
    vectors = embedder.embed_documents([chunk.search_text for chunk in chunks])
    return (
        IndexedChunk(
            chunk=chunks[0],
            vector=vectors.vectors[0],
            embedding_space_fingerprint=vectors.space.fingerprint,
            configuration_id=configuration_id,
        ),
        embedder,
    )


def _scope(*, release: str = "release-1", access: tuple[str, ...] = ("PUBLIC",), configuration: str = "contract") -> SearchScope:
    return SearchScope(
        project_id="project-alpha",
        project_version="1.0",
        locale="zh-CN",
        allowed_access_segments=access,
        knowledge_release_id=release,
        configuration_id=configuration,
    )


def _check_scope_isolation() -> None:
    engine = InMemoryServingEngine()
    public, embedder = _indexed(_document(document_id="public", revision="rev-public"))
    restricted, _ = _indexed(_document(document_id="restricted", revision="rev-restricted", access="PROJECT_AUTHORIZED"))
    other_project, _ = _indexed(_document(document_id="other", revision="rev-other", project="project-beta"))
    other_version, _ = _indexed(_document(document_id="v2", revision="rev-v2", version="2.0"))
    engine.stage([public, restricted, other_project, other_version], "scope-stage")
    query = embedder.embed_queries(["审计日志"])
    hits = engine.vector_search(query.vectors[0], query.space, _scope(), 10)
    _require([hit.chunk.document_id for hit in hits] == ["public"], "scope leaked non-public/non-project data")


def _check_revocation() -> None:
    engine = InMemoryServingEngine()
    item, embedder = _indexed(_document(document_id="revoked", revision="revoked-revision"))
    engine.stage([item], "revoke-stage")
    engine.revoke_revision("revoked-revision", "revoke-event")
    query = embedder.embed_queries(["审计日志"])
    _require(not engine.vector_search(query.vectors[0], query.space, _scope(), 10), "revoked evidence was recalled")


def _check_citation() -> None:
    document = _document(document_id="citation", revision="citation-revision", text="# 引用\n\n可追溯范围必须保留。")
    chunk = StructureAwareChunker().chunk(document)[0]
    _require(document.text[chunk.start_char : chunk.end_char] == chunk.text, "citation range cannot recover chunk text")
    _require(bool(chunk.citation_url and chunk.section and chunk.knowledge_release_id), "citation fields are incomplete")


def _check_embedding_space() -> None:
    engine = InMemoryServingEngine()
    item, embedder = _indexed(_document(document_id="space", revision="space-revision"))
    incompatible = IndexedChunk(
        chunk=item.chunk,
        vector=item.vector,
        embedding_space_fingerprint="incompatible-space",
        configuration_id="contract",
    )
    engine.stage([incompatible], "space-stage")
    query = embedder.embed_queries(["审计日志"])
    try:
        engine.vector_search(query.vectors[0], query.space, _scope(), 10)
    except ContractError:
        return
    raise AssertionError("mixed vector spaces were accepted")


def _check_release_switch() -> None:
    engine = InMemoryServingEngine()
    old, embedder = _indexed(_document(document_id="old", revision="old-revision", release="release-1", text="旧版规则。"))
    new, _ = _indexed(_document(document_id="new", revision="new-revision", release="release-2", text="新版规则。"))
    engine.stage([old, new], "release-stage")
    router = ReleaseRouter()
    binding = BindingKey("project-alpha", "1.0", "zh-CN", "PUBLIC")
    router.activate(binding, "release-1", "activate-old")
    query = embedder.embed_queries(["规则"])
    before = engine.vector_search(query.vectors[0], query.space, _scope(release=router.resolve(binding)), 10)
    router.activate(binding, "release-2", "activate-new")
    after = engine.vector_search(query.vectors[0], query.space, _scope(release=router.resolve(binding)), 10)
    router.activate(binding, "release-1", "rollback-old")
    rollback = engine.vector_search(query.vectors[0], query.space, _scope(release=router.resolve(binding)), 10)
    _require([hit.chunk.document_id for hit in before] == ["old"], "old release contains mixed documents")
    _require([hit.chunk.document_id for hit in after] == ["new"], "new release contains mixed documents")
    _require([hit.chunk.document_id for hit in rollback] == ["old"], "rollback did not restore prior release")


def _check_idempotency() -> None:
    engine = InMemoryServingEngine()
    item, embedder = _indexed(_document(document_id="idempotent", revision="idempotent-revision"))
    engine.stage([item], "same-event")
    engine.stage([item], "same-event")
    engine.delete_document("idempotent", "delete-event")
    engine.delete_document("idempotent", "delete-event")
    query = embedder.embed_queries(["审计日志"])
    _require(not engine.vector_search(query.vectors[0], query.space, _scope(), 10), "deleted document was recalled")
    another, _ = _indexed(_document(document_id="different", revision="different-revision"))
    try:
        engine.stage([another], "same-event")
    except ContractError:
        return
    raise AssertionError("conflicting idempotency replay was accepted")


def _require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)
