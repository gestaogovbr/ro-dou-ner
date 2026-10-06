import json
import logging
from datetime import UTC, datetime


class EnrichmentLogFormatter(logging.Formatter):
    def format(self, record):
        payload = {
            "timestamp": datetime.now(UTC).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
        }
        for name in (
            "publication_id",
            "stage",
            "error_type",
            "processed",
            "skipped",
            "failed",
            "projection_failed",
        ):
            if hasattr(record, name):
                payload[name] = getattr(record, name)
        return json.dumps(payload, ensure_ascii=False)


def configure_logging():
    logger = logging.getLogger("ro_dou_ner")
    handler = logging.StreamHandler()
    handler.setFormatter(EnrichmentLogFormatter())
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)
    logger.propagate = False
