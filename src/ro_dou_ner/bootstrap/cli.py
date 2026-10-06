import argparse
import json
import sys
from dataclasses import asdict
from datetime import date
from pathlib import Path

from ro_dou_ner.adapters.persistence.memory import InMemoryRepository
from ro_dou_ner.adapters.sources.json_file import JsonFileSource
from ro_dou_ner.domain import PublicationBatch

from .container import (
    build_processor,
    create_runtime_app,
    opensearch_projector,
    postgres_repository,
)
from .logging import configure_logging
from .settings import Settings


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(description="INLABS publication enrichment")
    root.add_argument("--pipeline", help="JSON pipeline configuration")
    root.add_argument("--mode", choices=("rules", "hybrid"))
    root.add_argument("--model-id")
    root.add_argument("--model-revision", help="Immutable Hugging Face commit SHA")
    root.add_argument(
        "--tokenizer-id", help="Pinned tokenizer/backbone for non-self-contained checkpoints"
    )
    root.add_argument("--tokenizer-revision", help="Immutable tokenizer/backbone commit SHA")
    commands = root.add_subparsers(dest="command", required=True)
    commands.add_parser("init-db", help="Initialize enrichment schema and optional search index")
    process = commands.add_parser(
        "process", help="Read full INLABS publications, persist and project"
    )
    process.add_argument("--date", type=date.fromisoformat)
    process.add_argument("--publication-id", action="append", default=[])
    process.add_argument("--page-size", type=int, default=500)
    offline = commands.add_parser(
        "enrich-file", help="Run offline JSONL through in-memory repository"
    )
    offline.add_argument("input")
    offline.add_argument("--output", required=True)
    serve = commands.add_parser("serve", help="Read-only enrichment API")
    serve.add_argument("--host", default="127.0.0.1")
    serve.add_argument("--port", type=int, default=8000)
    benchmark = commands.add_parser("benchmark", help="Exact-span evaluation over annotated JSONL")
    benchmark.add_argument("dataset")
    benchmark.add_argument("--output", required=True)
    return root


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    configure_logging()
    try:
        settings = Settings.from_environment(
            args.pipeline,
            mode=args.mode,
            model_id=args.model_id,
            model_revision=args.model_revision,
            tokenizer_id=args.tokenizer_id,
            tokenizer_revision=args.tokenizer_revision,
        )
        if args.command == "init-db":
            postgres_repository(settings).initialize()
            projector = opensearch_projector(settings)
            if projector:
                projector.initialize()
            print(json.dumps({"status": "initialized"}))
            return 0
        if args.command == "serve":
            import uvicorn

            uvicorn.run(create_runtime_app(settings), host=args.host, port=args.port)
            return 0
        if args.command == "process":
            from ro_dou_ner.adapters.sources.inlabs import InlabsPublicationSource

            if not settings.inlabs_dsn:
                raise ValueError("RO_DOU_NER_INLABS_DSN is required")
            if args.date is None and not args.publication_id:
                raise ValueError("process requires --date or at least one --publication-id")
            processor = build_processor(
                settings,
                InlabsPublicationSource(settings.inlabs_dsn),
                postgres_repository(settings),
                opensearch_projector(settings),
            )
            report = processor.execute(
                PublicationBatch(args.date, tuple(args.publication_id), args.page_size)
            )
        elif args.command == "enrich-file":
            repository = InMemoryRepository()
            processor = build_processor(settings, JsonFileSource(args.input), repository)
            report = processor.execute(PublicationBatch())
            ids = tuple(
                item.publication_id
                for item in JsonFileSource(args.input).iter_publications(PublicationBatch())
            )
            results = [
                repository.get_latest(publication_id) for publication_id in dict.fromkeys(ids)
            ]
            Path(args.output).write_text(
                "".join(
                    json.dumps(result.to_dict(), ensure_ascii=False) + "\n"
                    for result in results
                    if result is not None
                ),
                encoding="utf-8",
            )
        else:
            from ro_dou_ner.application.evaluation import evaluate_pipeline

            class SinglePublicationSource:
                def __init__(self):
                    self.publication = None

                def iter_publications(self, batch):
                    return (self.publication,)

            source = SinglePublicationSource()
            repository = InMemoryRepository()
            processor = build_processor(settings, source, repository)

            def enrich(publication):
                source.publication = publication
                outcome = processor.execute(PublicationBatch())
                if outcome.failed:
                    raise RuntimeError("publication failed")
                return repository.get_latest(publication.publication_id)

            result = evaluate_pipeline(
                args.dataset,
                enrich,
                settings.labels,
                metadata={
                    "model": asdict(processor.pipeline.model),
                    "pipeline_version": processor.pipeline.version,
                    "taxonomy_version": processor.pipeline.taxonomy_version,
                },
            )
            Path(args.output).write_text(
                json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            print(json.dumps(result, ensure_ascii=False))
            return 1 if result["coverage"]["failed_documents"] else 0
        print(json.dumps(asdict(report), ensure_ascii=False))
        return 1 if report.failed or report.projection_failed else 0
    except Exception as error:
        # SDK exceptions may include credentials. Expose only their type at the CLI boundary.
        print(json.dumps({"status": "failed", "error_type": type(error).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
