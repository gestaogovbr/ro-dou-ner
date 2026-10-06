"""Real OpenSearch wire behavior; each test owns and deletes one unique index."""

import os
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import pytest

from ro_dou_ner.adapters.search.opensearch import OpenSearchProjector, OpenSearchPublicationReader
from ro_dou_ner.application.ports import PaginationWindowExceeded
from ro_dou_ner.domain import EnrichmentResult, Mention, ModelInfo

pytestmark = pytest.mark.integration


@pytest.fixture
def projector():
    url = os.environ.get("RO_DOU_NER_TEST_OPENSEARCH_URL")
    if not url:
        pytest.skip("Set RO_DOU_NER_TEST_OPENSEARCH_URL for real OpenSearch integration")
    opensearchpy = pytest.importorskip("opensearchpy")
    client = opensearchpy.OpenSearch(hosts=[url])
    index = f"ro-dou-ner-test-{uuid4().hex}"
    adapter = OpenSearchProjector(client=client, index=index, refresh=True)
    try:
        adapter.initialize()
        yield adapter
    finally:
        # Never delete any index other than the random one generated above.
        client.indices.delete(index=index, ignore=[404])
        client.close()


def mention(label, surface, start):
    return Mention(label, surface, start, start + len(surface), 0.9, "fixture")


def result(*, publication="inlabs:1", revision="revision-a", pipeline="pipeline-a", mentions=None):
    return EnrichmentResult(
        publication_id=publication,
        source_revision=revision,
        pipeline_version=pipeline,
        taxonomy_version="v1",
        body_text="Maria Silva e João Silva",
        completed_at=datetime(2026, 10, 6, 12, tzinfo=UTC),
        model=ModelInfo(provider="fixture", model_id="test", revision="v1"),
        mentions=tuple(mentions or [mention("PERSON", "Maria Silva", 0)]),
    )


def test_nested_query_excludes_cross_mention_false_positive(projector):
    correct = result(publication="inlabs:correct")
    false_positive = result(
        publication="inlabs:wrong",
        mentions=[
            mention("ORGANIZATION", "Maria Silva", 0),
            mention("PERSON", "João Silva", 14),
        ],
    )
    projector.project(correct)
    projector.project(false_positive)
    matches = projector.search_entities("PERSON", "Maria Silva")
    assert [item["publication_id"] for item in matches] == ["inlabs:correct"]
    assert matches[0]["body_text"] == correct.to_dict()["body_text"]
    assert projector.search_entities("PERSON", "maria silva") == ()


def test_projection_retry_is_idempotent_and_new_versions_remain(projector):
    first = result()
    revised_document = result(revision="revision-b")
    revised_pipeline = result(pipeline="pipeline-b")
    projector.project(first)
    projector.project(first)
    assert projector.client.count(index=projector.index)["count"] == 1
    projector.project(revised_document)
    projector.project(revised_pipeline)
    matches = projector.search_entities("PERSON", "Maria Silva")
    assert {(item["source_revision"], item["pipeline_version"]) for item in matches} == {
        ("revision-a", "pipeline-a"),
        ("revision-b", "pipeline-a"),
        ("revision-a", "pipeline-b"),
    }
    assert projector.client.count(index=projector.index)["count"] == 3
    projector.initialize()
    assert projector.health()


def test_reader_paginates_versions_in_stable_order_and_preserves_complete_sources(projector):
    first = result(publication="inlabs:1", revision="revision-a")
    newer = replace(
        first, source_revision="revision-b", completed_at=first.completed_at + timedelta(seconds=1)
    )
    tied = replace(newer, pipeline_version="pipeline-b")
    last = result(publication="inlabs:2")
    originals = {}
    for document in (last, tied, first, newer):
        source = document.to_dict()
        source["additional_unmapped_attribute"] = {"arbitrary": [None, "😀", {"value": 42}]}
        originals[document.idempotency_key] = source
        projector.client.index(
            index=projector.index, id=document.idempotency_key, body=source, refresh=True
        )
    reader = OpenSearchPublicationReader(client=projector.client, index=projector.index)
    page_one = reader.list_publications(1, 2).to_dict()
    page_two = reader.list_publications(2, 2).to_dict()
    ids = [item["id"] for item in page_one["items"] + page_two["items"]]
    assert ids == [
        newer.idempotency_key,
        tied.idempotency_key,
        first.idempotency_key,
        last.idempotency_key,
    ]
    assert page_one["total"] == page_two["total"] == 4
    assert page_one["total_pages"] == 2 and page_one["has_next"]
    assert not page_two["has_next"] and page_two["has_previous"]
    assert reader.list_publications(3, 2).items == ()
    for item in page_one["items"] + page_two["items"]:
        assert item["document"] == originals[item["id"]]
    assert reader.list_publications(1, 2).to_dict() == page_one


def test_reader_respects_real_index_result_window(projector):
    projector.client.indices.put_settings(
        index=projector.index, body={"index": {"max_result_window": 2}}
    )
    reader = OpenSearchPublicationReader(client=projector.client, index=projector.index)
    assert reader.list_publications(1, 2).total == 0
    with pytest.raises(PaginationWindowExceeded):
        reader.list_publications(2, 2)
