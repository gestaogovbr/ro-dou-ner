from datetime import date, datetime
from unittest.mock import patch

import pytest

from ro_dou_ner.adapters.sources.inlabs import InlabsPublicationSource
from ro_dou_ner.domain import PublicationBatch, source_revision


class FakeConnection:
    def __init__(self, pages):
        self.pages = iter(pages)
        self.calls = []
        self.read_only = False

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def execute(self, query, params):
        assert self.read_only is True
        self.calls.append((query, params))
        rows = next(self.pages)
        return type("Cursor", (), {"fetchall": lambda self: rows})()


def row(article_id, text="<p>Maria &amp; João — Lei nº 8.112/1990.</p>"):
    return {
        "id": article_id,
        "texto": text,
        "pubdate": datetime(2026, 10, 6),
        "titulo": "Título integral",
        "pubname": "DOU1",
        "artcategory": "Ministério",
        "assina": "Maria",
        "highlightpriority": None,
    }


def test_full_html_metadata_and_deterministic_identity():
    first = row(1)
    reordered = dict(reversed(list(first.items())))
    revisions = []
    for record in (first, reordered):
        connection = FakeConnection([[record]])
        with patch(
            "ro_dou_ner.adapters.sources.inlabs.source.psycopg.connect", return_value=connection
        ):
            (publication,) = InlabsPublicationSource("unused").iter_publications(PublicationBatch())
        assert publication.publication_id == "inlabs:1"
        assert publication.body_text == first["texto"]
        assert publication.metadata["pubdate"] == "2026-10-06T00:00:00"
        assert publication.metadata["titulo"] == "Título integral"
        assert "texto" not in publication.metadata
        assert "id" not in publication.metadata
        revisions.append(source_revision(publication.body_text, publication.metadata))
    assert revisions[0] == revisions[1]


def test_keyset_pages_and_filters_are_parameterized():
    connection = FakeConnection(
        [
            [row(1), row(5)],
            [row(20)],
        ]
    )
    batch = PublicationBatch(date(2026, 10, 6), ("inlabs:20", "inlabs:1", "inlabs:5"), 2)
    with patch(
        "ro_dou_ner.adapters.sources.inlabs.source.psycopg.connect", return_value=connection
    ):
        publications = list(InlabsPublicationSource("unused").iter_publications(batch))
    assert [item.publication_id for item in publications] == ["inlabs:1", "inlabs:5", "inlabs:20"]
    first_query, first_params = connection.calls[0]
    assert "OFFSET" not in first_query
    assert "ORDER BY id LIMIT %s" in first_query
    assert "id = ANY(%s)" in first_query
    assert first_params == [date(2026, 10, 6), date(2026, 10, 7), [1, 5, 20], 2]
    second_query, second_params = connection.calls[1]
    assert "id > %s" in second_query
    assert second_params[0] == 5
    assert "2026-10-06" not in first_query


def test_exact_full_page_checks_next_page_without_duplication():
    connection = FakeConnection([[row(2)], [row(9)], []])
    with patch(
        "ro_dou_ner.adapters.sources.inlabs.source.psycopg.connect", return_value=connection
    ):
        publications = list(
            InlabsPublicationSource("unused").iter_publications(PublicationBatch(page_size=1))
        )
    assert [item.publication_id for item in publications] == ["inlabs:2", "inlabs:9"]
    assert len(connection.calls) == 3


@pytest.mark.parametrize(
    "publication_id",
    [
        "other:1",
        "inlabs:1;DELETE FROM x",
        "inlabs:-1",
        "inlabs:",
        "1",
        "inlabs:١",
        "inlabs:9223372036854775808",
    ],
)
def test_invalid_source_ids_rejected_before_database_access(publication_id):
    with patch("ro_dou_ner.adapters.sources.inlabs.source.psycopg.connect") as connect:
        with pytest.raises(ValueError):
            list(
                InlabsPublicationSource("unused").iter_publications(
                    PublicationBatch(publication_ids=(publication_id,))
                )
            )
        connect.assert_not_called()


def test_missing_full_text_is_explicit_failure():
    connection = FakeConnection([[row(1, text=None)]])
    with patch(
        "ro_dou_ner.adapters.sources.inlabs.source.psycopg.connect", return_value=connection
    ):
        with pytest.raises(ValueError, match="has no complete text"):
            list(InlabsPublicationSource("unused").iter_publications(PublicationBatch()))
