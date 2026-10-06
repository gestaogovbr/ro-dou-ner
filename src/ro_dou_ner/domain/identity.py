"""Canonical, versioned identities independent of storage and model SDKs."""

import hashlib
import json
from typing import Any


def canonical_sha256(payload: Any) -> str:
    """Hash unambiguous JSON; reject non-finite numbers and non-JSON values."""
    serialized = json.dumps(
        payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False
    )
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def source_revision(raw_content: str, metadata: dict | None = None) -> str:
    return canonical_sha256(
        {"identity_version": 1, "content": raw_content, "metadata": metadata or {}}
    )


def idempotency_key(publication_id: str, source_revision: str, pipeline_version: str) -> str:
    return canonical_sha256(
        {
            "identity_version": 1,
            "publication_id": publication_id,
            "source_revision": source_revision,
            "pipeline_version": pipeline_version,
        }
    )
