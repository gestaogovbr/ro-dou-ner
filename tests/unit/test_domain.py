import json
import math
from dataclasses import replace
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from ro_dou_ner.adapters.text import OverlappingChunker
from ro_dou_ner.domain import (
    EnrichmentResult,
    Mention,
    MentionCandidate,
    ModelInfo,
    PipelineSpec,
    PublicationBatch,
    TextChunk,
    consolidate,
    globalize,
    idempotency_key,
    source_revision,
    validate_mention,
)


@pytest.fixture
def pipeline():
    return PipelineSpec(
        ModelInfo("gliner", "org/checkpoint", "abc123"),
        "taxonomy-v1",
        ("PERSON", "ORGANIZATION"),
        "nfc-v1",
        {"size": 128, "overlap": 20},
        {"rules": "v1", "gliner": "v1"},
        {"threshold": 0.5},
    )


def test_source_revision_preserves_raw_text_and_canonical_metadata():
    assert source_revision("é", {"b": 2, "a": 1}) == source_revision("é", {"a": 1, "b": 2})
    assert source_revision("é") != source_revision("e\u0301")
    assert source_revision("texto", {"date": "2026-10-06"}) != source_revision(
        "texto", {"date": "2026-10-07"}
    )
    assert source_revision("texto") != source_revision("texto ")


@pytest.mark.parametrize(
    "updates",
    [
        {"model": ModelInfo("gliner", "org/checkpoint", "different")},
        {"model": ModelInfo("other", "org/checkpoint", "abc123")},
        {"model": ModelInfo("gliner", "other/checkpoint", "abc123")},
        {"taxonomy_version": "taxonomy-v2"},
        {"labels": ("PERSON", "LOCATION")},
        {"normalization_version": "nfc-v2"},
        {"chunking": {"size": 256, "overlap": 20}},
        {"extractor_versions": {"rules": "v2", "gliner": "v1"}},
        {"configuration": {"threshold": 0.6}},
    ],
)
def test_every_effective_pipeline_component_changes_version(pipeline, updates):
    assert replace(pipeline, **updates).version != pipeline.version


def test_version_serialization_is_canonical_and_rejects_nan(pipeline):
    assert replace(pipeline, chunking={"overlap": 20, "size": 128}).version == pipeline.version
    with pytest.raises(ValueError):
        replace(pipeline, configuration={"threshold": math.nan})


def test_idempotency_tuple_has_unambiguous_boundaries():
    assert idempotency_key("a", "bc", "d") != idempotency_key("ab", "c", "d")
    assert idempotency_key("a", "b", "c") == idempotency_key("a", "b", "c")
    assert len(idempotency_key("a", "b", "c")) == 64


def test_global_offsets_use_unicode_codepoints():
    text = "👩🏾 São José"
    local = TextChunk(10, 10 + len(text), text)
    candidate = MentionCandidate("PERSON", "São José", 3, len(text), 0.8, "gliner")
    mention = globalize(candidate, local, ("PERSON",))
    assert mention.start == 13
    assert mention.end == 10 + len(text)
    validate_mention(mention, "x" * 10 + text, ("PERSON",))


@pytest.mark.parametrize(
    "changes",
    [
        {"start": -1},
        {"start": 0.0},
        {"start": True},
        {"end": 0},
        {"end": 99},
        {"surface": "Maria"},
        {"label": "UNKNOWN"},
        {"extractor": ""},
        {"score": math.nan},
        {"score": math.inf},
        {"score": -0.1},
        {"score": 1.1},
        {"score": True},
        {"score": "0.5"},
    ],
)
def test_invalid_mentions_are_rejected(changes):
    mention = Mention("PERSON", "José", 0, 4, 0.9, "gliner")
    with pytest.raises(ValueError):
        validate_mention(replace(mention, **changes), "José", ("PERSON",))


def test_consolidation_prioritizes_rules_without_comparing_cross_model_scores():
    gliner = Mention("PERSON", "Maria Silva", 0, 11, 0.99, "gliner")
    rule = replace(gliner, score=0.1, extractor="rules")
    assert consolidate((gliner, rule), "Maria Silva", ("PERSON",)) == (rule,)
    assert consolidate((rule, gliner), "Maria Silva", ("PERSON",)) == (rule,)


def test_consolidation_keeps_nested_spans_and_different_labels():
    whole = Mention("ORGANIZATION", "Banco Maria", 0, 11, 0.8, "gliner")
    nested = Mention("PERSON", "Maria", 6, 11, 0.8, "gliner")
    same_span_other_label = replace(nested, label="ORGANIZATION")
    duplicate_lower_score = replace(nested, score=0.2)
    result = consolidate(
        (nested, whole, same_span_other_label, duplicate_lower_score),
        "Banco Maria",
        ("PERSON", "ORGANIZATION"),
    )
    assert set(result) == {whole, nested, same_span_other_label}


def test_result_roundtrip_validates_spans_and_preserves_provenance(pipeline):
    result = EnrichmentResult(
        "inlabs:1",
        source_revision("José"),
        pipeline.version,
        pipeline.taxonomy_version,
        pipeline.model,
        "José",
        (Mention("PERSON", "José", 0, 4, 0.75, "gliner"),),
        datetime(2026, 10, 6, tzinfo=UTC),
        {"nested": {"x": [1]}},
    )
    restored = EnrichmentResult.from_dict(json.loads(json.dumps(result.to_dict())))
    assert restored == result
    assert restored.idempotency_key == result.idempotency_key
    payload = result.to_dict()
    payload["metadata"]["nested"]["x"].append(2)
    assert result.metadata["nested"]["x"] == [1]
    payload["mentions"][0]["end"] = 8
    with pytest.raises(ValueError):
        EnrichmentResult.from_dict(payload)


@pytest.mark.parametrize("size", [0, -1, 0.5, True])
def test_batch_rejects_invalid_pagination(size):
    with pytest.raises(ValueError):
        PublicationBatch(page_size=size)


def test_naive_result_timestamp_rejected(pipeline):
    with pytest.raises(ValueError, match="timezone"):
        EnrichmentResult(
            "inlabs:1", "rev", pipeline.version, "v1", pipeline.model, "", (), datetime(2026, 10, 6)
        )


@given(
    text=st.text(max_size=400),
    size=st.integers(min_value=1, max_value=100),
    raw_overlap=st.integers(min_value=0, max_value=100),
)
def test_arbitrary_unicode_chunking_has_exact_slices_complete_coverage_and_valid_global_offsets(
    text, size, raw_overlap
):
    from ro_dou_ner.domain import CanonicalDocument

    document = CanonicalDocument("inlabs:unicode", text, "revision")
    chunks = list(OverlappingChunker(size, raw_overlap % size).chunk(document))
    covered = set()
    for chunk in chunks:
        assert chunk.text == text[chunk.start : chunk.end]
        assert len(chunk.text) <= size
        covered.update(range(chunk.start, chunk.end))
        if chunk.text:
            candidate = MentionCandidate("PERSON", chunk.text, 0, len(chunk.text), None, "test")
            mention = globalize(candidate, chunk, ("PERSON",))
            validate_mention(mention, text, ("PERSON",))
    assert covered == set(range(len(text)))
    if text:
        assert chunks[0].start == 0 and chunks[-1].end == len(text)
