from collections.abc import Iterable
from contextlib import AbstractContextManager
from typing import Protocol

from ro_dou_ner.application.dto.publication_page import PublicationPage
from ro_dou_ner.domain import (
    CanonicalDocument,
    EnrichmentResult,
    MentionCandidate,
    ModelInfo,
    Publication,
    PublicationBatch,
    TextChunk,
)


class PublicationSource(Protocol):
    def iter_publications(self, batch: PublicationBatch) -> Iterable[Publication]: ...


class TextPreparer(Protocol):
    def prepare(self, publication: Publication) -> CanonicalDocument: ...


class Chunker(Protocol):
    def chunk(self, document: CanonicalDocument) -> Iterable[TextChunk]: ...


class EntityExtractor(Protocol):
    def extract(self, chunk: TextChunk) -> tuple[MentionCandidate, ...]: ...


class EnrichmentRepository(Protocol):
    def get(self, key: str) -> EnrichmentResult | None: ...
    def get_latest(
        self,
        publication_id: str,
        source_revision: str | None = None,
        pipeline_version: str | None = None,
    ) -> EnrichmentResult | None: ...
    def claim(self, key: str) -> AbstractContextManager[bool]: ...
    def start_run(
        self,
        publication_id: str,
        source_revision: str,
        pipeline_version: str,
        model: ModelInfo | None = None,
    ) -> str: ...
    def save(self, result: EnrichmentResult, run_id: str) -> None: ...
    def fail_run(self, run_id: str, error: str) -> None: ...
    def health(self) -> bool: ...


class ResultProjector(Protocol):
    def project(self, result: EnrichmentResult) -> None: ...


class PaginationWindowExceeded(ValueError):
    """The requested page exceeds the search backend's result window."""


class PublicationReader(Protocol):
    def list_publications(self, page: int, page_size: int) -> PublicationPage: ...
