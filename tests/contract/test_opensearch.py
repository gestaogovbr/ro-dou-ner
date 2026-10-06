from copy import deepcopy
from unittest.mock import Mock

import pytest

from ro_dou_ner.adapters.search.opensearch import (
    DEFAULT_INDEX,
    IncompatibleIndexMapping,
    OpenSearchProjector,
)
from ro_dou_ner.adapters.search.opensearch.projector import INDEX_MAPPING


@pytest.fixture
def search_client():
    client = Mock()
    client.indices.exists.return_value = False
    client.indices.get_mapping.return_value = {DEFAULT_INDEX: {"mappings": deepcopy(INDEX_MAPPING)}}
    return client


def test_initialize_creates_explicit_nested_keyword_mapping(search_client):
    projector = OpenSearchProjector(client=search_client)
    projector.initialize()
    search_client.indices.create.assert_called_once_with(
        index=DEFAULT_INDEX, body={"mappings": INDEX_MAPPING}
    )
    mapping = search_client.indices.create.call_args.kwargs["body"]["mappings"]
    assert mapping["properties"]["mentions"]["type"] == "nested"
    assert mapping["properties"]["mentions"]["properties"]["surface"]["type"] == "keyword"
    assert mapping["properties"]["completed_at"]["type"] == "date"


def test_initialize_reuses_compatible_mapping(search_client):
    search_client.indices.exists.return_value = True
    OpenSearchProjector(client=search_client).initialize()
    search_client.indices.create.assert_not_called()


@pytest.mark.parametrize(
    "field,bad_type", [("mentions", "object"), ("surface", "text"), ("label", "text")]
)
def test_existing_incompatible_mapping_rejected(search_client, field, bad_type):
    search_client.indices.exists.return_value = True
    properties = search_client.indices.get_mapping.return_value[DEFAULT_INDEX]["mappings"][
        "properties"
    ]
    if field == "mentions":
        properties[field]["type"] = bad_type
    else:
        properties["mentions"]["properties"][field]["type"] = bad_type
    with pytest.raises(IncompatibleIndexMapping, match=field):
        OpenSearchProjector(client=search_client).initialize()


def test_missing_mapping_rejected(search_client):
    search_client.indices.get_mapping.return_value = {}
    with pytest.raises(IncompatibleIndexMapping, match="no index mapping"):
        OpenSearchProjector(client=search_client).initialize()


def test_concurrent_index_creation_validates_winning_mapping(search_client):
    error = RuntimeError("concurrent creation")
    error.info = {"error": {"type": "resource_already_exists_exception"}}
    search_client.indices.create.side_effect = error
    OpenSearchProjector(client=search_client).initialize()
    search_client.indices.get_mapping.assert_called_once_with(index=DEFAULT_INDEX)


@pytest.mark.parametrize(
    "info", [None, {"error": {"type": "security_exception"}}, {"error": "unavailable"}]
)
def test_other_index_creation_errors_propagate(search_client, info):
    error = RuntimeError("unavailable")
    error.info = info
    search_client.indices.create.side_effect = error
    with pytest.raises(RuntimeError, match="unavailable"):
        OpenSearchProjector(client=search_client).initialize()
    search_client.indices.get_mapping.assert_not_called()


def test_projection_is_stable_and_keeps_complete_result(search_client):
    result = Mock()
    result.idempotency_key = "one-version"
    result.to_dict.return_value = {
        "publication_id": "inlabs:123",
        "body_text": "Maria Silva",
        "mentions": [],
    }
    projector = OpenSearchProjector(client=search_client)
    projector.project(result)
    projector.project(result)
    calls = search_client.index.call_args_list
    assert len(calls) == 2
    assert calls[0] == calls[1]
    assert calls[0].kwargs == {
        "index": DEFAULT_INDEX,
        "id": "one-version",
        "body": result.to_dict.return_value,
        "refresh": False,
    }


def test_search_constrains_label_and_surface_in_single_nested_query(search_client):
    search_client.search.return_value = {
        "hits": {"hits": [{"_source": {"publication_id": "inlabs:123"}}]}
    }
    results = OpenSearchProjector(client=search_client).search_entities("PERSON", "Maria Silva", 5)
    assert results == ({"publication_id": "inlabs:123"},)
    search_client.search.assert_called_once_with(
        index=DEFAULT_INDEX,
        body={
            "size": 5,
            "query": {
                "nested": {
                    "path": "mentions",
                    "score_mode": "none",
                    "query": {
                        "bool": {
                            "filter": [
                                {"term": {"mentions.label": "PERSON"}},
                                {"term": {"mentions.surface": "Maria Silva"}},
                            ]
                        }
                    },
                }
            },
        },
    )


@pytest.mark.parametrize("limit", [0, -1, 1001, 1.2, True])
def test_invalid_search_limit_rejected_without_io(search_client, limit):
    with pytest.raises(ValueError, match="limit"):
        OpenSearchProjector(client=search_client).search_entities("PERSON", "Maria", limit)
    search_client.search.assert_not_called()


@pytest.mark.parametrize("label,surface", [("", "Maria"), ("PERSON", "")])
def test_empty_entity_query_rejected_without_io(search_client, label, surface):
    with pytest.raises(ValueError, match="nonempty"):
        OpenSearchProjector(client=search_client).search_entities(label, surface)
    search_client.search.assert_not_called()


@pytest.mark.parametrize("index", ["", "ALL", "*", "a,b", "a/b", "_private", ".", "a b"])
def test_index_requires_concrete_lowercase_name(search_client, index):
    with pytest.raises(ValueError, match="index name"):
        OpenSearchProjector(client=search_client, index=index)


def test_missing_configuration_fails_before_optional_sdk_import():
    with pytest.raises(ValueError, match="URL or injected client"):
        OpenSearchProjector()


def test_health_reports_client_ping(search_client):
    search_client.ping.return_value = False
    assert OpenSearchProjector(client=search_client).health() is False
