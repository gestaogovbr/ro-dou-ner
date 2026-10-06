from copy import deepcopy
from unittest.mock import Mock

import pytest

from ro_dou_ner.adapters.search.opensearch import DEFAULT_INDEX, OpenSearchPublicationReader
from ro_dou_ner.application.ports import PaginationWindowExceeded


@pytest.fixture
def client():
    value = Mock()
    value.indices.get_settings.return_value = {
        DEFAULT_INDEX: {"defaults": {"index": {"max_result_window": "10000"}}}
    }
    value.search.return_value = {"hits": {"total": {"value": 0, "relation": "eq"}, "hits": []}}
    return value


def test_preserves_full_document_and_requests_exact_total_with_unique_order(client):
    document = {
        "publication_id": "inlabs:42",
        "body_text": "😀 Maria Silva",
        "mentions": [{"label": "PERSON", "surface": "Maria Silva", "start": 2, "end": 13}],
        "metadata": {"titulo": "Ato", "texto": "<p>Texto integral</p>"},
        "future_field": {"embedding": [0.1, 0.2]},
    }
    original = deepcopy(document)
    client.search.return_value = {
        "hits": {
            "total": {"value": 25, "relation": "eq"},
            "hits": [{"_id": "key", "_source": document}],
        }
    }
    data = OpenSearchPublicationReader(client=client).list_publications(2, 10).to_dict()
    assert data == {
        "items": [{"id": "key", "document": original}],
        "total": 25,
        "page": 2,
        "page_size": 10,
        "total_pages": 3,
        "has_next": True,
        "has_previous": True,
    }
    assert document == original
    client.search.assert_called_once_with(
        index=DEFAULT_INDEX,
        body={
            "from": 10,
            "size": 10,
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
    client.index.assert_not_called()
    client.indices.create.assert_not_called()


@pytest.mark.parametrize(
    "page,total,expected",
    [
        (1, 0, (0, False, False)),
        (1, 1, (1, False, False)),
        (1, 11, (2, True, False)),
        (2, 20, (2, False, True)),
        (3, 20, (2, False, True)),
    ],
)
def test_empty_last_and_past_last_page_metadata(client, page, total, expected):
    client.search.return_value["hits"]["total"]["value"] = total
    result = OpenSearchPublicationReader(client=client).list_publications(page, 10).to_dict()
    assert result["items"] == []
    assert (result["total_pages"], result["has_next"], result["has_previous"]) == expected


@pytest.mark.parametrize(
    "page,size", [(0, 10), (-1, 10), (1.2, 10), (True, 10), (1, 0), (1, 101), (1, True), (1, 2.5)]
)
def test_invalid_pagination_fails_before_io(client, page, size):
    with pytest.raises(ValueError):
        OpenSearchPublicationReader(client=client).list_publications(page, size)
    client.indices.get_settings.assert_not_called()
    client.search.assert_not_called()


def test_configured_result_window_is_respected(client):
    client.indices.get_settings.return_value[DEFAULT_INDEX]["settings"] = {
        "index": {"max_result_window": "20"}
    }
    reader = OpenSearchPublicationReader(client=client)
    reader.list_publications(2, 10)
    client.search.reset_mock()
    with pytest.raises(PaginationWindowExceeded):
        reader.list_publications(3, 10)
    client.search.assert_not_called()


def test_default_window_boundary(client):
    reader = OpenSearchPublicationReader(client=client)
    reader.list_publications(100, 100)
    with pytest.raises(PaginationWindowExceeded):
        reader.list_publications(101, 100)


@pytest.mark.parametrize("total", [{"value": 10000, "relation": "gte"}, -1, True, "25"])
def test_inexact_or_malformed_count_is_not_reported_as_exact(client, total):
    client.search.return_value["hits"]["total"] = total
    with pytest.raises(RuntimeError):
        OpenSearchPublicationReader(client=client).list_publications()


def test_missing_index_settings_fails(client):
    client.indices.get_settings.return_value = {}
    with pytest.raises(RuntimeError):
        OpenSearchPublicationReader(client=client).list_publications()


@pytest.mark.parametrize("partial", [{"timed_out": True}, {"_shards": {"failed": 1}}])
def test_partial_search_is_not_reported_as_complete(client, partial):
    client.search.return_value.update(partial)
    with pytest.raises(RuntimeError, match="Complete"):
        OpenSearchPublicationReader(client=client).list_publications()


def test_reader_uses_integer_total_returned_by_legacy_search(client):
    client.search.return_value["hits"]["total"] = 25
    assert OpenSearchPublicationReader(client=client).list_publications().total == 25
