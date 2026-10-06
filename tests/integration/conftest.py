"""Canonical INLABS test schema, independent of test execution order."""

import os

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict


@pytest.fixture(scope="session", autouse=True)
def prepare_test_inlabs_schema():
    dsn = os.environ.get("RO_DOU_NER_TEST_POSTGRES_DSN")
    if not dsn:
        return
    if "test" not in conninfo_to_dict(dsn).get("dbname", "").lower():
        pytest.fail("INLABS test schema requires a dedicated test database")
    fields = {
        "name": "TEXT",
        "idoficio": "BIGINT",
        "pubname": "TEXT",
        "arttype": "TEXT",
        "pubdate": "TIMESTAMP WITHOUT TIME ZONE",
        "artclass": "TEXT",
        "artcategory": "TEXT",
        "artsize": "BIGINT",
        "artnotes": "TEXT",
        "numberpage": "BIGINT",
        "pdfpage": "TEXT",
        "editionnumber": "TEXT",
        "highlighttype": "TEXT",
        "highlightpriority": "FLOAT",
        "highlight": "TEXT",
        "highlightimage": "TEXT",
        "highlightimagename": "TEXT",
        "idmateria": "BIGINT",
        "midias": "TEXT",
        "identifica": "TEXT",
        "data": "TEXT",
        "ementa": "TEXT",
        "titulo": "TEXT",
        "subtitulo": "TEXT",
        "texto": "TEXT",
        "assina": "TEXT",
    }
    with psycopg.connect(dsn) as connection:
        connection.execute("CREATE SCHEMA IF NOT EXISTS dou_inlabs")
        connection.execute(
            "CREATE TABLE IF NOT EXISTS dou_inlabs.article_raw (id BIGINT PRIMARY KEY)"
        )
        for field, kind in fields.items():
            connection.execute(
                sql.SQL("ALTER TABLE dou_inlabs.article_raw ADD COLUMN IF NOT EXISTS {} {}").format(
                    sql.Identifier(field), sql.SQL(kind)
                )
            )
