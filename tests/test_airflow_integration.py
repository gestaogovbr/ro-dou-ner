"""Carregamento da DAG e execução do callable usando o pacote transferido."""

import runpy
import sys
from pathlib import Path
from types import ModuleType
from unittest.mock import MagicMock

import pytest

pytest.importorskip("airflow")


def test_dag_loads_and_uses_migrated_enricher(monkeypatch):
    from ro_dou_enrichment import gliner_enrichment

    root = Path(__file__).resolve().parents[1]
    # Tests may run from /tmp while the DAG is mounted in the Airflow dags folder.
    dag_path = root / "dag" / "ro_dou_inlabs_gliner_enrich_dag.py"
    if not dag_path.exists():
        dag_path = Path("/opt/airflow/dags/ro_dou_enrichment_dags/ro_dou_inlabs_gliner_enrich_dag.py")
    dag = runpy.run_path(str(dag_path))["dag"]
    assert dag.dag_id == "ro-dou_inlabs_gliner_enrich"
    assert dag.get_task("check_if_enabled").downstream_task_ids == {"get_reference_dates"}
    assert dag.get_task("get_reference_dates").downstream_task_ids == {"enrich_entities"}

    client_module = ModuleType("ro_dou_src.utils.open_search.client_open_search")
    client_module.OpenSearchClient = MagicMock()
    config_module = ModuleType("ro_dou_src.utils.open_search.config")
    config_module.INDEX_NAME = "dou"
    monkeypatch.setitem(sys.modules, client_module.__name__, client_module)
    monkeypatch.setitem(sys.modules, config_module.__name__, config_module)
    monkeypatch.setattr("airflow.sdk.Variable.get", lambda key, default="": default)
    service = MagicMock()
    enricher = MagicMock()
    enricher.return_value.run.return_value = {"processed": 2}
    monkeypatch.setattr(gliner_enrichment, "GlinerServiceClient", service)
    monkeypatch.setattr(gliner_enrichment, "GlinerEnricher", enricher)

    result = dag.get_task("enrich_entities").python_callable(["2026-09-29"])
    assert result == {"2026-09-29": {"processed": 2}}
    enricher.return_value.run.assert_called_once_with("2026-09-29")
    enricher.assert_called_once_with(
        client=client_module.OpenSearchClient.return_value.get_client.return_value,
        service=service.return_value,
        index="dou",
    )
