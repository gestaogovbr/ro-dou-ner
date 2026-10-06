"""Read complete indexed enrichment versions without projecting or modifying data."""

from typing import Any

from ro_dou_ner.application.dto import IndexedPublication, PublicationPage
from ro_dou_ner.application.ports import PaginationWindowExceeded

from .projector import DEFAULT_INDEX, OpenSearchProjector


class OpenSearchPublicationReader:
    def __init__(
        self,
        url: str | None = None,
        *,
        client: Any | None = None,
        index: str = DEFAULT_INDEX,
    ) -> None:
        connection = OpenSearchProjector(url, client=client, index=index)
        self.client = connection.client
        self.index = connection.index

    def list_publications(self, page: int = 1, page_size: int = 10) -> PublicationPage:
        if isinstance(page, bool) or not isinstance(page, int) or page < 1:
            raise ValueError("page must be a positive integer")
        if (
            isinstance(page_size, bool)
            or not isinstance(page_size, int)
            or not 1 <= page_size <= 100
        ):
            raise ValueError("page_size must be an integer between 1 and 100")
        offset = (page - 1) * page_size
        settings = self.client.indices.get_settings(
            index=self.index, name="index.max_result_window", include_defaults=True
        )
        windows = []
        for value in settings.values():
            explicit = value.get("settings", {}).get("index", {})
            defaults = value.get("defaults", {}).get("index", {})
            windows.append(
                int(explicit.get("max_result_window", defaults.get("max_result_window", 10000)))
            )
        if not windows:
            raise RuntimeError("Search index settings unavailable")
        if offset + page_size > min(windows):
            raise PaginationWindowExceeded("Requested page exceeds the OpenSearch result window")
        response = self.client.search(
            index=self.index,
            body={
                "from": offset,
                "size": page_size,
                "track_total_hits": True,
                "query": {"match_all": {}},
                "sort": [
                    {"publication_id": "asc"},
                    {"completed_at": "desc"},
                    {"pipeline_version": "asc"},
                    {"source_revision": "asc"},
                ],
            },
        )
        if response.get("timed_out") or response.get("_shards", {}).get("failed", 0):
            raise RuntimeError("Complete publication search unavailable")
        hits = response["hits"]
        total = hits["total"]
        if isinstance(total, dict):
            if total.get("relation") != "eq":
                raise RuntimeError("Exact publication count unavailable")
            total = total["value"]
        if isinstance(total, bool) or not isinstance(total, int) or total < 0:
            raise RuntimeError("Invalid publication count")
        return PublicationPage(
            items=tuple(IndexedPublication(hit["_id"], hit["_source"]) for hit in hits["hits"]),
            total=total,
            page=page,
            page_size=page_size,
        )
