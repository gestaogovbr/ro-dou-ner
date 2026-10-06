from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class Publication:
    publication_id: str
    body_text: str
    metadata: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.publication_id, str) or not self.publication_id:
            raise ValueError("publication_id must be a nonempty string")
        if not isinstance(self.body_text, str):
            raise ValueError("body_text must be a string")


@dataclass(frozen=True)
class PublicationBatch:
    reference_date: date | None = None
    publication_ids: tuple[str, ...] = ()
    page_size: int = 500

    def __post_init__(self) -> None:
        if (
            isinstance(self.page_size, bool)
            or not isinstance(self.page_size, int)
            or self.page_size < 1
        ):
            raise ValueError("page_size must be a positive integer")
        if self.reference_date is not None and type(self.reference_date) is not date:
            raise ValueError("reference_date must be a date")
        if any(not isinstance(item, str) or not item for item in self.publication_ids):
            raise ValueError("publication_ids must contain nonempty strings")


@dataclass(frozen=True)
class CanonicalDocument:
    publication_id: str
    body_text: str
    source_revision: str
    metadata: dict = field(default_factory=dict)


@dataclass(frozen=True)
class TextChunk:
    start: int
    end: int
    text: str

    def __post_init__(self) -> None:
        if type(self.start) is not int or type(self.end) is not int:
            raise ValueError("chunk offsets must be integers")
        if self.start < 0 or self.end < self.start or self.end - self.start != len(self.text):
            raise ValueError("chunk offsets must match its text")
