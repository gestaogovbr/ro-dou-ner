"""INLABS adapter. The upstream table and HTML remain untouched."""

from collections.abc import Iterator
from datetime import date, datetime, timedelta
from math import isfinite
from typing import Any

import psycopg
from psycopg.rows import dict_row

from ro_dou_ner.domain import Publication, PublicationBatch

# Mirrors dag_load_inlabs/sql/init-db.sql in Ro-dou. SELECT * deliberately retains
# source metadata if that source adds a column, without coupling the domain to SQL.
_SELECT = "SELECT * FROM dou_inlabs.article_raw"


def _metadata_value(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, float) and not isfinite(value):
        return None
    return value


def _article_ids(publication_ids: tuple[str, ...]) -> list[int]:
    result = []
    for publication_id in publication_ids:
        prefix, separator, suffix = publication_id.partition(":")
        if prefix != "inlabs" or not separator or not suffix.isascii() or not suffix.isdigit():
            raise ValueError("INLABS publication IDs must use inlabs:<nonnegative integer>")
        article_id = int(suffix)
        if article_id > 9223372036854775807:
            raise ValueError("INLABS article ID exceeds PostgreSQL BIGINT")
        result.append(article_id)
    return sorted(set(result))


class InlabsPublicationSource:
    """Stream complete publications with stable, bounded keyset pagination.

    The connection opens a read-only transaction, preventing accidental writes to
    Ro-DOU. A page is materialized before yielding; the entire batch never is.
    """

    def __init__(self, dsn: str, *, connect_timeout: int = 10) -> None:
        self._dsn = dsn
        self._connect_timeout = connect_timeout

    def iter_publications(self, batch: PublicationBatch) -> Iterator[Publication]:
        ids = _article_ids(batch.publication_ids)
        if batch.page_size < 1:
            raise ValueError("page_size must be positive")
        with psycopg.connect(
            self._dsn, connect_timeout=self._connect_timeout, row_factory=dict_row
        ) as connection:
            connection.read_only = True
            last_id: int | None = None
            while True:
                clauses: list[str] = []
                params: list[Any] = []
                if last_id is not None:
                    clauses.append("id > %s")
                    params.append(last_id)
                if batch.reference_date is not None:
                    clauses.extend(("pubdate >= %s", "pubdate < %s"))
                    params.extend((batch.reference_date, batch.reference_date + timedelta(days=1)))
                if batch.publication_ids:
                    clauses.append("id = ANY(%s)")
                    params.append(ids)
                sql = _SELECT
                if clauses:
                    sql += " WHERE " + " AND ".join(clauses)
                sql += " ORDER BY id LIMIT %s"
                params.append(batch.page_size)
                rows = connection.execute(sql, params).fetchall()
                if not rows:
                    break
                connection.commit()
                for row in rows:
                    if not isinstance(row["texto"], str):
                        raise ValueError(
                            f"INLABS publication inlabs:{row['id']} has no complete text"
                        )
                    metadata = {
                        key: _metadata_value(value)
                        for key, value in sorted(row.items())
                        if key not in {"id", "texto"}
                    }
                    yield Publication(
                        publication_id=f"inlabs:{row['id']}",
                        body_text=row["texto"],
                        metadata=metadata,
                    )
                last_id = rows[-1]["id"]
                if len(rows) < batch.page_size:
                    break

    def health(self) -> bool:
        try:
            with psycopg.connect(self._dsn, connect_timeout=self._connect_timeout) as connection:
                connection.read_only = True
                connection.execute("SELECT id FROM dou_inlabs.article_raw LIMIT 0")
            return True
        except psycopg.Error:
            return False
