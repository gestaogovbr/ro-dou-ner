"""Composition root: concrete adapters are wired explicitly in one place."""

from ro_dou_ner.adapters.extraction.rules import RuleExtractor
from ro_dou_ner.adapters.text import HTMLTextPreparer, OverlappingChunker
from ro_dou_ner.application import EnrichPublications
from ro_dou_ner.domain import ModelInfo, PipelineSpec

from .settings import Settings


def pipeline_components(settings: Settings):
    preparer = HTMLTextPreparer()
    chunker = OverlappingChunker(settings.max_chars, settings.overlap)
    rules = RuleExtractor()
    extractors = []
    model_info = ModelInfo("rules", "brazil-publication-rules", rules.version)
    versions = {"rules": rules.version}
    if settings.mode == "hybrid":
        from ro_dou_ner.adapters.extraction.gliner import GlinerExtractor

        extractor = GlinerExtractor(
            settings.model_id,
            settings.model_revision,
            threshold=settings.threshold,
            tokenizer_id=settings.tokenizer_id,
            tokenizer_revision=settings.tokenizer_revision,
        )
        extractors.append(extractor)
        model_info = ModelInfo("gliner", settings.model_id, settings.model_revision)
        versions["gliner"] = extractor.version
    pipeline = PipelineSpec(
        model=model_info,
        taxonomy_version=settings.taxonomy_version,
        labels=settings.labels,
        normalization_version=preparer.version,
        chunking={
            "version": chunker.version,
            "max_chars": settings.max_chars,
            "overlap": settings.overlap,
        },
        extractor_versions=versions,
        configuration={
            "mode": settings.mode,
            "threshold": settings.threshold,
            "extractor_priority": ["rules", "gliner"],
            "runtime_versions": settings.runtime_versions(),
            "tokenizer_id": settings.tokenizer_id,
            "tokenizer_revision": settings.tokenizer_revision,
        },
    )
    return preparer, chunker, tuple(extractors), rules, pipeline


def build_processor(settings: Settings, source, repository, projector=None) -> EnrichPublications:
    preparer, chunker, extractors, rules, pipeline = pipeline_components(settings)
    return EnrichPublications(
        source,
        preparer,
        chunker,
        extractors,
        repository,
        pipeline,
        projector=projector,
        whole_document_extractors=(rules,),
    )


def postgres_repository(settings: Settings):
    from ro_dou_ner.adapters.persistence.postgres import PostgresEnrichmentRepository

    return PostgresEnrichmentRepository(settings.require_database())


def opensearch_projector(settings: Settings):
    if not settings.opensearch_url:
        return None
    from ro_dou_ner.adapters.search.opensearch import OpenSearchProjector

    return OpenSearchProjector(settings.opensearch_url, index=settings.opensearch_index)


def opensearch_reader(settings: Settings):
    if not settings.opensearch_url:
        return None
    from ro_dou_ner.adapters.search.opensearch import OpenSearchPublicationReader

    return OpenSearchPublicationReader(settings.opensearch_url, index=settings.opensearch_index)


def create_runtime_app(settings: Settings | None = None):
    from ro_dou_ner.adapters.api.app import create_app

    settings = settings or Settings.from_environment()
    return create_app(
        postgres_repository(settings),
        publication_reader=opensearch_reader(settings),
        preview_directory=settings.preview_directory,
    )
