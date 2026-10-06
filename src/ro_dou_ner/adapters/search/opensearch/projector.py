"""Keep publication versions in a dedicated, explicitly mapped index."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from ro_dou_ner.domain import EnrichmentResult

DEFAULT_INDEX = "ro-dou-ner-publications-v1"

INDEX_MAPPING: dict[str, Any] = {
    "dynamic": False,
    "properties": {
        "idempotency_key": {"type": "keyword"},
        "publication_id": {"type": "keyword"},
        "source_revision": {"type": "keyword"},
        "pipeline_version": {"type": "keyword"},
        "taxonomy_version": {"type": "keyword"},
        "normalization_version": {"type": "keyword"},
        "chunking_version": {"type": "keyword"},
        "body_text": {"type": "text", "index": False},
        "completed_at": {"type": "date"},
        "validation_status": {"type": "keyword"},
        "model": {
            "properties": {
                "provider": {"type": "keyword"},
                "model_id": {"type": "keyword"},
                "revision": {"type": "keyword"},
            }
        },
        "mentions": {
            "type": "nested",
            "properties": {
                "label": {"type": "keyword"},
                "surface": {"type": "keyword"},
                "start": {"type": "integer"},
                "end": {"type": "integer"},
                "score": {"type": "float"},
                "extractor": {"type": "keyword"},
            },
        },
    },
}


class IncompatibleIndexMapping(ValueError):
    """An existing index cannot safely answer the required entity queries."""


class OpenSearchProjector:
    def __init__(
        self,
        url: str | None = None,
        *,
        client: Any | None = None,
        index: str = DEFAULT_INDEX,
        refresh: bool | str = False,
    ) -> None:
        if (
            not index
            or index != index.lower()
            or any(character in index for character in ' \\/*?"<>|,#:')
            or index.startswith(("-", "_", "+"))
            or index in {".", ".."}
        ):
            raise ValueError("A concrete lowercase OpenSearch index name is required")
        if client is None:
            if not url:
                raise ValueError("OpenSearch URL or injected client is required")
            from opensearchpy import OpenSearch

            client = OpenSearch(hosts=[url])
        self.client = client
        self.index = index
        self.refresh = refresh

    def initialize(self) -> None:
        """Create our index, or verify that existing mention fields are nested."""
        if not self.client.indices.exists(index=self.index):
            try:
                self.client.indices.create(
                    index=self.index,
                    body={"mappings": deepcopy(INDEX_MAPPING)},
                )
            except Exception as exc:
                # Another initializer may win the exists/create race. All other
                # errors (permissions, networking, malformed requests) propagate.
                info = getattr(exc, "info", None)
                error = info.get("error") if isinstance(info, dict) else None
                error_type = error.get("type") if isinstance(error, dict) else error
                if error_type != "resource_already_exists_exception":
                    raise
        response = self.client.indices.get_mapping(index=self.index)
        if not response:
            raise IncompatibleIndexMapping("OpenSearch returned no index mapping")
        for index_name, item in response.items():
            mapping = item.get("mappings", {})
            self._validate_properties(
                INDEX_MAPPING["properties"], mapping.get("properties", {}), index_name
            )

    @staticmethod
    def _validate_properties(required: dict[str, Any], actual: dict[str, Any], path: str) -> None:
        for name, specification in required.items():
            existing = actual.get(name, {})
            expected_type = specification.get("type", "object")
            actual_type = existing.get("type", "object" if "properties" in existing else None)
            if expected_type != actual_type:
                raise IncompatibleIndexMapping(
                    f"{path}.{name} must be {expected_type}, found {actual_type}"
                )
            if "properties" in specification:
                OpenSearchProjector._validate_properties(
                    specification["properties"],
                    existing.get("properties", {}),
                    f"{path}.{name}",
                )

    def project(self, result: EnrichmentResult) -> None:
        """Retrying a result replaces its projection; other revisions remain."""
        self.client.index(
            index=self.index,
            id=result.idempotency_key,
            body=result.to_dict(),
            refresh=self.refresh,
        )

    def search_entities(
        self, label: str, surface: str, limit: int = 20
    ) -> tuple[dict[str, Any], ...]:
        """Both exact predicates must match one mention, never separate ones."""
        if not label or not surface:
            raise ValueError("Entity label and surface must be nonempty")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 1000:
            raise ValueError("Search limit must be an integer between 1 and 1000")
        response = self.client.search(
            index=self.index,
            body={
                "size": limit,
                "query": {
                    "nested": {
                        "path": "mentions",
                        "score_mode": "none",
                        "query": {
                            "bool": {
                                "filter": [
                                    {"term": {"mentions.label": label}},
                                    {"term": {"mentions.surface": surface}},
                                ]
                            }
                        },
                    }
                },
            },
        )
        return tuple(hit["_source"] for hit in response["hits"]["hits"])

    def health(self) -> bool:
        return bool(self.client.ping())
