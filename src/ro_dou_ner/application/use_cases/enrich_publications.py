"""Publication enrichment: retries and persistence are independent of projection."""

import logging
from collections.abc import Iterable
from copy import deepcopy
from dataclasses import asdict
from datetime import UTC, datetime

from ro_dou_ner.application.dto import BatchReport
from ro_dou_ner.application.ports import (
    Chunker,
    EnrichmentRepository,
    EntityExtractor,
    PublicationSource,
    ResultProjector,
    TextPreparer,
)
from ro_dou_ner.domain import (
    CanonicalDocument,
    EnrichmentResult,
    Mention,
    PipelineSpec,
    Publication,
    PublicationBatch,
    TextChunk,
    consolidate,
    globalize,
    idempotency_key,
)

logger = logging.getLogger(__name__)


class EnrichPublications:
    def __init__(
        self,
        source: PublicationSource,
        preparer: TextPreparer,
        chunker: Chunker,
        extractors: Iterable[EntityExtractor],
        repository: EnrichmentRepository,
        pipeline: PipelineSpec,
        projector: ResultProjector | None = None,
        whole_document_extractors: Iterable[EntityExtractor] = (),
    ) -> None:
        self.source = source
        self.preparer = preparer
        self.chunker = chunker
        self.extractors = tuple(extractors)
        self.repository = repository
        self.pipeline = deepcopy(pipeline)
        self.projector = projector
        self.whole_document_extractors = tuple(whole_document_extractors)

    def execute(self, batch: PublicationBatch) -> BatchReport:
        report = BatchReport()
        # Source iteration errors are batch-level errors: no publication exists to
        # associate them with, and callers must receive the failed source read.
        for publication in self.source.iter_publications(batch):
            self._enrich(publication, report)
        logger.info(
            "enrichment batch completed",
            extra={
                "processed": report.processed,
                "skipped": report.skipped,
                "failed": report.failed,
                "projection_failed": report.projection_failed,
            },
        )
        return report

    def _error(self, publication_id: str, stage: str, error: Exception, report: BatchReport) -> str:
        # Adapter exception messages can contain DSNs, request credentials or
        # publication contents. Only a stable exception type crosses this boundary.
        safe_error = f"{stage}: {type(error).__name__}"
        report.errors.append(
            {"publication_id": publication_id, "stage": stage, "error": safe_error}
        )
        logger.error(
            "enrichment failure",
            extra={
                "publication_id": publication_id,
                "stage": stage,
                "error_type": type(error).__name__,
            },
        )
        return safe_error

    def _project(self, result: EnrichmentResult, report: BatchReport) -> None:
        if self.projector is None:
            return
        try:
            self.projector.project(result)
        except Exception as error:
            report.projection_failed += 1
            self._error(result.publication_id, "projection", error, report)

    def _enrich(self, publication: Publication, report: BatchReport) -> None:
        stage = "preparation"
        outcome_recorded = False
        try:
            document = self.preparer.prepare(publication)
            if document.publication_id != publication.publication_id:
                raise ValueError("preparation changed publication identity")
            # Snapshot mutable nested configuration before inference starts so
            # both the hash and persisted provenance describe the same run.
            pipeline = deepcopy(self.pipeline)
            version = pipeline.version
            key = idempotency_key(document.publication_id, document.source_revision, version)
            stage = "claim"
            with self.repository.claim(key) as acquired:
                if not acquired:
                    report.skipped += 1
                    return
                # All run transitions, including failures, finish before releasing
                # this claim. A retry must never observe our unfinished attempt.
                self._run_claimed(document, pipeline, version, key, report)
                outcome_recorded = True
        except Exception as error:
            if not outcome_recorded:
                report.failed += 1
            self._error(publication.publication_id, stage, error, report)

    def _run_claimed(
        self,
        document: CanonicalDocument,
        pipeline: PipelineSpec,
        version: str,
        key: str,
        report: BatchReport,
    ) -> None:
        run_id: str | None = None
        stage = "lookup"
        try:
            existing = self.repository.get(key)
            if existing is not None:
                report.skipped += 1
                self._project(existing, report)
                return
            stage = "start_run"
            run_id = self.repository.start_run(
                document.publication_id, document.source_revision, version, pipeline.model
            )
            stage = "extraction"
            mentions = self._extract(document, pipeline)
            stage = "validation"
            priority = pipeline.configuration.get("extractor_priority", ("rules", "gliner"))
            result = EnrichmentResult(
                publication_id=document.publication_id,
                source_revision=document.source_revision,
                pipeline_version=version,
                taxonomy_version=pipeline.taxonomy_version,
                model=pipeline.model,
                body_text=document.body_text,
                mentions=consolidate(
                    mentions, document.body_text, pipeline.labels, tuple(priority)
                ),
                completed_at=datetime.now(UTC),
                metadata=document.metadata,
                pipeline_config=asdict(pipeline),
            )
            stage = "save"
            self.repository.save(result, run_id)
        except Exception as error:
            report.failed += 1
            safe_error = self._error(document.publication_id, stage, error, report)
            if run_id is not None:
                try:
                    self.repository.fail_run(run_id, safe_error)
                except Exception as persistence_error:
                    self._error(document.publication_id, "fail_run", persistence_error, report)
            return
        report.processed += 1
        self._project(result, report)

    def _extract(self, document: CanonicalDocument, pipeline: PipelineSpec) -> list[Mention]:
        mentions: list[Mention] = []
        whole = TextChunk(0, len(document.body_text), document.body_text)
        for extractor in self.whole_document_extractors:
            mentions.extend(
                globalize(candidate, whole, pipeline.labels)
                for candidate in extractor.extract(whole)
            )
        # Verify every chunk and complete coverage even when an adapter provides
        # malformed chunks. No silent truncation is permitted at this boundary.
        covered_until = 0
        for chunk in self.chunker.chunk(document):
            if (
                chunk.end > len(document.body_text)
                or chunk.text != document.body_text[chunk.start : chunk.end]
            ):
                raise ValueError("chunk does not match canonical document")
            if chunk.start > covered_until or (document.body_text and chunk.start == chunk.end):
                raise ValueError("chunking leaves a document gap")
            covered_until = max(covered_until, chunk.end)
            for extractor in self.extractors:
                mentions.extend(
                    globalize(candidate, chunk, pipeline.labels)
                    for candidate in extractor.extract(chunk)
                )
        if covered_until != len(document.body_text):
            raise ValueError("chunking silently truncated the document")
        return mentions
