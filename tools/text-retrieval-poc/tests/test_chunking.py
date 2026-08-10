from __future__ import annotations

import unittest

from veritymesh_poc.chunking import DEFAULT_PROFILES, FixedRecursiveChunker, SemanticBoundaryChunker, StructureAwareChunker
from veritymesh_poc.embeddings import DeterministicHashEmbedding
from veritymesh_poc.tokenization import UnicodeRegexTokenizer

from support import document


class ChunkingTests(unittest.TestCase):
    def test_profiles_cover_required_document_kinds(self) -> None:
        self.assertEqual(
            {"prose", "faq", "api", "release_notes", "policy", "table", "code"},
            set(DEFAULT_PROFILES),
        )

    def test_all_chunkers_preserve_a_citation_range(self) -> None:
        source = document(
            document_type="api",
            text=(
                "# API\n\n## 创建\n\n调用 POST /v1/events 创建事件。\n\n"
                "```http\nPOST /v1/events\nAuthorization: Bearer token\n```\n\n"
                "## 限制\n\n每分钟最多 120 次请求。"
            ),
        )
        chunkers = (
            StructureAwareChunker(),
            FixedRecursiveChunker(),
            SemanticBoundaryChunker(DeterministicHashEmbedding()),
        )
        for chunker in chunkers:
            with self.subTest(chunker=chunker.name):
                chunks = chunker.chunk(source)
                self.assertTrue(chunks)
                for chunk in chunks:
                    self.assertEqual(source.text[chunk.start_char : chunk.end_char], chunk.text)
                    self.assertTrue(chunk.citation_url)

    def test_structure_chunks_never_exceed_profile_hard_limit(self) -> None:
        source = document(document_type="prose", text="\n\n".join("词" * 900 for _ in range(3)))
        tokenizer = UnicodeRegexTokenizer()
        profile = DEFAULT_PROFILES["prose"]
        chunks = StructureAwareChunker(tokenizer).chunk(source)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(tokenizer.spans(chunk.text)) <= profile.hard_max_tokens for chunk in chunks))


if __name__ == "__main__":
    unittest.main()
