import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from ro_dou_ner.adapters.api.app import create_app
from ro_dou_ner.adapters.persistence.memory import InMemoryRepository
from ro_dou_ner.bootstrap.cli import main
from ro_dou_ner.bootstrap.container import build_processor
from ro_dou_ner.bootstrap.settings import Settings
from ro_dou_ner.domain import Publication, PublicationBatch


class Source:
    def __init__(self, text="Lei nº 14.133/2021 em 06/10/2026. Valor R$ 1.234,56."):
        self.text = text

    def iter_publications(self, batch):
        return (Publication("inlabs:42", self.text, {"titulo": "Licitação"}),)


def test_process_and_consult_enrichment_and_entities():
    repository = InMemoryRepository()
    report = build_processor(Settings(), Source(), repository).execute(PublicationBatch())
    assert report.processed == 1 and report.failed == 0
    with TestClient(create_app(repository)) as client:
        assert client.get("/health").json() == {"status": "ok"}
        data = client.get("/publications/inlabs:42/enrichment").json()
        assert {mention["label"] for mention in data["mentions"]} == {
            "LEGAL_REFERENCE",
            "DATE",
            "MONEY",
        }
        for mention in data["mentions"]:
            assert data["body_text"][mention["start"] : mention["end"]] == mention["surface"]
        assert data["model"]["provider"] == "rules"
        assert data["pipeline_config"]["normalization_version"]
        entities = client.get("/publications/inlabs:42/entities?label=MONEY").json()
        assert len(entities["mentions"]) == 1
        assert entities["mentions"][0]["surface"] == "R$ 1.234,56"
        assert client.get("/publications/missing/enrichment").status_code == 404


def test_api_version_filters_and_failed_new_revision_preserve_previous():
    repository = InMemoryRepository()
    source = Source()
    processor = build_processor(Settings(), source, repository)
    processor.execute(PublicationBatch())
    previous = repository.get_latest("inlabs:42")
    source.text += " Portaria nº 10/2026."
    processor.execute(PublicationBatch())
    with TestClient(create_app(repository)) as client:
        assert (
            client.get("/publications/inlabs:42/enrichment").json()["source_revision"]
            != previous.source_revision
        )
        old = client.get(
            "/publications/inlabs:42/enrichment",
            params={
                "source_revision": previous.source_revision,
                "pipeline_version": previous.pipeline_version,
            },
        )
        assert old.json() == previous.to_dict()
        assert (
            client.get("/publications/inlabs:42/enrichment?pipeline_version=missing").status_code
            == 404
        )


def test_api_unavailable_is_sanitized():
    class Unavailable:
        def health(self):
            raise ConnectionError("secret-password")

        def get_latest(self, *args):
            raise ConnectionError("secret-password")

    with TestClient(create_app(Unavailable())) as client:
        assert client.get("/health").status_code == 503
        response = client.get("/publications/inlabs:42/enrichment")
        assert response.status_code == 503
        assert "secret" not in response.text


@pytest.fixture
def clean_env(monkeypatch):
    for name in (
        "DATABASE_DSN",
        "INLABS_DSN",
        "OPENSEARCH_URL",
        "OPENSEARCH_INDEX",
        "MODEL_ID",
        "MODEL_REVISION",
        "TOKENIZER_ID",
        "TOKENIZER_REVISION",
        "MODE",
    ):
        monkeypatch.delenv("RO_DOU_NER_" + name, raising=False)


def test_offline_cli_and_benchmark_are_executable(tmp_path, capsys, clean_env):
    source = tmp_path / "input.jsonl"
    output = tmp_path / "result.jsonl"
    source.write_text(
        json.dumps({"publication_id": "inlabs:42", "body_text": Source().text}) + "\n"
    )
    assert main(["enrich-file", str(source), "--output", str(output)]) == 0
    report = json.loads(capsys.readouterr().out)
    assert report["processed"] == 1
    assert len(json.loads(output.read_text())["mentions"]) == 3
    benchmark = tmp_path / "benchmark.json"
    assert (
        main(
            [
                "benchmark",
                str(Path(__file__).parents[1] / "fixtures/evaluation-synthetic.jsonl"),
                "--output",
                str(benchmark),
            ]
        )
        == 0
    )
    metrics = json.loads(benchmark.read_text())
    assert metrics["coverage"]["total_documents"] == 5
    assert metrics["coverage"]["fraction"] == 1
    assert metrics["metadata"]["model"]["provider"] == "rules"
    assert metrics["metadata"]["dataset_sha256"]


def test_cli_missing_database_and_bad_input_fail_without_credentials(tmp_path, clean_env, capsys):
    assert main(["init-db"]) == 1
    assert json.loads(capsys.readouterr().err)["error_type"] == "ValueError"
    assert main(["enrich-file", str(tmp_path / "missing"), "--output", str(tmp_path / "out")]) == 1


def test_settings_versions_hash_all_configuration_but_exclude_credentials(clean_env):
    first = build_processor(Settings(), Source(), InMemoryRepository()).pipeline
    changed = build_processor(Settings(max_chars=800), Source(), InMemoryRepository()).pipeline
    assert first.version != changed.version
    creds = build_processor(
        Settings(database_dsn="secret", inlabs_dsn="other-secret"), Source(), InMemoryRepository()
    ).pipeline
    assert creds.version == first.version
    assert "secret" not in str(first.configuration)
    assert first.configuration["runtime_versions"]["ro-dou-ner"] == "0.1.0"


def test_pipeline_file_taxonomy_load_and_environment_override(clean_env, monkeypatch):
    path = Path(__file__).parents[2] / "configs/pipelines/rules-v1.json"
    settings = Settings.from_environment(str(path))
    assert settings.labels == Settings().labels
    monkeypatch.setenv("RO_DOU_NER_MODE", "hybrid")
    with pytest.raises(ValueError):
        Settings.from_environment(str(path))


def test_empty_optional_environment_matches_host_defaults(clean_env, monkeypatch):
    monkeypatch.setenv("RO_DOU_NER_TOKENIZER_ID", "")
    monkeypatch.setenv("RO_DOU_NER_TOKENIZER_REVISION", "")
    assert Settings.from_environment() == Settings()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"max_chars": 0},
        {"overlap": 700},
        {"threshold": float("nan")},
        {"mode": "generic"},
        {"mode": "hybrid", "model_id": "x", "model_revision": "main"},
        {"labels": ("PERSON", "PERSON")},
        {"labels": ("UNKNOWN",)},
        {"labels": ("PERSON",)},
    ],
)
def test_invalid_settings_fail_fast(kwargs):
    with pytest.raises(ValueError):
        Settings(**kwargs)


def test_hybrid_fingerprint_includes_secondary_tokenizer_revision(monkeypatch):
    monkeypatch.setattr(Settings, "runtime_versions", lambda self: {"gliner": "0.2.29"})
    base = Settings(
        mode="hybrid",
        model_id="urchade/gliner_multi-v2.1",
        model_revision="a" * 40,
        tokenizer_id="microsoft/mdeberta-v3-base",
        tokenizer_revision="b" * 40,
    )
    first = build_processor(base, Source(), InMemoryRepository()).pipeline
    from dataclasses import replace

    second = build_processor(
        replace(base, tokenizer_revision="c" * 40), Source(), InMemoryRepository()
    ).pipeline
    assert first.model == second.model
    assert first.version != second.version
