from dataclasses import dataclass, field

from .publication_page import IndexedPublication, PublicationPage

__all__ = ["BatchReport", "IndexedPublication", "PublicationPage"]


@dataclass
class BatchReport:
    processed: int = 0
    skipped: int = 0
    failed: int = 0
    projection_failed: int = 0
    errors: list[dict[str, str]] = field(default_factory=list)

    @property
    def total(self) -> int:
        return self.processed + self.skipped + self.failed
