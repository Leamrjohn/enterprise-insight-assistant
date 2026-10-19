from types import SimpleNamespace

from app.modules.input_artifacts import outbox_tasks, tasks
from app.modules.input_artifacts.processing.image_ocr import TesseractImageOcr
from app.modules.input_artifacts.processing.parser import ImageParseLimits, PdfParseLimits


class _Session:
    def close(self) -> None:
        pass


def test_parse_task_passes_server_owned_ocr_configuration_to_the_worker(
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}
    settings = SimpleNamespace(
        input_artifact_parser_processor_version="test-parser-v1",
        input_artifact_image_max_pixels=123,
        input_artifact_ocr_minimum_confidence=65.0,
        input_artifact_ocr_languages="eng",
        input_artifact_ocr_timeout_seconds=9,
        input_artifact_pdf_render_timeout_seconds=11,
        input_artifact_pdf_render_max_side_pixels=1234,
        input_artifact_pdf_max_ocr_pages=2,
    )
    monkeypatch.setattr(tasks, "get_settings", lambda: settings)
    monkeypatch.setattr(tasks, "SessionLocal", _Session)
    monkeypatch.setattr(tasks, "set_tenant_scope", lambda db, company_id: None)
    monkeypatch.setattr(
        tasks,
        "get_artifact_processing_storage",
        lambda settings: "storage",
    )

    def execute_parse_job(db, **kwargs) -> bool:
        captured.update(kwargs)
        return True

    monkeypatch.setattr(tasks, "execute_parse_job", execute_parse_job)

    assert tasks.process_parse_job.run(7, 8, 9)
    assert captured["processor_version"] == "test-parser-v1"
    assert captured["image_limits"] == ImageParseLimits(
        max_pixels=123,
        minimum_ocr_confidence=65.0,
    )
    assert isinstance(captured["image_ocr"].__self__, TesseractImageOcr)
    assert captured["image_ocr"].__self__._languages == "eng"
    assert captured["image_ocr"].__self__._timeout_seconds == 9
    assert captured["pdf_page_renderer"].__self__._timeout_seconds == 11
    assert captured["pdf_page_renderer"].__self__._max_side_pixels == 1234
    assert captured["pdf_limits"] == PdfParseLimits(
        max_ocr_pages=2,
        minimum_ocr_confidence=65.0,
    )


def test_outbox_publisher_routes_parse_jobs_to_the_parse_task(monkeypatch) -> None:
    delivered: list[dict[str, int]] = []
    event = SimpleNamespace(job_id=8)
    job = SimpleNamespace(stage="parse")
    db = SimpleNamespace(
        scalars=lambda _query: SimpleNamespace(all=lambda: [7]),
        get=lambda model, record_id: event if record_id == 1 else job,
        close=lambda: None,
    )
    monkeypatch.setattr(outbox_tasks, "SessionLocal", lambda: db)
    monkeypatch.setattr(outbox_tasks, "set_tenant_scope", lambda db, company_id: None)
    monkeypatch.setattr(
        outbox_tasks,
        "pending_artifact_processing_event_ids",
        lambda db: [1],
    )
    monkeypatch.setattr(
        tasks,
        "process_parse_job",
        SimpleNamespace(delay=lambda **kwargs: delivered.append(kwargs) or object()),
    )

    def publish_event(db, *, event_id, enqueue) -> bool:
        enqueue(7, 8, 9)
        return True

    monkeypatch.setattr(
        outbox_tasks,
        "publish_artifact_processing_event",
        publish_event,
    )

    assert outbox_tasks.publish_pending_artifact_processing_events.run() == 1
    assert delivered == [
        {"company_id": 7, "job_id": 8, "dispatch_generation": 9}
    ]
