"""Real PostgreSQL tests; opt in only with an explicitly named test database."""

import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import UTC, date, datetime
from hashlib import sha256
from threading import Event
from types import SimpleNamespace
from uuid import uuid4

import psycopg
import pytest
from psycopg.conninfo import conninfo_to_dict

from ro_dou_ner.adapters.persistence.postgres import PostgresEnrichmentRepository
from ro_dou_ner.adapters.sources.inlabs import InlabsPublicationSource
from ro_dou_ner.domain import EnrichmentResult, ModelInfo, PublicationBatch, source_revision

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def postgres_dsn():
    dsn = os.environ.get("RO_DOU_NER_TEST_POSTGRES_DSN")
    if not dsn:
        pytest.skip("Set RO_DOU_NER_TEST_POSTGRES_DSN to run real PostgreSQL integration tests")
    if "test" not in conninfo_to_dict(dsn).get("dbname", "").lower():
        pytest.fail(
            "Integration tests require a database name containing 'test'; refusing a production database"
        )
    # An explicitly configured but broken test service is a failure, never a skip.
    with psycopg.connect(dsn, connect_timeout=5) as connection:
        connection.execute("SELECT 1")
    return dsn


@pytest.fixture
def repository(postgres_dsn):
    repository = PostgresEnrichmentRepository(postgres_dsn)
    repository.initialize()
    prefix = f"inlabs:test-{uuid4().hex}"
    yield repository, prefix
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute(
            "DELETE FROM ro_dou_ner.publication_enrichments WHERE publication_id = %s", (prefix,)
        )
        connection.execute(
            "DELETE FROM ro_dou_ner.enrichment_runs WHERE publication_id = %s", (prefix,)
        )


def result(publication_id, revision="source-v1", pipeline="pipeline-v1"):
    return EnrichmentResult(
        publication_id=publication_id,
        source_revision=revision,
        pipeline_version=pipeline,
        taxonomy_version="taxonomy-v1",
        model=ModelInfo("rules", "deterministic", "rules-v1"),
        body_text="Texto canônico íntegro: João.",
        mentions=(),
        completed_at=datetime.now(UTC),
        metadata={"titulo": "Nomeação", "normalization_version": "v1"},
    )


def persist(repository, item):
    with repository.claim(item.idempotency_key) as acquired:
        assert acquired
        run_id = repository.start_run(
            item.publication_id, item.source_revision, item.pipeline_version
        )
        repository.save(item, run_id)
    return run_id


def test_roundtrip_filters_revisions_and_utc_timestamps(repository, postgres_dsn):
    repo, publication_id = repository
    first = result(publication_id)
    first_run = persist(repo, first)
    assert repo.get(first.idempotency_key) == first
    assert repo.get("unknown") is None
    assert repo.get_latest("unknown") is None
    second = result(publication_id, revision="source-v2")
    persist(repo, second)
    third = result(publication_id, revision="source-v2", pipeline="pipeline-v2")
    persist(repo, third)
    assert repo.get_latest(publication_id) == third
    assert repo.get_latest(publication_id, source_revision="source-v1") == first
    assert repo.get_latest(publication_id, pipeline_version="pipeline-v1") == second
    assert (
        repo.get_latest(publication_id, source_revision="source-v1", pipeline_version="pipeline-v2")
        is None
    )
    with psycopg.connect(postgres_dsn) as connection:
        run = connection.execute(
            "SELECT status, started_at, finished_at, model, error FROM ro_dou_ner.enrichment_runs WHERE run_id = %s",
            (first_run,),
        ).fetchone()
    assert run[0] == "succeeded"
    assert run[1].tzinfo is not None and run[2] >= run[1]
    assert run[3]["revision"] == "rules-v1"
    assert run[4] is None
    assert repo.health()


def test_logical_result_not_overwritten_by_duplicate_attempt(repository, postgres_dsn):
    repo, publication_id = repository
    first = result(publication_id)
    persist(repo, first)
    persist(repo, replace(first, metadata={"attempt": "duplicate"}))
    assert repo.get(first.idempotency_key) == first
    with psycopg.connect(postgres_dsn) as connection:
        count = connection.execute(
            "SELECT count(*) FROM ro_dou_ner.publication_enrichments WHERE publication_id = %s",
            (publication_id,),
        ).fetchone()[0]
    assert count == 1


def test_atomic_save_rolls_back_run_if_result_insert_fails(repository, postgres_dsn):
    repo, publication_id = repository
    item = result(publication_id)
    run_id = repo.start_run(publication_id, item.source_revision, item.pipeline_version)
    invalid_payload = item.to_dict()
    invalid_payload["taxonomy_version"] = None
    invalid = SimpleNamespace(
        publication_id=item.publication_id,
        source_revision=item.source_revision,
        pipeline_version=item.pipeline_version,
        idempotency_key=item.idempotency_key,
        to_dict=lambda: invalid_payload,
    )
    with pytest.raises(psycopg.errors.NotNullViolation):
        repo.save(invalid, run_id)
    assert repo.get(item.idempotency_key) is None
    with psycopg.connect(postgres_dsn) as connection:
        status, finished = connection.execute(
            "SELECT status, finished_at FROM ro_dou_ner.enrichment_runs WHERE run_id = %s",
            (run_id,),
        ).fetchone()
    assert (status, finished) == ("running", None)


def test_failed_attempt_retry_and_stale_crash_recovery(repository, postgres_dsn):
    repo, publication_id = repository
    item = result(publication_id)
    with repo.claim(item.idempotency_key):
        failed = repo.start_run(publication_id, item.source_revision, item.pipeline_version)
        repo.fail_run(failed, "extractor_failed:RetryableError")
    with repo.claim(item.idempotency_key):
        stale = repo.start_run(publication_id, item.source_revision, item.pipeline_version)
        # Leave durable running row as a terminated worker would.
    complete = persist(repo, item)
    with psycopg.connect(postgres_dsn) as connection:
        rows = dict(
            connection.execute(
                "SELECT run_id::text, status FROM ro_dou_ner.enrichment_runs WHERE publication_id = %s",
                (publication_id,),
            ).fetchall()
        )
    assert rows == {failed: "failed", stale: "abandoned", complete: "succeeded"}
    assert repo.get(item.idempotency_key) == item


def test_claim_excludes_other_workers_and_releases_after_failure(repository):
    repo, publication_id = repository
    key = result(publication_id).idempotency_key

    def competing_claim():
        with repo.claim(key) as acquired:
            return acquired

    with pytest.raises(RuntimeError, match="simulated"):
        with repo.claim(key) as acquired:
            assert acquired
            with ThreadPoolExecutor(max_workers=1) as executor:
                assert executor.submit(competing_claim).result(timeout=10) is False
            raise RuntimeError("simulated worker failure")
    assert competing_claim() is True


def test_server_terminated_lock_session_can_be_claimed_again(repository, postgres_dsn):
    repo, publication_id = repository
    key = result(publication_id).idempotency_key
    lock_id = int.from_bytes(sha256(key.encode()).digest()[:8], "big", signed=True)
    with psycopg.connect(postgres_dsn, autocommit=True) as worker:
        worker.execute("SELECT pg_advisory_lock(%s)", (lock_id,))
        pid = worker.info.backend_pid
        with repo.claim(key) as acquired:
            assert acquired is False
        with psycopg.connect(postgres_dsn, autocommit=True) as admin:
            assert admin.execute("SELECT pg_terminate_backend(%s)", (pid,)).fetchone()[0]
        with repo.claim(key) as acquired:
            assert acquired is True


def test_save_rejects_wrong_attempt_identity_and_preserves_results(repository):
    repo, publication_id = repository
    first = result(publication_id)
    persist(repo, first)
    run_id = repo.start_run(publication_id, "source-v2", first.pipeline_version)
    with pytest.raises(ValueError, match="does not match"):
        repo.save(first, run_id)
    assert repo.get(first.idempotency_key) == first


def test_failed_attempt_retains_model_and_failure_cannot_change_success(repository, postgres_dsn):
    repo, publication_id = repository
    item = result(publication_id)
    failed = repo.start_run(publication_id, item.source_revision, item.pipeline_version, item.model)
    repo.fail_run(failed, "extractor_failed:TimeoutError")
    with psycopg.connect(postgres_dsn) as connection:
        model, status, error = connection.execute(
            "SELECT model, status, error FROM ro_dou_ner.enrichment_runs WHERE run_id = %s",
            (failed,),
        ).fetchone()
    assert model == {"provider": "rules", "model_id": "deterministic", "revision": "rules-v1"}
    assert status == "failed"
    assert error == "extractor_failed:TimeoutError"
    succeeded = persist(repo, item)
    repo.fail_run(succeeded, "late error")
    with psycopg.connect(postgres_dsn) as connection:
        status = connection.execute(
            "SELECT status FROM ro_dou_ner.enrichment_runs WHERE run_id = %s", (succeeded,)
        ).fetchone()[0]
    assert status == "succeeded"


def test_concurrent_processing_has_one_attempt_and_one_logical_effect(repository, postgres_dsn):
    repo, publication_id = repository
    item = result(publication_id)
    ready = Event()
    finish = Event()

    def first_worker():
        with repo.claim(item.idempotency_key) as acquired:
            assert acquired
            run_id = repo.start_run(publication_id, item.source_revision, item.pipeline_version)
            ready.set()
            assert finish.wait(timeout=15)
            repo.save(item, run_id)

    def competing_worker():
        with repo.claim(item.idempotency_key) as acquired:
            if acquired:
                run_id = repo.start_run(publication_id, item.source_revision, item.pipeline_version)
                repo.save(item, run_id)
            return acquired

    with ThreadPoolExecutor(max_workers=5) as executor:
        first = executor.submit(first_worker)
        try:
            assert ready.wait(timeout=10)
            competitors = [executor.submit(competing_worker) for _ in range(4)]
            assert [worker.result(timeout=10) for worker in competitors] == [False] * 4
        finally:
            finish.set()
        first.result(timeout=10)
    with psycopg.connect(postgres_dsn) as connection:
        assert (
            connection.execute(
                "SELECT count(*) FROM ro_dou_ner.enrichment_runs WHERE publication_id = %s",
                (publication_id,),
            ).fetchone()[0]
            == 1
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM ro_dou_ner.publication_enrichments WHERE publication_id = %s",
                (publication_id,),
            ).fetchone()[0]
            == 1
        )


@pytest.fixture
def inlabs_rows(postgres_dsn):
    # Same schema as Ro-dou/dag_load_inlabs/sql/init-db.sql. Own inserted IDs are
    # removed afterward; fixtures never truncate an upstream or enrichment table.
    ddl = """
    CREATE SCHEMA IF NOT EXISTS dou_inlabs;
    CREATE TABLE IF NOT EXISTS dou_inlabs.article_raw (
        id BIGINT PRIMARY KEY, name TEXT, idoficio BIGINT, pubname TEXT,
        arttype TEXT, pubdate TIMESTAMP WITHOUT TIME ZONE, artclass TEXT,
        artcategory TEXT, artsize BIGINT, artnotes TEXT, numberpage BIGINT,
        pdfpage TEXT, editionnumber TEXT, highlighttype TEXT,
        highlightpriority FLOAT, highlight TEXT, highlightimage TEXT,
        highlightimagename TEXT, idmateria BIGINT, midias TEXT, identifica TEXT,
        data TEXT, ementa TEXT, titulo TEXT, subtitulo TEXT, texto TEXT, assina TEXT
    );
    """
    base = uuid4().int % (2**60)
    ids = [base + i for i in range(5)]
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute(ddl)
        for index, article_id in enumerate(ids):
            connection.execute(
                "INSERT INTO dou_inlabs.article_raw (id, pubdate, titulo, texto, pubname) VALUES (%s, %s, %s, %s, %s)",
                (
                    article_id,
                    datetime(2026, 10, 6 if index < 4 else 7),
                    "Título íntegro",
                    "<p>João &amp; Maria.</p>",
                    "DOU1",
                ),
            )
    yield ids
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute("DELETE FROM dou_inlabs.article_raw WHERE id = ANY(%s)", (ids,))


def test_inlabs_real_keyset_date_ids_and_source_remain_unchanged(postgres_dsn, inlabs_rows):
    source = InlabsPublicationSource(postgres_dsn)
    ids = tuple(f"inlabs:{item}" for item in reversed(inlabs_rows))
    publications = list(
        source.iter_publications(PublicationBatch(date(2026, 10, 6), ids, page_size=2))
    )
    assert [item.publication_id for item in publications] == [
        f"inlabs:{item}" for item in inlabs_rows[:4]
    ]
    assert all(item.body_text == "<p>João &amp; Maria.</p>" for item in publications)
    assert source.health()
    original = publications[0]
    original_revision = source_revision(original.body_text, original.metadata)
    with psycopg.connect(postgres_dsn) as connection:
        connection.execute(
            "UPDATE dou_inlabs.article_raw SET titulo = 'Novo título' WHERE id = %s",
            (inlabs_rows[0],),
        )
    (changed,) = source.iter_publications(
        PublicationBatch(publication_ids=(original.publication_id,))
    )
    assert source_revision(changed.body_text, changed.metadata) != original_revision
    assert changed.body_text == original.body_text
