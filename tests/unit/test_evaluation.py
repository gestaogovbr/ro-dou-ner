import hashlib
import json
import tracemalloc
from pathlib import Path
from types import SimpleNamespace

import pytest

from ro_dou_ner.application.evaluation import (
    evaluate_mentions,
    evaluate_pipeline,
    load_evaluation_dataset,
)
from ro_dou_ner.domain.mentions import Mention

LABELS = (
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "LEGAL_REFERENCE",
    "PROCESS_NUMBER",
    "IDENTIFIER",
    "DATE",
    "MONEY",
)
FIXTURE = Path(__file__).parents[1] / "fixtures" / "evaluation-synthetic.jsonl"


def mention(label="PERSON", start=0, end=2):
    return Mention(label, "xx", start, end, None, "test")


def test_exact_matching_requires_document_span_and_label():
    result = evaluate_mentions(
        {"a": [mention(), mention(start=3, end=5), mention(start=6, end=8)]},
        {"a": [mention(), mention(start=3, end=6), mention("LOCATION", 6, 8)], "b": [mention()]},
        ["PERSON", "LOCATION"],
    )
    assert result["micro"]["true_positives"] == 1
    assert result["micro"]["false_positives"] == 3
    assert result["micro"]["false_negatives"] == 2
    assert result["micro"]["precision"] == pytest.approx(1 / 4)
    assert result["micro"]["recall"] == pytest.approx(1 / 3)
    assert result["micro"]["f1"] == pytest.approx(2 / 7)
    assert result["macro"]["f1"] == pytest.approx(1 / 6)
    assert result["per_label"]["LOCATION"]["false_positives"] == 1


def test_duplicate_mentions_are_sets_and_missing_predictions_are_false_negatives():
    result = evaluate_mentions(
        {"a": [mention(), mention()], "missing": [mention()]},
        {"a": [mention(), mention()]},
        ["PERSON"],
    )
    assert result["micro"]["true_positives"] == 1
    assert result["micro"]["false_negatives"] == 1
    assert result["micro"]["false_positives"] == 0


def test_absent_labels_use_explicit_zero_convention_in_macro():
    result = evaluate_mentions({"a": [mention()]}, {"a": [mention()]}, ["PERSON", "DATE"])
    assert result["micro"]["f1"] == 1
    assert result["per_label"]["DATE"]["precision"] == 0
    assert result["per_label"]["DATE"]["recall"] == 0
    assert result["macro"]["f1"] == 0.5
    assert evaluate_mentions({}, {}, ["PERSON"])["micro"]["f1"] == 0


@pytest.mark.parametrize("labels", [[], [""], [1]])
def test_invalid_taxonomy_is_rejected(labels):
    with pytest.raises(ValueError, match="labels"):
        evaluate_mentions({}, {}, labels)


@pytest.mark.parametrize(
    "bad", [mention("UNKNOWN"), mention(start=-1), mention(start=True), mention(start=2, end=2)]
)
def test_invalid_evaluation_mentions_are_rejected(bad):
    with pytest.raises(ValueError):
        evaluate_mentions({}, {"a": [bad]}, ["PERSON"])


def test_fixture_annotations_preserve_unicode_and_cover_taxonomy():
    documents = load_evaluation_dataset(FIXTURE, LABELS)
    assert len(documents) >= 4
    assert {m.label for doc in documents for m in doc.mentions} == set(LABELS)
    assert "Conceição" in documents[0].publication.body_text
    assert "🙂" in documents[-1].publication.body_text
    for doc in documents:
        assert doc.publication.metadata["dataset_kind"] == "synthetic"
        for entity in doc.mentions:
            assert entity.surface == doc.publication.body_text[entity.start : entity.end]


@pytest.mark.parametrize(
    "problem",
    [
        "offset",
        "unknown_label",
        "duplicate_mention",
        "duplicate_id",
        "missing_key",
        "malformed",
        "metadata",
    ],
)
def test_dataset_rejects_invalid_annotations(tmp_path, problem):
    value = {
        "publication_id": "a",
        "body_text": "José",
        "mentions": [{"label": "PERSON", "surface": "José", "start": 0, "end": 4}],
    }
    if problem == "offset":
        value["mentions"][0]["end"] = 5
    if problem == "unknown_label":
        value["mentions"][0]["label"] = "UNKNOWN"
    if problem == "duplicate_mention":
        value["mentions"] *= 2
    if problem == "missing_key":
        del value["publication_id"]
    if problem == "metadata":
        value["metadata"] = None
    line = json.dumps(value)
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        "{"
        if problem == "malformed"
        else line + ("\n" + line if problem == "duplicate_id" else ""),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="line"):
        load_evaluation_dataset(path, LABELS)


def test_empty_dataset_is_rejected(tmp_path):
    path = tmp_path / "empty.jsonl"
    path.write_text("\n \n")
    with pytest.raises(ValueError, match="at least one"):
        load_evaluation_dataset(path, LABELS)


def test_benchmark_exact_predictions_record_reproducibility_and_performance():
    documents = load_evaluation_dataset(FIXTURE, LABELS)
    by_id = {doc.publication.publication_id: doc.mentions for doc in documents}
    metadata = {
        "model": {"provider": "fixture", "model_id": "oracle", "revision": "sha"},
        "checkpoint": "sha",
        "pipeline_version": "abc",
    }
    result = evaluate_pipeline(
        FIXTURE,
        lambda doc: SimpleNamespace(mentions=by_id[doc.publication_id]),
        iter(LABELS),
        metadata,
    )
    assert result["micro"]["f1"] == result["macro"]["f1"] == 1
    assert result["coverage"]["fraction"] == 1
    assert result["coverage"]["successful_documents"] == len(documents)
    assert result["metadata"]["dataset_sha256"] == hashlib.sha256(FIXTURE.read_bytes()).hexdigest()
    assert result["metadata"]["model"] == metadata["model"]
    assert result["metadata"]["pipeline_version"] == "abc"
    assert result["metadata"]["dataset_kinds"] == ["synthetic"]
    assert len(result["performance"]["document_latency_seconds"]) == len(documents)
    assert result["performance"]["elapsed_seconds"] > 0
    assert result["performance"]["successful_documents_per_second"] > 0
    assert result["performance"]["python_peak_allocated_bytes"] > 0
    assert result["performance"]["process_peak_rss_bytes"] > 0
    json.dumps(result, allow_nan=False)


def test_failed_document_remains_in_evaluation_denominator_and_error_is_sanitized():
    documents = load_evaluation_dataset(FIXTURE, LABELS)
    by_id = {doc.publication.publication_id: doc.mentions for doc in documents}

    def process(doc):
        if doc.publication_id == "synthetic:1":
            raise RuntimeError("secret token should not be reported")
        return by_id[doc.publication_id]

    result = evaluate_pipeline(FIXTURE, process, LABELS)
    assert result["coverage"]["failed_documents"] == 1
    assert result["coverage"]["fraction"] == 4 / 5
    assert result["micro"]["false_negatives"] == 4
    assert result["coverage"]["failures"] == [
        {"publication_id": "synthetic:1", "error_type": "RuntimeError"}
    ]
    assert "secret token" not in json.dumps(result)


def test_invalid_prediction_counts_as_failed_document(tmp_path):
    path = tmp_path / "dataset.jsonl"
    path.write_text(
        json.dumps(
            {
                "publication_id": "a",
                "body_text": "José",
                "mentions": [{"label": "PERSON", "surface": "José", "start": 0, "end": 4}],
            }
        )
    )
    result = evaluate_pipeline(path, lambda doc: [mention()], LABELS)
    assert result["coverage"]["failed_documents"] == 1
    assert result["coverage"]["successful_documents"] == 0
    assert result["micro"]["false_negatives"] == 1


def test_benchmark_preserves_preexisting_tracing():
    tracemalloc.start()
    try:
        result = evaluate_pipeline(FIXTURE, lambda doc: (), LABELS)
        assert tracemalloc.is_tracing()
        assert result["performance"]["python_memory_scope"] == "pre-existing process tracing peak"
    finally:
        tracemalloc.stop()


def test_prediction_for_wrong_document_is_rejected():
    result = evaluate_pipeline(
        FIXTURE, lambda doc: SimpleNamespace(publication_id="another", mentions=()), LABELS
    )
    assert result["coverage"]["successful_documents"] == 0
    assert result["coverage"]["failed_documents"] == 5


def test_annotation_offsets_cannot_silently_reference_different_normalized_text():
    result = evaluate_pipeline(
        FIXTURE,
        lambda doc: SimpleNamespace(body_text=doc.body_text + " changed", mentions=()),
        LABELS,
    )
    assert result["coverage"]["failed_documents"] == 5
    assert result["micro"]["false_negatives"] == 12
