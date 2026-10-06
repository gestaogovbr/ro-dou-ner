from datetime import date
from types import SimpleNamespace

import pytest

from ro_dou_ner.adapters.triggers.airflow import process_events, reference_dates
from ro_dou_ner.application import BatchReport


def event(value):
    return SimpleNamespace(extra={"reference_date": value})


def test_coalesced_normal_and_extra_events_process_all_dates_once():
    events = {
        "inlabs": [event("2026-10-05"), event("2026-10-06")],
        "inlabs_edicao_extra": [event("2026-10-06")],
    }
    assert reference_dates(events) == (date(2026, 10, 5), date(2026, 10, 6))
    batches = []

    class Processor:
        def execute(self, batch):
            batches.append(batch)
            return BatchReport(processed=1)

    reports = process_events(events, Processor())
    assert len(reports) == len(batches) == 2
    assert batches[0].reference_date == date(2026, 10, 5)


def test_manual_run_date_and_invalid_metadata():
    assert reference_dates({}, "2026-10-06") == (date(2026, 10, 6),)
    for events in ({}, {"inlabs": [SimpleNamespace(extra={})]}, {"inlabs": [event("not-a-date")]}):
        with pytest.raises(ValueError):
            reference_dates(events)


@pytest.mark.parametrize("report", [BatchReport(failed=1), BatchReport(projection_failed=1)])
def test_trigger_failure_requests_orchestrator_retry(report):
    class Processor:
        def execute(self, batch):
            return report

    with pytest.raises(RuntimeError):
        process_events({}, Processor(), "2026-10-06")
