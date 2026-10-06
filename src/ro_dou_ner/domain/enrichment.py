import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from typing import Any

from .identity import canonical_sha256, idempotency_key
from .mentions import Mention, validate_mention


@dataclass(frozen=True)
class ModelInfo:
    provider: str
    model_id: str
    revision: str

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, str) or not item
            for item in (self.provider, self.model_id, self.revision)
        ):
            raise ValueError("model provider, model_id and revision must be nonempty")


@dataclass(frozen=True)
class PipelineSpec:
    model: ModelInfo
    taxonomy_version: str
    labels: tuple[str, ...]
    normalization_version: str
    chunking: dict
    extractor_versions: dict
    configuration: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.taxonomy_version or not self.normalization_version:
            raise ValueError("taxonomy and normalization versions must be nonempty")
        if not self.labels or any(not isinstance(label, str) or not label for label in self.labels):
            raise ValueError("pipeline labels must be nonempty")
        if len(set(self.labels)) != len(self.labels):
            raise ValueError("pipeline labels must be unique")
        canonical_sha256(asdict(self))

    @property
    def version(self) -> str:
        return canonical_sha256({"identity_version": 1, **asdict(self)})

    @property
    def pipeline_version(self) -> str:
        return self.version


@dataclass(frozen=True)
class EnrichmentResult:
    publication_id: str
    source_revision: str
    pipeline_version: str
    taxonomy_version: str
    model: ModelInfo
    body_text: str
    mentions: tuple[Mention, ...]
    completed_at: datetime
    metadata: dict = field(default_factory=dict)
    pipeline_config: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        if any(
            not isinstance(item, str) or not item
            for item in (
                self.publication_id,
                self.source_revision,
                self.pipeline_version,
                self.taxonomy_version,
            )
        ):
            raise ValueError("result identity and version fields must be nonempty")
        if not isinstance(self.body_text, str):
            raise ValueError("result body_text must be a string")
        if self.completed_at.tzinfo is None or self.completed_at.utcoffset() is None:
            raise ValueError("completed_at must be timezone aware")
        for mention in self.mentions:
            validate_mention(mention, self.body_text)
        canonical_sha256(self.metadata)
        canonical_sha256(self.pipeline_config)
        object.__setattr__(
            self, "pipeline_config", json.loads(json.dumps(self.pipeline_config, allow_nan=False))
        )

    @property
    def idempotency_key(self) -> str:
        return idempotency_key(self.publication_id, self.source_revision, self.pipeline_version)

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["completed_at"] = self.completed_at.astimezone(UTC).isoformat()
        result["mentions"] = [asdict(mention) for mention in self.mentions]
        # JSON roundtrip prevents callers from mutating persisted nested metadata.
        return json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False))

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EnrichmentResult":
        data = json.loads(json.dumps(payload, ensure_ascii=False, allow_nan=False))
        data["model"] = ModelInfo(**data["model"])
        data["mentions"] = tuple(Mention(**mention) for mention in data["mentions"])
        data["completed_at"] = datetime.fromisoformat(data["completed_at"].replace("Z", "+00:00"))
        return cls(**data)
