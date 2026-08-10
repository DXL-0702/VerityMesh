from __future__ import annotations

from veritymesh_poc.chunking import StructureAwareChunker
from veritymesh_poc.domain import Document, IndexedChunk, SearchScope
from veritymesh_poc.embeddings import DeterministicHashEmbedding


def document(**overrides) -> Document:
    values = {
        "document_id": "doc-1",
        "knowledge_revision_id": "revision-1",
        "project_id": "project-alpha",
        "project_version": "1.0",
        "locale": "zh-CN",
        "access_segment": "PUBLIC",
        "knowledge_release_id": "release-1",
        "knowledge_space_id": "space-1",
        "citation_url": "https://example.invalid/doc-1",
        "title": "审计日志",
        "text": "# 审计日志\n\n管理员可以导出审计日志 CSV。",
        "document_type": "prose",
    }
    values.update(overrides)
    return Document(**values)


def indexed_item(document_value: Document | None = None, configuration_id: str = "config-1"):
    value = document_value or document()
    embedder = DeterministicHashEmbedding()
    chunk = StructureAwareChunker().chunk(value)[0]
    batch = embedder.embed_documents([chunk.search_text])
    return (
        IndexedChunk(
            chunk=chunk,
            vector=batch.vectors[0],
            embedding_space_fingerprint=batch.space.fingerprint,
            configuration_id=configuration_id,
        ),
        embedder,
    )


def scope(configuration_id: str = "config-1") -> SearchScope:
    return SearchScope(
        project_id="project-alpha",
        project_version="1.0",
        locale="zh-CN",
        allowed_access_segments=("PUBLIC",),
        knowledge_release_id="release-1",
        configuration_id=configuration_id,
    )
