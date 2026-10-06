from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from ro_dou_ner.adapters.api.app import create_app
from ro_dou_ner.adapters.persistence.memory import InMemoryRepository
from ro_dou_ner.application.dto import IndexedPublication, PublicationPage
from ro_dou_ner.application.ports import PaginationWindowExceeded
from ro_dou_ner.bootstrap.container import create_runtime_app
from ro_dou_ner.bootstrap.settings import Settings


def test_listing_contract_preserves_extra_fields_and_nested_entities():
    reader = Mock()
    document = {
        "body_text": "Maria",
        "mentions": [{"label": "PERSON", "start": 0, "end": 5}],
        "metadata": {"anything": [None, "é"]},
        "future": "<script>secret</script>",
    }
    reader.list_publications.return_value = PublicationPage(
        (IndexedPublication("key", document),), 21, 2, 10
    )
    with TestClient(create_app(InMemoryRepository(), reader)) as client:
        response = client.get("/publications?page=2&page_size=10")
    assert response.status_code == 200
    assert response.json() == {
        "items": [{"id": "key", "document": document}],
        "total": 21,
        "page": 2,
        "page_size": 10,
        "total_pages": 3,
        "has_next": True,
        "has_previous": True,
    }
    reader.list_publications.assert_called_once_with(2, 10)


def test_listing_defaults():
    reader = Mock()
    reader.list_publications.return_value = PublicationPage((), 0, 1, 10)
    with TestClient(create_app(InMemoryRepository(), reader)) as client:
        assert client.get("/publications").json()["total_pages"] == 0
    reader.list_publications.assert_called_once_with(1, 10)


@pytest.mark.parametrize(
    "query",
    ["page=0", "page=-1", "page=abc", "page_size=0", "page_size=101", "page_size=2.5", "page=1.2"],
)
def test_bounds_rejected_without_search(query):
    reader = Mock()
    with TestClient(create_app(InMemoryRepository(), reader)) as client:
        assert client.get("/publications?" + query).status_code == 422
    reader.list_publications.assert_not_called()


@pytest.mark.parametrize(
    "error,status",
    [(ConnectionError("secret-password"), 503), (PaginationWindowExceeded("secret-password"), 422)],
)
def test_backend_errors_sanitized(error, status):
    reader = Mock()
    reader.list_publications.side_effect = error
    with TestClient(create_app(InMemoryRepository(), reader)) as client:
        response = client.get("/publications")
    assert response.status_code == status
    assert "secret" not in response.text


def test_missing_search_configuration_is_explicit():
    with TestClient(create_app(InMemoryRepository())) as client:
        assert client.get("/publications").status_code == 503
        assert client.get("/preview").status_code == 404


def test_preview_is_explicit_opt_in_and_serves_only_configured_directory(tmp_path):
    (tmp_path / "index.html").write_text("<html>temporary preview</html>")
    (tmp_path / "app.js").write_text("console.log('preview')")
    with TestClient(create_app(InMemoryRepository(), preview_directory=tmp_path)) as client:
        response = client.get("/preview")
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        assert "temporary preview" in response.text
        assert client.get("/preview-assets/app.js").status_code == 200
        assert client.get("/preview-assets/%2e%2e/pyproject.toml").status_code == 404
        assert "/preview" not in client.get("/openapi.json").json()["paths"]


def test_preview_missing_entry_point_fails_fast(tmp_path):
    with pytest.raises(ValueError, match="index.html"):
        create_app(InMemoryRepository(), preview_directory=tmp_path)


def test_runtime_wires_search_and_preview_settings(monkeypatch, tmp_path):
    repository = InMemoryRepository()
    reader = Mock()
    reader.list_publications.return_value = PublicationPage((), 0, 1, 10)
    from ro_dou_ner.bootstrap import container

    monkeypatch.setattr(container, "postgres_repository", lambda settings: repository)
    monkeypatch.setattr(container, "opensearch_reader", lambda settings: reader)
    (tmp_path / "index.html").write_text("preview")
    with TestClient(create_runtime_app(Settings(preview_directory=str(tmp_path)))) as client:
        assert client.get("/publications").status_code == 200
        assert client.get("/preview").status_code == 200


def test_preview_setting_reads_environment(monkeypatch):
    monkeypatch.setenv("RO_DOU_NER_PREVIEW_DIRECTORY", "/tmp/preview")
    assert Settings.from_environment().preview_directory == "/tmp/preview"
