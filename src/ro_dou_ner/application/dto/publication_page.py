from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class IndexedPublication:
    id: str
    document: dict[str, Any]


@dataclass(frozen=True)
class PublicationPage:
    items: tuple[IndexedPublication, ...]
    total: int
    page: int
    page_size: int

    def to_dict(self) -> dict[str, Any]:
        total_pages = (self.total + self.page_size - 1) // self.page_size
        return {
            "items": [{"id": item.id, "document": item.document} for item in self.items],
            "total": self.total,
            "page": self.page,
            "page_size": self.page_size,
            "total_pages": total_pages,
            "has_next": self.page < total_pages,
            "has_previous": self.page > 1,
        }
