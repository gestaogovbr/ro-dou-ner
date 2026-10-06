import random

import pytest

from ro_dou_ner.adapters.text import HTMLTextPreparer, OverlappingChunker
from ro_dou_ner.domain.publications import CanonicalDocument, Publication


def test_html_normalization_preserves_unicode_and_structural_boundaries():
    publication = Publication(
        "inlabs:1",
        "<p> Mari\u0301a&nbsp; Silva </p><p>São <b>Paulo</b><br>valor: 2 &lt; 5</p><script>alert('bad')</script><style>p{}</style>",
    )
    result = HTMLTextPreparer().prepare(publication)
    assert result.body_text == "María Silva\nSão Paulo\nvalor: 2 < 5"
    assert len(result.source_revision) == 64


def test_plain_text_comparisons_newlines_and_whitespace():
    publication = Publication("inlabs:1", "A < 5 e B > 2\r\n\tSão\tPaulo\rOutra linha\n\nFinal")
    assert (
        HTMLTextPreparer().prepare(publication).body_text
        == "A < 5 e B > 2\nSão Paulo\nOutra linha\nFinal"
    )


def test_revision_uses_raw_content_and_metadata_even_if_normalized_text_matches():
    preparer = HTMLTextPreparer()
    results = [
        preparer.prepare(publication)
        for publication in (
            Publication("inlabs:1", "<p>Texto</p>", {"date": "2026-10-06"}),
            Publication("inlabs:1", "Texto", {"date": "2026-10-06"}),
            Publication("inlabs:1", "Texto", {"date": "2026-10-07"}),
        )
    ]
    assert len({result.body_text for result in results}) == 1
    assert len({result.source_revision for result in results}) == 3


@pytest.mark.parametrize(
    "max_chars,overlap", [(0, 0), (1, 1), (20, -1), (20, 20), (True, 0), (20, False), (20.0, 2)]
)
def test_chunker_rejects_invalid_configuration(max_chars, overlap):
    with pytest.raises(ValueError):
        OverlappingChunker(max_chars, overlap)


@pytest.mark.parametrize(
    "max_chars,overlap", [(1, 0), (3, 1), (10, 0), (10, 9), (50, 10), (700, 100)]
)
def test_chunk_coverage_and_exact_slices_for_different_sizes(max_chars, overlap):
    rng = random.Random(17)
    text = "".join(rng.choice(("A", "ç", "ã", "界", " ", "\n")) for _ in range(1400)) + "tail"
    document = CanonicalDocument("inlabs:1", text, "revision")
    chunks = OverlappingChunker(max_chars, overlap).chunk(document)
    covered = set()
    previous_end = 0
    for chunk in chunks:
        assert chunk.text == text[chunk.start : chunk.end]
        assert 0 < len(chunk.text) <= max_chars
        assert chunk.start <= previous_end
        assert chunk.end > previous_end
        covered.update(range(chunk.start, chunk.end))
        previous_end = chunk.end
    assert covered == set(range(len(text)))
    assert chunks[-1].text.endswith("tail") or max_chars < len("tail")


def test_chunker_empty_single_chunk_and_unbroken_word():
    chunker = OverlappingChunker(15, 3)
    assert chunker.chunk(CanonicalDocument("inlabs:1", "", "v")) == ()
    assert [item.text for item in chunker.chunk(CanonicalDocument("inlabs:1", "short", "v"))] == [
        "short"
    ]
    chunks = chunker.chunk(CanonicalDocument("inlabs:1", "X" * 50, "v"))
    assert chunks[-1].end == 50
    assert all(len(item.text) <= 15 for item in chunks)
