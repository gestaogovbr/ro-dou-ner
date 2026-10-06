from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from dataclasses import asdict, replace
from threading import Event

import pytest

from ro_dou_ner.adapters.persistence.memory import InMemoryRepository
from ro_dou_ner.application import EnrichPublications
from ro_dou_ner.domain import (
    CanonicalDocument,
    MentionCandidate,
    ModelInfo,
    PipelineSpec,
    Publication,
    PublicationBatch,
    TextChunk,
    source_revision,
)


class Source:
    def __init__(self, publications):
        self.publications = publications

    def iter_publications(self, batch):
        return iter(self.publications)


class Preparer:
    def prepare(self, publication):
        return CanonicalDocument(
            publication.publication_id,
            publication.body_text,
            source_revision(publication.body_text, publication.metadata),
            publication.metadata,
        )


class Chunker:
    def __init__(self, size=40, overlap=12):
        self.size, self.overlap = size, overlap

    def chunk(self, document):
        start = 0
        while start < len(document.body_text):
            end = min(start + self.size, len(document.body_text))
            yield TextChunk(start, end, document.body_text[start:end])
            if end == len(document.body_text):
                break
            start = end - self.overlap


class Extractor:
    def __init__(self):
        self.calls = []
        self.fail = False

    def extract(self, chunk):
        self.calls.append(chunk)
        if self.fail:
            raise RuntimeError("password=do-not-expose-this")
        found = []
        start = 0
        while (start := chunk.text.find("José", start)) != -1:
            found.append(MentionCandidate("PERSON", "José", start, start + 4, 0.9, "gliner"))
            start += 4
        return tuple(found)


class Projector:
    def __init__(self):
        self.calls = []
        self.fail = False

    def project(self, result):
        self.calls.append(result)
        if self.fail:
            raise RuntimeError("token=do-not-expose-this")


@pytest.fixture
def components():
    source = Source([Publication("inlabs:1", "Nomeação de José para o Ministério.")])
    extractor = Extractor()
    repository = InMemoryRepository()
    pipeline = PipelineSpec(
        ModelInfo("fake", "deterministic-test-double", "v1"),
        "test-v1",
        ("PERSON", "IDENTIFIER"),
        "raw-test-v1",
        {"size": 40, "overlap": 12},
        {"gliner": "fake-v1", "rules": "fake-v1"},
    )
    return source, extractor, repository, pipeline


def make_use_case(components, **kwargs):
    source, extractor, repository, pipeline = components
    return EnrichPublications(
        source, Preparer(), Chunker(), (extractor,), repository, pipeline, **kwargs
    )


def test_publication_enriched_queryable_and_replay_does_not_duplicate(components):
    use_case = make_use_case(components)
    first = use_case.execute(PublicationBatch())
    source, extractor, repository, pipeline = components
    result = repository.get_latest("inlabs:1")
    assert (first.processed, first.failed) == (1, 0)
    assert result.body_text == source.publications[0].body_text
    assert result.model == pipeline.model and result.pipeline_version == pipeline.version
    assert result.taxonomy_version == pipeline.taxonomy_version
    assert result.mentions[0].surface == "José"
    count = len(extractor.calls)
    second = use_case.execute(PublicationBatch())
    assert (second.skipped, second.processed) == (1, 0)
    assert len(extractor.calls) == count and len(repository.runs) == 1


def test_document_and_pipeline_changes_create_independent_results(components):
    source, extractor, repository, pipeline = components
    make_use_case(components).execute(PublicationBatch())
    original = repository.get_latest("inlabs:1")
    source.publications = [replace(source.publications[0], body_text="José foi exonerado.")]
    make_use_case(components).execute(PublicationBatch())
    changed = repository.get_latest("inlabs:1")
    new_pipeline = replace(pipeline, model=replace(pipeline.model, revision="v2"))
    make_use_case((source, extractor, repository, new_pipeline)).execute(PublicationBatch())
    latest = repository.get_latest("inlabs:1")
    assert len(repository.runs) == 3
    assert original.source_revision != changed.source_revision
    assert latest.source_revision == changed.source_revision
    assert latest.pipeline_version != changed.pipeline_version
    assert repository.get(original.idempotency_key) == original
    assert repository.get_latest("inlabs:1", pipeline_version=pipeline.version) == changed


def test_long_document_is_fully_processed_with_global_unicode_offsets(components):
    source, extractor, repository, _ = components
    text = ("á👩🏾 x " * 30) + "José " + ("texto " * 40) + "José"
    source.publications = [Publication("inlabs:long", text)]
    report = make_use_case(components).execute(PublicationBatch())
    result = repository.get_latest("inlabs:long")
    assert report.processed == 1
    assert len(extractor.calls) > 10
    assert extractor.calls[0].start == 0 and extractor.calls[-1].end == len(text)
    assert {(m.start, m.end) for m in result.mentions} == {
        (text.index("José"), text.index("José") + 4),
        (text.rindex("José"), len(text)),
    }
    assert all(m.surface == text[m.start : m.end] for m in result.mentions)


def test_model_failure_records_sanitized_failure_and_can_retry(components, caplog):
    source, extractor, repository, pipeline = components
    make_use_case(components).execute(PublicationBatch())
    previous = repository.get_latest("inlabs:1")
    source.publications = [replace(source.publications[0], body_text="Nova publicação: José")]
    extractor.fail = True
    report = make_use_case(components).execute(PublicationBatch())
    assert report.failed == 1
    assert repository.get_latest("inlabs:1") == previous
    assert list(repository.runs.values())[-1]["status"] == "failed"
    assert list(repository.runs.values())[-1]["model"] == asdict(pipeline.model)
    assert "do-not-expose" not in str(report.errors) + caplog.text + str(repository.runs)
    extractor.fail = False
    retry = make_use_case(components).execute(PublicationBatch())
    assert retry.processed == 1 and retry.failed == 0
    assert list(repository.runs.values())[-1]["status"] == "succeeded"


def test_projection_failure_can_retry_without_model_or_persistence_duplicate(components):
    projector = Projector()
    projector.fail = True
    use_case = make_use_case(components, projector=projector)
    first = use_case.execute(PublicationBatch())
    assert (first.processed, first.failed, first.projection_failed) == (1, 0, 1)
    _, extractor, repository, _ = components
    count = len(extractor.calls)
    projector.fail = False
    retry = use_case.execute(PublicationBatch())
    assert (retry.skipped, retry.projection_failed) == (1, 0)
    assert len(projector.calls) == 2 and len(extractor.calls) == count
    assert len(repository.runs) == 1


def test_batch_continues_after_invalid_model_candidate(components):
    source, _, repository, pipeline = components
    source.publications = [Publication("inlabs:bad", "bad"), Publication("inlabs:good", "José")]

    class InvalidFirst(Extractor):
        def extract(self, chunk):
            if chunk.text == "bad":
                return (MentionCandidate("PERSON", "bad", 0, 99, 0.7, "gliner"),)
            return super().extract(chunk)

    report = make_use_case((source, InvalidFirst(), repository, pipeline)).execute(
        PublicationBatch()
    )
    assert (report.processed, report.failed) == (1, 1)
    assert repository.get_latest("inlabs:bad") is None
    assert repository.get_latest("inlabs:good") is not None


@pytest.mark.parametrize("spans", [[(0, 5)], [(1, 10)], [(0, 3), (4, 10)]])
def test_incomplete_chunk_coverage_is_rejected(components, spans):
    source, extractor, repository, pipeline = components
    source.publications = [Publication("inlabs:bad-chunks", "0123456789")]

    class BrokenChunker:
        def chunk(self, document):
            return [TextChunk(start, end, document.body_text[start:end]) for start, end in spans]

    report = EnrichPublications(
        source, Preparer(), BrokenChunker(), (extractor,), repository, pipeline
    ).execute(PublicationBatch())
    assert report.failed == 1
    assert repository.get_latest("inlabs:bad-chunks") is None


def test_rules_see_whole_document_once_to_preserve_boundary_entities(components):
    source, _, repository, _ = components
    text = "x" * 35 + "12345-67890" + "x" * 50
    source.publications = [Publication("inlabs:boundary", text)]

    class Rule:
        calls = []

        def extract(self, chunk):
            self.calls.append(chunk)
            return (MentionCandidate("IDENTIFIER", "12345-67890", 35, 46, None, "rules"),)

    rule = Rule()
    report = make_use_case(components, whole_document_extractors=(rule,)).execute(
        PublicationBatch()
    )
    assert report.processed == 1
    assert len(rule.calls) == 1 and rule.calls[0].text == text
    assert repository.get_latest("inlabs:boundary").mentions[0].surface == "12345-67890"


def test_concurrent_runs_only_execute_model_once(components):
    source, _, repository, pipeline = components
    started, release = Event(), Event()

    class BlockingExtractor(Extractor):
        def extract(self, chunk):
            started.set()
            assert release.wait(5), "test worker was not released"
            return super().extract(chunk)

    extractor = BlockingExtractor()
    use_case = make_use_case((source, extractor, repository, pipeline))
    with ThreadPoolExecutor(max_workers=2) as workers:
        first = workers.submit(use_case.execute, PublicationBatch())
        try:
            assert started.wait(5)
            second = workers.submit(use_case.execute, PublicationBatch()).result(timeout=5)
            assert second.skipped == 1
        finally:
            release.set()
        assert first.result(timeout=5).processed == 1
    assert len(extractor.calls) == 1 and len(repository.runs) == 1


def test_repository_returns_detached_results_and_claim_releases_after_failure(components):
    make_use_case(components).execute(PublicationBatch())
    _, _, repository, _ = components
    result = repository.get_latest("inlabs:1")
    result.metadata["injected"] = "mutation"
    assert "injected" not in repository.get(result.idempotency_key).metadata
    with pytest.raises(RuntimeError):
        with repository.claim("key") as acquired:
            assert acquired
            raise RuntimeError("failure")
    with repository.claim("key") as acquired:
        assert acquired


def test_pipeline_configuration_snapshot_preserves_hash_and_full_provenance(components):
    source, _, repository, pipeline = components
    expected_version = pipeline.version

    class MutatingExtractor(Extractor):
        def extract(self, chunk):
            pipeline.chunking["size"] = 999
            pipeline.configuration["threshold"] = 0.99
            return super().extract(chunk)

    use_case = make_use_case((source, MutatingExtractor(), repository, pipeline))
    assert use_case.execute(PublicationBatch()).processed == 1
    result = repository.get_latest("inlabs:1")
    assert result.pipeline_version == expected_version
    assert result.pipeline_config["chunking"]["size"] == 40
    assert "threshold" not in result.pipeline_config["configuration"]
    assert result.pipeline_config["model"] == asdict(result.model)
    assert result == type(result).from_dict(result.to_dict())


def test_save_failure_does_not_leave_result_or_success_and_can_retry(components):
    source, extractor, _, pipeline = components

    class FailingRepository(InMemoryRepository):
        fail = True

        def save(self, result, run_id):
            if self.fail:
                raise ConnectionError("secret-dsn")
            super().save(result, run_id)

    repository = FailingRepository()
    use_case = make_use_case((source, extractor, repository, pipeline))
    assert use_case.execute(PublicationBatch()).failed == 1
    assert repository.get_latest("inlabs:1") is None
    assert list(repository.runs.values())[-1]["status"] == "failed"
    repository.fail = False
    assert use_case.execute(PublicationBatch()).processed == 1


def test_repository_run_identity_mismatch_cannot_partially_commit(components):
    make_use_case(components).execute(PublicationBatch())
    _, _, repository, pipeline = components
    result = repository.get_latest("inlabs:1")
    run_id = repository.start_run("inlabs:wrong", result.source_revision, pipeline.version)
    changed = replace(result, publication_id="inlabs:new")
    with pytest.raises(ValueError, match="identity"):
        repository.save(changed, run_id)
    assert repository.get(changed.idempotency_key) is None
    assert repository.runs[run_id]["status"] == "running"


def test_empty_publication_is_valid_and_zero_mentions_are_persisted(components):
    source, extractor, repository, _ = components
    source.publications = [Publication("inlabs:empty", "")]
    assert make_use_case(components).execute(PublicationBatch()).processed == 1
    result = repository.get_latest("inlabs:empty")
    assert result.body_text == "" and result.mentions == ()
    assert extractor.calls == []


def test_failure_is_recorded_before_claim_release_and_reported_once(components):
    source, extractor, _, pipeline = components
    events = []

    class ObservedRepository(InMemoryRepository):
        @contextmanager
        def claim(self, key):
            with super().claim(key) as acquired:
                events.append("acquire")
                try:
                    yield acquired
                finally:
                    # Reproduce the retry worker's view at the unlock boundary.
                    # A running attempt here would be incorrectly abandoned.
                    assert all(run["status"] != "running" for run in self.runs.values())
                    events.append("release")

        def fail_run(self, run_id, error):
            run = self.runs[run_id]
            key = next(iter(self._claimed))
            with super().claim(key) as acquired:
                assert not acquired, "failed run must transition while its claim is held"
            assert run["status"] == "running"
            events.append("fail_run")
            super().fail_run(run_id, error)

    repository = ObservedRepository()
    extractor.fail = True
    report = make_use_case((source, extractor, repository, pipeline)).execute(PublicationBatch())
    assert events == ["acquire", "fail_run", "release"]
    assert report.failed == 1 and len(report.errors) == 1
    assert report.errors[0]["stage"] == "extraction"
    assert list(repository.runs.values())[0]["status"] == "failed"
    extractor.fail = False
    assert (
        make_use_case((source, extractor, repository, pipeline))
        .execute(PublicationBatch())
        .processed
        == 1
    )


@pytest.mark.parametrize("failing_stage", ["preparation", "claim"])
def test_failures_before_acquiring_claim_are_reported_once(components, failing_stage):
    source, extractor, _, pipeline = components

    class FailingPreparer(Preparer):
        def prepare(self, publication):
            if failing_stage == "preparation":
                raise ValueError("preparation failed")
            return super().prepare(publication)

    class FailingClaimRepository(InMemoryRepository):
        @contextmanager
        def claim(self, key):
            raise ConnectionError("claim failed")
            yield  # pragma: no cover

    repository = FailingClaimRepository()
    report = EnrichPublications(
        source, FailingPreparer(), Chunker(), (extractor,), repository, pipeline
    ).execute(PublicationBatch())
    assert report.failed == 1 and len(report.errors) == 1
    assert report.errors[0]["stage"] == failing_stage
    assert not repository.runs and not extractor.calls
