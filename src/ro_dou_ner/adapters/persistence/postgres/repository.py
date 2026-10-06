"""Durable attempts and one logical result per source and pipeline revision."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict
from hashlib import sha256
from importlib.resources import files
from uuid import uuid4

import psycopg
from psycopg.types.json import Jsonb

from ro_dou_ner.domain import EnrichmentResult, ModelInfo


class PostgresEnrichmentRepository:
    def __init__(self, dsn: str, *, connect_timeout: int = 10) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout

    def _connect(self, *, autocommit: bool = False) -> psycopg.Connection:
        return psycopg.connect(
            self._dsn, connect_timeout=self._connect_timeout, autocommit=autocommit
        )

    def initialize(self) -> None:
        """Explicit, idempotent schema bootstrap; never changes upstream INLABS."""
        schema = files(__package__).joinpath("schema.sql").read_text(encoding="utf-8")
        with self._connect() as connection:
            connection.execute(schema)

    def health(self) -> bool:
        try:
            with self._connect() as connection:
                connection.execute(
                    "SELECT idempotency_key FROM ro_dou_ner.publication_enrichments LIMIT 0"
                )
                connection.execute("SELECT run_id FROM ro_dou_ner.enrichment_runs LIMIT 0")
            return True
        except psycopg.Error:
            return False

    @contextmanager
    def claim(self, key: str) -> Iterator[bool]:
        """A session lock survives commits and is released on connection loss.

        Keep the session open for the complete extraction/save/projection interval;
        competing workers return immediately so orchestration can retry later.
        """
        lock_id = int.from_bytes(sha256(key.encode("utf-8")).digest()[:8], "big", signed=True)
        with self._connect(autocommit=True) as connection:
            acquired = connection.execute("SELECT pg_try_advisory_lock(%s)", (lock_id,)).fetchone()[
                0
            ]
            try:
                yield acquired
            finally:
                if acquired and not connection.closed:
                    connection.execute("SELECT pg_advisory_unlock(%s)", (lock_id,))

    def get(self, key: str) -> EnrichmentResult | None:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT result FROM ro_dou_ner.publication_enrichments WHERE idempotency_key = %s",
                (key,),
            ).fetchone()
        return EnrichmentResult.from_dict(row[0]) if row else None

    def get_latest(
        self,
        publication_id: str,
        source_revision: str | None = None,
        pipeline_version: str | None = None,
    ) -> EnrichmentResult | None:
        clauses = ["publication_id = %s"]
        params = [publication_id]
        if source_revision is not None:
            clauses.append("source_revision = %s")
            params.append(source_revision)
        if pipeline_version is not None:
            clauses.append("pipeline_version = %s")
            params.append(pipeline_version)
        query = (
            "SELECT result FROM ro_dou_ner.publication_enrichments WHERE "
            + " AND ".join(clauses)
            + " ORDER BY created_at DESC, idempotency_key DESC LIMIT 1"
        )
        with self._connect() as connection:
            row = connection.execute(query, params).fetchone()
        return EnrichmentResult.from_dict(row[0]) if row else None

    def start_run(
        self,
        publication_id: str,
        source_revision: str,
        pipeline_version: str,
        model: ModelInfo | None = None,
    ) -> str:
        """Persist an attempt before inference. Call only while holding claim()."""
        run_id = str(uuid4())
        with self._connect() as connection:
            # Once this identity's advisory lock is acquired, an unfinished previous
            # attempt belongs to a worker that lost its session or crashed.
            connection.execute(
                "UPDATE ro_dou_ner.enrichment_runs "
                "SET status = 'abandoned', finished_at = clock_timestamp(), "
                "error = 'Previous worker did not complete the attempt' "
                "WHERE publication_id = %s AND source_revision = %s AND pipeline_version = %s "
                "AND status = 'running'",
                (publication_id, source_revision, pipeline_version),
            )
            connection.execute(
                "INSERT INTO ro_dou_ner.enrichment_runs "
                "(run_id, publication_id, source_revision, pipeline_version, model, status) "
                "VALUES (%s, %s, %s, %s, %s, 'running')",
                (
                    run_id,
                    publication_id,
                    source_revision,
                    pipeline_version,
                    Jsonb(asdict(model)) if model is not None else None,
                ),
            )
        return run_id

    def save(self, result: EnrichmentResult, run_id: str) -> None:
        payload = result.to_dict()
        with self._connect() as connection:
            updated = connection.execute(
                "UPDATE ro_dou_ner.enrichment_runs SET status = 'succeeded', "
                "finished_at = clock_timestamp(), error = NULL, model = %s "
                "WHERE run_id = %s AND publication_id = %s AND source_revision = %s "
                "AND pipeline_version = %s AND status = 'running'",
                (
                    Jsonb(payload.get("model")),
                    run_id,
                    result.publication_id,
                    result.source_revision,
                    result.pipeline_version,
                ),
            )
            if updated.rowcount != 1:
                raise ValueError("Result does not match a running enrichment attempt")
            connection.execute(
                "INSERT INTO ro_dou_ner.publication_enrichments "
                "(idempotency_key, publication_id, source_revision, pipeline_version, "
                "taxonomy_version, validation_status, result, run_id) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (publication_id, source_revision, pipeline_version) DO NOTHING",
                (
                    result.idempotency_key,
                    result.publication_id,
                    result.source_revision,
                    result.pipeline_version,
                    payload["taxonomy_version"],
                    "valid",
                    Jsonb(payload),
                    run_id,
                ),
            )

    def fail_run(self, run_id: str, error: str) -> None:
        """Persist the caller's sanitized error code/message, never a raw exception."""
        with self._connect() as connection:
            connection.execute(
                "UPDATE ro_dou_ner.enrichment_runs SET status = 'failed', "
                "finished_at = clock_timestamp(), error = %s "
                "WHERE run_id = %s AND status = 'running'",
                (error[:2000], run_id),
            )
