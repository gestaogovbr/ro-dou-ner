import json
from pathlib import Path

from ro_dou_ner.domain import Publication, PublicationBatch


class JsonFileSource:
    """Explicit offline input: JSONL containing publication_id, body_text and metadata."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def iter_publications(self, batch: PublicationBatch):
        if batch.reference_date is not None:
            raise ValueError("offline JSONL input does not support date filtering")
        with self.path.open(encoding="utf-8") as source:
            for line in source:
                if not line.strip():
                    continue
                record = json.loads(line)
                if batch.publication_ids and record["publication_id"] not in batch.publication_ids:
                    continue
                yield Publication(
                    record["publication_id"], record["body_text"], record.get("metadata", {})
                )
