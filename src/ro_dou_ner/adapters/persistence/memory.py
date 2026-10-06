"""Thread-safe local repository implementing the same identity/run contract."""

from contextlib import contextmanager
from dataclasses import asdict
from datetime import UTC, datetime
from threading import RLock
from uuid import uuid4

from ro_dou_ner.domain import EnrichmentResult, ModelInfo


class InMemoryRepository:
    def __init__(self) -> None:
        self._results: dict[str, dict] = {}
        self._claimed: set[str] = set()
        self._lock = RLock()
        self.runs: dict[str, dict] = {}

    @contextmanager
    def claim(self, key: str):
        with self._lock:
            acquired = key not in self._claimed
            if acquired:
                self._claimed.add(key)
        try:
            yield acquired
        finally:
            if acquired:
                with self._lock:
                    self._claimed.remove(key)

    def get(self, key: str) -> EnrichmentResult | None:
        with self._lock:
            payload = self._results.get(key)
            return EnrichmentResult.from_dict(payload) if payload is not None else None

    def get_latest(
        self,
        publication_id: str,
        source_revision: str | None = None,
        pipeline_version: str | None = None,
    ) -> EnrichmentResult | None:
        with self._lock:
            results = [
                EnrichmentResult.from_dict(payload)
                for payload in self._results.values()
                if payload["publication_id"] == publication_id
                and (source_revision is None or payload["source_revision"] == source_revision)
                and (pipeline_version is None or payload["pipeline_version"] == pipeline_version)
            ]
            return max(results, key=lambda result: result.completed_at, default=None)

    def start_run(
        self,
        publication_id: str,
        source_revision: str,
        pipeline_version: str,
        model: ModelInfo | None = None,
    ) -> str:
        run_id = str(uuid4())
        with self._lock:
            self.runs[run_id] = {
                "publication_id": publication_id,
                "source_revision": source_revision,
                "pipeline_version": pipeline_version,
                "status": "running",
                "started_at": datetime.now(UTC),
                "error": None,
                "model": asdict(model) if model is not None else {},
            }
        return run_id

    def save(self, result: EnrichmentResult, run_id: str) -> None:
        payload = result.to_dict()
        with self._lock:
            run = self.runs[run_id]
            if run["status"] != "running":
                raise ValueError("run is not running")
            for name in ("publication_id", "source_revision", "pipeline_version"):
                if run[name] != getattr(result, name):
                    raise ValueError("result identity differs from run")
            if result.idempotency_key not in self._results:
                self._results[result.idempotency_key] = payload
            run.update(status="succeeded", completed_at=result.completed_at)

    def fail_run(self, run_id: str, error: str) -> None:
        with self._lock:
            run = self.runs[run_id]
            if run["status"] != "running":
                raise ValueError("run is not running")
            run.update(status="failed", error=error, completed_at=datetime.now(UTC))

    def health(self) -> bool:
        return True
