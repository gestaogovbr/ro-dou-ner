"""Dataset event consumption, independent of Airflow imports at application level."""

from datetime import date


def reference_dates(events: dict, manual_date: str | None = None) -> tuple[date, ...]:
    dates = set()
    if manual_date:
        dates.add(date.fromisoformat(manual_date))
    for dataset_events in events.values():
        for event in dataset_events:
            value = (event.extra or {}).get("reference_date")
            if not value:
                raise ValueError("INLABS event is missing reference_date")
            dates.add(date.fromisoformat(value))
    if not dates:
        raise ValueError("No INLABS reference_date supplied by events or manual run")
    return tuple(sorted(dates))


def process_events(events: dict, processor, manual_date: str | None = None):
    from ro_dou_ner.domain import PublicationBatch

    reports = [
        processor.execute(PublicationBatch(reference_date=value))
        for value in reference_dates(events, manual_date)
    ]
    if any(report.failed or report.projection_failed for report in reports):
        raise RuntimeError("INLABS enrichment failed; retry the Airflow task")
    return reports
