"""Full read-only INLABS -> extraction -> durable storage -> search -> HTTP contract."""

import os
from datetime import date
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg.conninfo import conninfo_to_dict

from ro_dou_ner.adapters.api.app import create_app
from ro_dou_ner.adapters.persistence.postgres import PostgresEnrichmentRepository
from ro_dou_ner.adapters.search.opensearch import OpenSearchProjector
from ro_dou_ner.adapters.sources.inlabs import InlabsPublicationSource
from ro_dou_ner.bootstrap.container import build_processor
from ro_dou_ner.bootstrap.settings import Settings
from ro_dou_ner.domain import PublicationBatch

pytestmark = pytest.mark.integration


def test_complete_inlabs_pipeline_revisions_projections_and_api():
    dsn = os.getenv("RO_DOU_NER_TEST_POSTGRES_DSN")
    url = os.getenv("RO_DOU_NER_TEST_OPENSEARCH_URL")
    if not dsn or not url:
        pytest.skip("Set both isolated backend test variables for complete integration")
    assert "test" in conninfo_to_dict(dsn).get("dbname", "").lower()
    article_id = int(uuid4().hex[:13], 16)
    publication_id = f"inlabs:{article_id}"
    repository = PostgresEnrichmentRepository(dsn)
    repository.initialize()
    projector = OpenSearchProjector(url, index="ro-dou-ner-test-" + uuid4().hex, refresh=True)
    projector.initialize()
    original = (
        "<p>Licitação conforme Lei nº 14.133/2021.</p><p>"
        + "Texto íntegro com acentos. " * 100
        + "</p><p>Em 06/10/2026, valor R$ 1.234,56.</p>"
    )
    try:
        with psycopg.connect(dsn) as connection:
            connection.execute("CREATE SCHEMA IF NOT EXISTS dou_inlabs")
            connection.execute(
                "CREATE TABLE IF NOT EXISTS dou_inlabs.article_raw (id BIGINT PRIMARY KEY, texto TEXT, pubdate TIMESTAMP)"
            )
            connection.execute(
                "INSERT INTO dou_inlabs.article_raw (id, texto, pubdate) VALUES (%s,%s,%s)",
                (article_id, original, date(2026, 10, 6)),
            )
        source = InlabsPublicationSource(dsn)
        processor = build_processor(
            Settings(max_chars=120, overlap=35), source, repository, projector
        )
        batch = PublicationBatch(publication_ids=(publication_id,), page_size=1)
        report = processor.execute(batch)
        assert (report.processed, report.failed, report.projection_failed) == (1, 0, 0)
        first = repository.get_latest(publication_id)
        assert len(first.body_text) > processor.chunker.max_chars
        assert any(mention.surface == "R$ 1.234,56" for mention in first.mentions)
        assert len(projector.search_entities("MONEY", "R$ 1.234,56")) == 1
        assert processor.execute(batch).skipped == 1
        with psycopg.connect(dsn) as connection:
            assert (
                connection.execute(
                    "SELECT texto FROM dou_inlabs.article_raw WHERE id=%s", (article_id,)
                ).fetchone()[0]
                == original
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM ro_dou_ner.enrichment_runs WHERE publication_id=%s",
                    (publication_id,),
                ).fetchone()[0]
                == 1
            )
            # Simulate an upstream correction, independently of the enrichment service.
            connection.execute(
                "UPDATE dou_inlabs.article_raw SET texto=%s WHERE id=%s",
                (original + "<p>Portaria nº 9/2026.</p>", article_id),
            )
        assert processor.execute(batch).processed == 1
        second = repository.get_latest(publication_id)
        assert second.source_revision != first.source_revision
        revised_pipeline = build_processor(
            Settings(max_chars=150, overlap=35), source, repository, projector
        )
        assert revised_pipeline.execute(batch).processed == 1
        latest = repository.get_latest(publication_id)
        assert latest.pipeline_version != first.pipeline_version
        assert len(projector.search_entities("MONEY", "R$ 1.234,56")) == 3
        with TestClient(create_app(repository)) as client:
            assert client.get("/health").status_code == 200
            response = client.get(f"/publications/{publication_id}/enrichment")
            assert response.json() == latest.to_dict()
            for mention in response.json()["mentions"]:
                assert latest.body_text[mention["start"] : mention["end"]] == mention["surface"]
            historical = client.get(
                f"/publications/{publication_id}/enrichment",
                params={
                    "source_revision": first.source_revision,
                    "pipeline_version": first.pipeline_version,
                },
            )
            assert historical.json() == first.to_dict()
    finally:
        projector.client.indices.delete(index=projector.index, ignore=[404])
        projector.client.close()
        with psycopg.connect(dsn) as connection:
            connection.execute(
                "DELETE FROM ro_dou_ner.publication_enrichments WHERE publication_id=%s",
                (publication_id,),
            )
            connection.execute(
                "DELETE FROM ro_dou_ner.enrichment_runs WHERE publication_id=%s", (publication_id,)
            )
            connection.execute("DELETE FROM dou_inlabs.article_raw WHERE id=%s", (article_id,))
