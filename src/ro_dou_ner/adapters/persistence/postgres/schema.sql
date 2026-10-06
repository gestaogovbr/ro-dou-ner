CREATE SCHEMA IF NOT EXISTS ro_dou_ner;

CREATE TABLE IF NOT EXISTS ro_dou_ner.enrichment_runs (
    run_id UUID PRIMARY KEY,
    publication_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    model JSONB,
    status TEXT NOT NULL CHECK (status IN ('running', 'succeeded', 'failed', 'abandoned')),
    started_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    finished_at TIMESTAMPTZ,
    error TEXT,
    CHECK ((status = 'running' AND finished_at IS NULL) OR
           (status <> 'running' AND finished_at IS NOT NULL))
);

CREATE INDEX IF NOT EXISTS enrichment_runs_identity_idx
    ON ro_dou_ner.enrichment_runs (publication_id, source_revision, pipeline_version);

CREATE TABLE IF NOT EXISTS ro_dou_ner.publication_enrichments (
    idempotency_key TEXT PRIMARY KEY,
    publication_id TEXT NOT NULL,
    source_revision TEXT NOT NULL,
    pipeline_version TEXT NOT NULL,
    taxonomy_version TEXT NOT NULL,
    validation_status TEXT NOT NULL,
    result JSONB NOT NULL,
    run_id UUID NOT NULL REFERENCES ro_dou_ner.enrichment_runs(run_id),
    created_at TIMESTAMPTZ NOT NULL DEFAULT clock_timestamp(),
    UNIQUE (publication_id, source_revision, pipeline_version)
);

CREATE INDEX IF NOT EXISTS publication_enrichments_latest_idx
    ON ro_dou_ner.publication_enrichments (publication_id, created_at DESC);
