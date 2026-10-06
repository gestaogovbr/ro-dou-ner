"""Install ro-dou-ner in the task runtime, then copy this file to the DAG directory.

Requires Airflow 2.10+ or 3.x. Credentials are read only inside the task.
"""

from datetime import UTC, datetime, timedelta

try:
    from airflow.sdk import Asset, dag, get_current_context, task
except ImportError:
    from airflow.datasets import Dataset as Asset
    from airflow.decorators import dag, task
    from airflow.operators.python import get_current_context


@dag(
    dag_id="ro_dou_ner_inlabs",
    schedule=Asset("inlabs") | Asset("inlabs_edicao_extra"),
    start_date=datetime(2024, 1, 1, tzinfo=UTC),
    catchup=False,
    max_active_runs=1,
    default_args={"retries": 2, "retry_delay": timedelta(minutes=2)},
    tags=["inlabs", "ner"],
)
def enrichment_dag():
    @task
    def enrich_loaded_publications():
        from ro_dou_ner.adapters.sources.inlabs import InlabsPublicationSource
        from ro_dou_ner.adapters.triggers.airflow import process_events
        from ro_dou_ner.bootstrap.container import (
            build_processor,
            opensearch_projector,
            postgres_repository,
        )
        from ro_dou_ner.bootstrap.logging import configure_logging
        from ro_dou_ner.bootstrap.settings import Settings

        context = get_current_context()
        configure_logging()
        settings = Settings.from_environment()
        if not settings.inlabs_dsn:
            raise ValueError("RO_DOU_NER_INLABS_DSN is required")
        processor = build_processor(
            settings,
            InlabsPublicationSource(settings.inlabs_dsn),
            postgres_repository(settings),
            opensearch_projector(settings),
        )
        events = context.get(
            "triggering_asset_events", context.get("triggering_dataset_events", {})
        )
        manual_date = (context["dag_run"].conf or {}).get("reference_date")
        reports = process_events(events, processor, manual_date)
        return [
            {
                "processed": r.processed,
                "skipped": r.skipped,
                "failed": r.failed,
                "projection_failed": r.projection_failed,
            }
            for r in reports
        ]

    enrich_loaded_publications()


ro_dou_ner_inlabs = enrichment_dag()
