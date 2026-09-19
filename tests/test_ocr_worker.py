from pathlib import Path

from source_doc_converter import ocr_worker
from source_doc_converter.ocr_pipeline import (
    DoclingResult,
    OcrCancelledError,
    OcrError,
    OcrResult,
)
from source_doc_converter.ocr_worker import ProcessingWorker


def test_worker_reports_ocr_success(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    destination = tmp_path / "output" / "filing.searchable.pdf"

    def fake_run_ocr(*args, **kwargs):
        return OcrResult(source, destination, ("ocrmypdf",), "", "")

    monkeypatch.setattr(ocr_worker, "run_ocr", fake_run_ocr)
    worker = ProcessingWorker(
        (source,),
        tmp_path / "output",
        create_searchable_pdf=True,
        create_markdown=False,
        create_json=False,
        executable="ocrmypdf",
    )
    successes = []
    summaries = []
    worker.file_succeeded.connect(lambda source_path, output: successes.append((source_path, output)))
    worker.finished.connect(lambda cancelled, ok, failed: summaries.append((cancelled, ok, failed)))

    worker.run()

    assert len(successes) == 1
    assert successes[0][0] == str(source)
    assert str(destination) in successes[0][1]
    assert "Timing: Total per file " in successes[0][1]
    assert summaries == [(False, 1, 0)]


def test_worker_routes_original_pdf_to_docling_when_ocr_disabled(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    output_directory = tmp_path / "output"
    markdown_file = output_directory / "filing.md"
    called_with: list[Path] = []

    def fake_run_docling(input_path, *args, **kwargs):
        called_with.append(input_path)
        return DoclingResult(input_path, markdown_file, None)

    monkeypatch.setattr(ocr_worker, "run_docling", fake_run_docling)
    worker = ProcessingWorker(
        (source,),
        output_directory,
        create_searchable_pdf=False,
        create_markdown=True,
        create_json=False,
    )
    successes = []
    worker.file_succeeded.connect(lambda source_path, output: successes.append((source_path, output)))

    worker.run()

    assert called_with == [source]
    assert len(successes) == 1
    assert successes[0][0] == str(source)
    assert str(markdown_file) in successes[0][1]
    assert "Timing: Total per file " in successes[0][1]


def test_worker_routes_searchable_pdf_to_docling_when_both_selected(
    monkeypatch,
    tmp_path: Path,
) -> None:
    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    output_directory = tmp_path / "output"
    searchable = output_directory / "filing.searchable.pdf"
    markdown = output_directory / "filing.searchable.md"
    json_file = output_directory / "filing.searchable.json"
    called_with: list[Path] = []

    def fake_run_ocr(*args, **kwargs):
        return OcrResult(source, searchable, ("ocrmypdf",), "", "")

    def fake_run_docling(input_path, *args, **kwargs):
        called_with.append(input_path)
        return DoclingResult(input_path, markdown, json_file)

    monkeypatch.setattr(ocr_worker, "run_ocr", fake_run_ocr)
    monkeypatch.setattr(ocr_worker, "run_docling", fake_run_docling)
    worker = ProcessingWorker(
        (source,),
        output_directory,
        create_searchable_pdf=True,
        create_markdown=True,
        create_json=True,
        executable="ocrmypdf",
    )
    successes = []
    worker.file_succeeded.connect(lambda source_path, output: successes.append((source_path, output)))

    worker.run()

    assert called_with == [searchable]
    assert len(successes) == 1
    assert successes[0][0] == str(source)
    assert str(searchable) in successes[0][1]
    assert str(markdown) in successes[0][1]
    assert str(json_file) in successes[0][1]


def test_worker_continues_after_failure(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")

    def fake_run_ocr(input_path, output_directory, **kwargs):
        if input_path == first:
            raise OcrError("test failure")
        destination = output_directory / "second.searchable.pdf"
        return OcrResult(second, destination, ("ocrmypdf",), "", "")

    monkeypatch.setattr(ocr_worker, "run_ocr", fake_run_ocr)
    worker = ProcessingWorker(
        (first, second),
        tmp_path / "output",
        create_searchable_pdf=True,
        create_markdown=False,
        create_json=False,
        executable="ocrmypdf",
    )
    failures = []
    summaries = []
    worker.file_failed.connect(lambda source_path, error: failures.append((source_path, error)))
    worker.finished.connect(lambda cancelled, ok, failed: summaries.append((cancelled, ok, failed)))

    worker.run()

    assert failures == [(str(first), "test failure")]
    assert summaries == [(False, 1, 1)]


def test_worker_continues_after_fast_markdown_failure(monkeypatch, tmp_path: Path) -> None:
    first = tmp_path / "first.pdf"
    second = tmp_path / "second.pdf"
    first.write_bytes(b"%PDF-1.4\n")
    second.write_bytes(b"%PDF-1.4\n")
    output_directory = tmp_path / "output"

    def fake_run_docling(input_path, output_directory, **kwargs):
        if input_path == first:
            raise OcrError("Fast Markdown mode requires pypdf support in this runtime.")
        return DoclingResult(input_path, output_directory / "second.md", None)

    monkeypatch.setattr(ocr_worker, "run_docling", fake_run_docling)
    worker = ProcessingWorker(
        (first, second),
        output_directory,
        create_searchable_pdf=False,
        create_markdown=True,
        create_json=False,
        analysis_mode="fast",
    )
    failures = []
    successes = []
    summaries = []
    worker.file_failed.connect(lambda source_path, error: failures.append((source_path, error)))
    worker.file_succeeded.connect(lambda source_path, output: successes.append((source_path, output)))
    worker.finished.connect(lambda cancelled, ok, failed: summaries.append((cancelled, ok, failed)))

    worker.run()

    assert failures == [(str(first), "Fast Markdown mode requires pypdf support in this runtime.")]
    assert len(successes) == 1
    assert successes[0][0] == str(second)
    assert summaries == [(False, 1, 1)]


def test_worker_can_be_cancelled_before_start(tmp_path: Path) -> None:
    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    worker = ProcessingWorker(
        (source,),
        tmp_path / "output",
        create_searchable_pdf=True,
        create_markdown=False,
        create_json=False,
        executable="ocrmypdf",
    )
    summaries = []
    worker.finished.connect(lambda cancelled, ok, failed: summaries.append((cancelled, ok, failed)))

    worker.cancel()
    worker.run()

    assert summaries == [(True, 0, 0)]


def test_worker_reports_cancellation_from_docling_stage(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "filing.pdf"
    source.write_bytes(b"%PDF-1.4\n")

    def fake_run_docling(*args, **kwargs):
        raise OcrCancelledError("Processing cancelled: filing.pdf")

    monkeypatch.setattr(ocr_worker, "run_docling", fake_run_docling)
    worker = ProcessingWorker(
        (source,),
        tmp_path / "output",
        create_searchable_pdf=False,
        create_markdown=True,
        create_json=False,
    )
    summaries = []
    worker.finished.connect(lambda cancelled, ok, failed: summaries.append((cancelled, ok, failed)))

    worker.run()

    assert summaries == [(True, 0, 0)]
