"""Exact-span NER evaluation independent of model and persistence SDKs.

Mention identity is (document, label, start, end); duplicates count once.
Every zero denominator yields zero, including absent labels in macro F1.
Failed documents remain in the denominator and contribute false negatives.
"""

import hashlib
import json
import resource
import sys
import time
import tracemalloc
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ro_dou_ner.domain.mentions import Mention, validate_mention
from ro_dou_ner.domain.publications import Publication


@dataclass(frozen=True)
class EvaluationDocument:
    publication: Publication
    mentions: tuple[Mention, ...]


def _taxonomy(labels: Iterable[str]) -> tuple[str, ...]:
    values = tuple(labels)
    if not values or any(not isinstance(label, str) or not label for label in values):
        raise ValueError("evaluation labels must be nonempty strings")
    return tuple(sorted(set(values)))


def _mention_keys(
    mentions: Iterable[Mention], labels: tuple[str, ...]
) -> set[tuple[str, int, int]]:
    keys = set()
    for mention in mentions:
        if mention.label not in labels:
            raise ValueError("evaluation mention is outside the taxonomy")
        if (
            type(mention.start) is not int
            or type(mention.end) is not int
            or not 0 <= mention.start < mention.end
        ):
            raise ValueError("evaluation offsets must be nonnegative half-open spans")
        keys.add((mention.label, mention.start, mention.end))
    return keys


def _metrics(tp: int, fp: int, fn: int) -> dict[str, int | float]:
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": precision,
        "recall": recall,
        "f1": 2 * tp / (2 * tp + fp + fn) if 2 * tp + fp + fn else 0.0,
        "support": tp + fn,
    }


def evaluate_mentions(
    gold_by_doc: Mapping[str, Iterable[Mention]],
    predicted_by_doc: Mapping[str, Iterable[Mention]],
    labels: Iterable[str],
) -> dict[str, Any]:
    """Compare exact span + label sets, never matching across documents."""
    taxonomy = _taxonomy(labels)
    counts = {label: [0, 0, 0] for label in taxonomy}
    for document_id in gold_by_doc.keys() | predicted_by_doc.keys():
        gold = _mention_keys(gold_by_doc.get(document_id, ()), taxonomy)
        predicted = _mention_keys(predicted_by_doc.get(document_id, ()), taxonomy)
        for index, values in enumerate((gold & predicted, predicted - gold, gold - predicted)):
            for label, _, _ in values:
                counts[label][index] += 1
    per_label = {label: _metrics(*counts[label]) for label in taxonomy}
    micro = _metrics(*(sum(values[index] for values in counts.values()) for index in range(3)))
    macro = {
        metric: sum(float(values[metric]) for values in per_label.values()) / len(taxonomy)
        for metric in ("precision", "recall", "f1")
    }
    return {
        "matching": "document + exact half-open span + label",
        "duplicate_policy": "set",
        "zero_division": 0.0,
        "macro_labels": list(taxonomy),
        "per_label": per_label,
        "micro": micro,
        "macro": macro,
    }


def load_evaluation_dataset(
    path: str | Path, labels: Iterable[str]
) -> tuple[EvaluationDocument, ...]:
    """Load UTF-8 JSONL and reject malformed/duplicate annotations eagerly."""
    return _parse_evaluation_dataset(Path(path).read_text(encoding="utf-8"), labels)


def _parse_evaluation_dataset(
    content: str, labels: Iterable[str]
) -> tuple[EvaluationDocument, ...]:
    taxonomy = _taxonomy(labels)
    documents = []
    seen = set()
    for line_number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
            if not isinstance(value.get("metadata", {}), dict):
                raise ValueError("metadata must be a JSON object")
            publication = Publication(
                value["publication_id"], value["body_text"], value.get("metadata", {})
            )
            if publication.publication_id in seen:
                raise ValueError("duplicate publication_id")
            mentions = tuple(
                Mention(item["label"], item["surface"], item["start"], item["end"], None, "gold")
                for item in value["mentions"]
            )
            for mention in mentions:
                validate_mention(mention, publication.body_text, taxonomy)
            if len(_mention_keys(mentions, taxonomy)) != len(mentions):
                raise ValueError("duplicate gold mention")
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise ValueError(f"invalid evaluation document at line {line_number}: {exc}") from exc
        documents.append(EvaluationDocument(publication, mentions))
        seen.add(publication.publication_id)
    if not documents:
        raise ValueError("evaluation dataset must contain at least one document")
    return tuple(documents)


def evaluate_pipeline(
    dataset_path: str | Path,
    processor: Callable[[Publication], Any],
    labels: Iterable[str],
    metadata: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Benchmark a callable returning mentions or an object exposing .mentions.

    Timings include processing and prediction validation, excluding JSONL loading.
    RSS is the process-lifetime high-water mark, not incremental model memory.
    Tracemalloc measures Python allocations, excluding native/GPU allocations.
    If tracing was already active, its peak includes that pre-existing scope.
    """
    taxonomy = _taxonomy(labels)
    path = Path(dataset_path)
    dataset_bytes = path.read_bytes()
    documents = _parse_evaluation_dataset(dataset_bytes.decode("utf-8"), taxonomy)
    gold = {document.publication.publication_id: document.mentions for document in documents}
    predictions: dict[str, tuple[Mention, ...]] = {}
    latencies: list[float] = []
    failures: list[dict[str, str]] = []
    owns_tracing = not tracemalloc.is_tracing()
    if owns_tracing:
        tracemalloc.start()
    started = time.perf_counter()
    try:
        for document in documents:
            doc_started = time.perf_counter()
            try:
                output = processor(document.publication)
                if (
                    hasattr(output, "body_text")
                    and output.body_text != document.publication.body_text
                ):
                    raise ValueError(
                        "Evaluation annotations must address the canonical output text"
                    )
                if (
                    hasattr(output, "publication_id")
                    and output.publication_id != document.publication.publication_id
                ):
                    raise ValueError(
                        "prediction publication_id does not match the evaluated document"
                    )
                mentions = tuple(output.mentions if hasattr(output, "mentions") else output)
                for mention in mentions:
                    validate_mention(mention, document.publication.body_text, taxonomy)
                predictions[document.publication.publication_id] = mentions
            except Exception as exc:
                # Exception text may include credentials/source contents; retain only type.
                failures.append(
                    {
                        "publication_id": document.publication.publication_id,
                        "error_type": type(exc).__name__,
                    }
                )
            finally:
                latencies.append(time.perf_counter() - doc_started)
        elapsed = time.perf_counter() - started
        _, python_peak = tracemalloc.get_traced_memory()
    finally:
        if owns_tracing:
            tracemalloc.stop()
    report = evaluate_mentions(gold, predictions, taxonomy)
    report["metadata"] = {
        **dict(metadata or {}),
        "dataset_path": str(path.resolve()),
        "dataset_sha256": hashlib.sha256(dataset_bytes).hexdigest(),
        "dataset_kinds": sorted(
            {
                str(document.publication.metadata.get("dataset_kind", "unspecified"))
                for document in documents
            }
        ),
    }
    total, succeeded = len(documents), len(predictions)
    report["coverage"] = {
        "total_documents": total,
        "successful_documents": succeeded,
        "failed_documents": len(failures),
        "fraction": succeeded / total,
        "failures": failures,
    }
    report["performance"] = {
        "scope": "processor call and prediction validation; excludes dataset loading",
        "elapsed_seconds": elapsed,
        "document_latency_seconds": latencies,
        "mean_latency_seconds": sum(latencies) / total,
        "attempted_documents_per_second": total / elapsed if elapsed else 0.0,
        "successful_documents_per_second": succeeded / elapsed if elapsed else 0.0,
        "python_peak_allocated_bytes": python_peak,
        "python_memory_scope": "benchmark Python allocations"
        if owns_tracing
        else "pre-existing process tracing peak",
        "process_peak_rss_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        * (1 if sys.platform == "darwin" else 1024),
        "rss_scope": "process-lifetime high-water mark; includes runtime and model",
        "memory_limitations": "tracemalloc excludes native and GPU allocations; RSS is not model-only memory",
    }
    return report
