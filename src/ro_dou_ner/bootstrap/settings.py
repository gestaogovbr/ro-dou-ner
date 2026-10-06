"""Explicit runtime configuration; credentials are never part of pipeline fingerprints."""

import json
import os
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path

LABELS = (
    "PERSON",
    "ORGANIZATION",
    "LOCATION",
    "PROCESS_NUMBER",
    "IDENTIFIER",
    "DATE",
    "MONEY",
    "LEGAL_REFERENCE",
)


@dataclass(frozen=True)
class Settings:
    database_dsn: str | None = None
    inlabs_dsn: str | None = None
    opensearch_url: str | None = None
    opensearch_index: str = "ro-dou-ner-publications-v1"
    preview_directory: str | None = None
    mode: str = "rules"
    model_id: str | None = None
    model_revision: str | None = None
    tokenizer_id: str | None = None
    tokenizer_revision: str | None = None
    threshold: float = 0.5
    max_chars: int = 700
    overlap: int = 100
    taxonomy_version: str = "ner-v1"
    labels: tuple[str, ...] = LABELS

    def __post_init__(self):
        if self.mode not in {"rules", "hybrid"}:
            raise ValueError("mode must be rules or hybrid")
        if self.max_chars <= 0 or not 0 <= self.overlap < self.max_chars:
            raise ValueError("chunk configuration must satisfy 0 <= overlap < max_chars")
        if not 0 <= self.threshold <= 1:
            raise ValueError("threshold must be in [0, 1]")
        if len(set(self.labels)) != len(self.labels) or set(self.labels) != set(LABELS):
            raise ValueError("MVP taxonomy must contain all eight supported labels exactly once")
        if self.mode == "hybrid":
            import re

            if (
                not self.model_id
                or not self.model_revision
                or not re.fullmatch(r"[a-f0-9]{40}", self.model_revision)
            ):
                raise ValueError(
                    "hybrid mode requires model ID and immutable 40-character checkpoint SHA"
                )
            if self.tokenizer_id or self.tokenizer_revision:
                if (
                    not self.tokenizer_id
                    or not self.tokenizer_revision
                    or not re.fullmatch(r"[a-f0-9]{40}", self.tokenizer_revision)
                ):
                    raise ValueError("external tokenizer requires ID and immutable checkpoint SHA")

    @classmethod
    def from_environment(cls, pipeline_path: str | None = None, **overrides):
        values = {}
        if pipeline_path:
            path = Path(pipeline_path)
            values = json.loads(path.read_text())
            taxonomy = values.pop("taxonomy", None)
            if taxonomy:
                tax = json.loads((path.parent / taxonomy).read_text())
                values.update(taxonomy_version=tax["version"], labels=tuple(tax["labels"]))
        env = {
            "database_dsn": "RO_DOU_NER_DATABASE_DSN",
            "inlabs_dsn": "RO_DOU_NER_INLABS_DSN",
            "opensearch_url": "RO_DOU_NER_OPENSEARCH_URL",
            "model_id": "RO_DOU_NER_MODEL_ID",
            "model_revision": "RO_DOU_NER_MODEL_REVISION",
            "mode": "RO_DOU_NER_MODE",
            "opensearch_index": "RO_DOU_NER_OPENSEARCH_INDEX",
            "preview_directory": "RO_DOU_NER_PREVIEW_DIRECTORY",
            "tokenizer_id": "RO_DOU_NER_TOKENIZER_ID",
            "tokenizer_revision": "RO_DOU_NER_TOKENIZER_REVISION",
        }
        values.update({key: os.environ[name] for key, name in env.items() if os.environ.get(name)})
        values.update({key: value for key, value in overrides.items() if value is not None})
        return cls(**values)

    def require_database(self) -> str:
        if not self.database_dsn:
            raise ValueError("RO_DOU_NER_DATABASE_DSN is required")
        return self.database_dsn

    def runtime_versions(self) -> dict[str, str]:
        packages = ["ro-dou-ner"]
        if self.mode == "hybrid":
            packages += ["gliner", "torch", "transformers", "tokenizers"]
        return {package: version(package) for package in packages}
