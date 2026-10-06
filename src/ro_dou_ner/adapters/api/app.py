from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from ro_dou_ner.application import EnrichmentRepository
from ro_dou_ner.application.ports import PaginationWindowExceeded, PublicationReader


def create_app(
    repository: EnrichmentRepository,
    publication_reader: PublicationReader | None = None,
    preview_directory: str | Path | None = None,
) -> FastAPI:
    app = FastAPI(title="Ro-DOU NER", version="0.1.0")

    if preview_directory:
        directory = Path(preview_directory).resolve()
        preview_file = directory / "index.html"
        if not preview_file.is_file():
            raise ValueError("Preview directory must contain index.html")
        app.mount("/preview-assets", StaticFiles(directory=directory), name="preview-assets")

        @app.get("/preview", include_in_schema=False)
        def preview():
            return FileResponse(preview_file, headers={"Cache-Control": "no-store"})

    def get_result(publication_id: str, source_revision: str | None, pipeline_version: str | None):
        try:
            result = repository.get_latest(publication_id, source_revision, pipeline_version)
        except Exception as error:
            raise HTTPException(503, "Enrichment storage unavailable") from error
        if result is None:
            raise HTTPException(404, "Enrichment not found")
        return result

    @app.get("/health")
    def health():
        try:
            healthy = repository.health()
        except Exception:
            healthy = False
        return JSONResponse(
            {"status": "ok" if healthy else "unavailable"}, status_code=200 if healthy else 503
        )

    @app.get("/publications")
    def publications(
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=10, ge=1, le=100),
    ):
        """Paginate indexed enrichment versions, preserving every _source attribute."""
        if publication_reader is None:
            raise HTTPException(503, "Publication search unavailable")
        try:
            return publication_reader.list_publications(page, page_size).to_dict()
        except PaginationWindowExceeded as error:
            raise HTTPException(
                422, "Requested page exceeds the OpenSearch result window"
            ) from error
        except Exception as error:
            raise HTTPException(503, "Publication search unavailable") from error

    @app.get("/publications/{publication_id}/enrichment")
    def enrichment(
        publication_id: str, source_revision: str | None = None, pipeline_version: str | None = None
    ):
        return get_result(publication_id, source_revision, pipeline_version).to_dict()

    @app.get("/publications/{publication_id}/entities")
    def entities(
        publication_id: str,
        label: str | None = Query(default=None),
        source_revision: str | None = None,
        pipeline_version: str | None = None,
    ):
        result = get_result(publication_id, source_revision, pipeline_version)
        data = result.to_dict()
        return {
            "publication_id": publication_id,
            "source_revision": result.source_revision,
            "pipeline_version": result.pipeline_version,
            "mentions": [
                mention
                for mention in data["mentions"]
                if label is None or mention["label"] == label
            ],
        }

    return app
