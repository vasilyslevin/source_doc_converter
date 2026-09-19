from contextlib import nullcontext
from pathlib import Path

import pytest

from source_doc_converter import ocr_pipeline
from source_doc_converter.docling_runtime import ConverterBuildMetrics
from source_doc_converter.ocr_pipeline import (
    OcrError,
    OcrPageAnalysis,
    OcrValidationReport,
    build_ocr_command,
    run_docling,
    run_ocr,
)


def test_build_ocr_command_uses_jobs_and_skip_text() -> None:
    command = build_ocr_command(
        Path("filing.pdf"),
        Path("Converted/filing.searchable.pdf"),
        executable="/tools/ocrmypdf",
        language="eng",
        mode="skip",
    )

    assert command[:6] == [
        "/tools/ocrmypdf",
        "--output-type",
        "pdf",
        "--jobs",
        "2",
        "--skip-text",
    ]


def test_smart_preflight_selects_redo_before_first_invocation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "mixed.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    calls: list[tuple[str, ...]] = []

    class FakeProcess:
        returncode = 0

        def __init__(self, command, **kwargs):
            calls.append(tuple(command))
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"%PDF-1.4\n")

        def communicate(self, timeout=None):
            return "", ""

    monkeypatch.setattr(ocr_pipeline, "find_ocrmypdf", lambda: "/tools/ocrmypdf")
    monkeypatch.setattr(ocr_pipeline, "resolve_tesseract_profile", lambda: None)
    monkeypatch.setattr(ocr_pipeline, "build_ocr_environment", lambda profile: {})
    monkeypatch.setattr(
        ocr_pipeline,
        "_smart_preflight_decision",
        lambda path: ocr_pipeline.SmartPreflightDecision("redo", "mixed", ("preflight",)),
    )
    monkeypatch.setattr(
        ocr_pipeline,
        "_validate_pdf_text",
        lambda path: OcrValidationReport((1,), (), (), ()),
    )
    monkeypatch.setattr(ocr_pipeline.subprocess, "Popen", FakeProcess)

    result = run_ocr(source, tmp_path / "out", mode="smart")

    assert calls
    assert "--redo-ocr" in calls[0]
    assert "--skip-text" not in calls[0]
    assert result.effective_mode == "redo"


def test_blank_pages_do_not_produce_false_validation_failures(monkeypatch) -> None:
    monkeypatch.setattr(
        ocr_pipeline,
        "_analyze_pdf_pages",
        lambda path: (
            OcrPageAnalysis(page_number=1, text="", has_raster_content=False),
            OcrPageAnalysis(page_number=2, text="", has_raster_content=False),
        ),
    )

    report = ocr_pipeline._validate_pdf_text(Path("ignored.pdf"))

    assert report is not None
    assert report.blank_pages == (1, 2)
    assert report.weak_pages == ()


def test_smart_preflight_detects_ecf_header_over_scanned_body(monkeypatch) -> None:
    header = "Case 1:23-cv-00001 Doc 12 Filed 10/02/2026 Page 1 of 2"
    monkeypatch.setattr(
        ocr_pipeline,
        "_analyze_pdf_pages",
        lambda path: (
            OcrPageAnalysis(page_number=1, text=header, has_raster_content=True),
            OcrPageAnalysis(page_number=2, text=header, has_raster_content=True),
        ),
    )

    decision = ocr_pipeline._smart_preflight_decision(Path("synthetic.pdf"))

    assert decision.selected_mode == "redo"
    assert any("mixed searchable-header pages" in warning for warning in decision.warnings)


def test_auto_analysis_chooses_fast_for_searchable_markdown(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "searchable.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    monkeypatch.setattr(
        ocr_pipeline,
        "_validate_pdf_text",
        lambda path: OcrValidationReport((1,), (), (), ()),
    )
    monkeypatch.setattr(
        ocr_pipeline,
        "_fast_markdown_export",
        lambda path: "Case 1\n\n<!-- PDF_PAGE_BREAK -->\n\nDoc 2",
    )

    result = run_docling(
        source,
        tmp_path / "out",
        export_markdown=True,
        export_json=False,
        analysis_mode="auto",
    )

    assert result.effective_analysis_mode == "fast"
    text = (tmp_path / "out" / "searchable.md").read_text(encoding="utf-8")
    assert "<!-- PDF_PAGE_BREAK -->" in text
    assert "Case 1" in text


def test_auto_analysis_chooses_accurate_when_json_required(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "structured.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    model_dir = tmp_path / "models"
    model_dir.mkdir()

    class FakeDocument:
        def export_to_markdown(self, *, page_break_placeholder: str) -> str:
            return "md"

        def export_to_dict(self) -> dict[str, str]:
            return {"k": "v"}

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, input_path: Path):
            return FakeResult()

    monkeypatch.setattr(ocr_pipeline, "require_ready_model_directory", lambda _: model_dir)
    monkeypatch.setattr(
        ocr_pipeline,
        "create_local_pdf_converter_with_metrics",
        lambda *args, **kwargs: (FakeConverter(), ConverterBuildMetrics(cache_hit=True, init_seconds=0)),
    )
    monkeypatch.setattr(
        ocr_pipeline,
        "offline_environment",
        lambda *args, **kwargs: nullcontext(),
    )

    result = run_docling(
        source,
        tmp_path / "out",
        export_markdown=True,
        export_json=True,
        analysis_mode="auto",
    )

    assert result.effective_analysis_mode == "accurate"
    assert any("JSON export requires standard pipeline" in warning for warning in result.warnings)


def test_fast_mode_json_request_falls_back_with_warning(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "fallback.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    model_dir = tmp_path / "models"
    model_dir.mkdir()
    captured: dict[str, object] = {}

    class FakeDocument:
        def export_to_markdown(self, *, page_break_placeholder: str) -> str:
            return "md"

        def export_to_dict(self) -> dict[str, str]:
            return {"k": "v"}

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, input_path: Path):
            captured["convert"] = input_path
            return FakeResult()

    monkeypatch.setattr(ocr_pipeline, "require_ready_model_directory", lambda _: model_dir)
    monkeypatch.setattr(
        ocr_pipeline,
        "create_local_pdf_converter_with_metrics",
        lambda *args, **kwargs: (
            FakeConverter(),
            ConverterBuildMetrics(cache_hit=False, init_seconds=0.1),
        ),
    )
    monkeypatch.setattr(
        ocr_pipeline,
        "offline_environment",
        lambda *args, **kwargs: nullcontext(),
    )

    result = run_docling(
        source,
        tmp_path / "out",
        export_markdown=True,
        export_json=True,
        analysis_mode="fast",
    )

    assert result.effective_analysis_mode == "accurate"
    assert any("incompatible with JSON export" in warning for warning in result.warnings)
    assert (tmp_path / "out" / "fallback.md").is_file()
    assert (tmp_path / "out" / "fallback.json").is_file()


def test_auto_mode_falls_back_when_fast_preflight_unavailable(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "no-pypdf.pdf"
    source.write_bytes(b"%PDF-1.4\n")
    model_dir = tmp_path / "models"
    model_dir.mkdir()

    class FakeDocument:
        def export_to_markdown(self, *, page_break_placeholder: str) -> str:
            return "md"

    class FakeResult:
        document = FakeDocument()

    class FakeConverter:
        def convert(self, input_path: Path):
            return FakeResult()

    monkeypatch.setattr(ocr_pipeline, "_validate_pdf_text", lambda _: None)
    monkeypatch.setattr(ocr_pipeline, "require_ready_model_directory", lambda _: model_dir)
    monkeypatch.setattr(
        ocr_pipeline,
        "create_local_pdf_converter_with_metrics",
        lambda *args, **kwargs: (FakeConverter(), ConverterBuildMetrics(cache_hit=False, init_seconds=0)),
    )
    monkeypatch.setattr(ocr_pipeline, "offline_environment", lambda *args, **kwargs: nullcontext())

    result = run_docling(
        source,
        tmp_path / "out",
        export_markdown=True,
        export_json=False,
        analysis_mode="auto",
    )

    assert result.effective_analysis_mode == "accurate"
    assert any("could not preflight" in warning for warning in result.warnings)


def test_fast_mode_without_pypdf_reports_actionable_error(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "fast.pdf"
    source.write_bytes(b"%PDF-1.4\n")

    monkeypatch.setattr(
        ocr_pipeline,
        "_fast_markdown_export",
        lambda _: (_ for _ in ()).throw(
            OcrError(
                "Fast Markdown mode requires pypdf support in this runtime. "
                "Install pypdf and retry, or choose Accurate Markdown."
            )
        ),
    )

    with pytest.raises(OcrError, match="Install pypdf and retry"):
        run_docling(
            source,
            tmp_path / "out",
            export_markdown=True,
            export_json=False,
            analysis_mode="fast",
        )


def test_ocr_timing_contains_preflight_and_validation(monkeypatch, tmp_path: Path) -> None:
    source = tmp_path / "timed.pdf"
    source.write_bytes(b"%PDF-1.4\n")

    class FakeProcess:
        returncode = 0

        def __init__(self, command, **kwargs):
            Path(command[-1]).parent.mkdir(parents=True, exist_ok=True)
            Path(command[-1]).write_bytes(b"%PDF-1.4\n")

        def communicate(self, timeout=None):
            return "", ""

    ticks = iter([10.0, 10.2, 10.3, 11.0, 11.1, 11.3, 11.4, 11.5])
    monkeypatch.setattr(ocr_pipeline.time, "monotonic", lambda: next(ticks))
    monkeypatch.setattr(ocr_pipeline, "find_ocrmypdf", lambda: "/tools/ocrmypdf")
    monkeypatch.setattr(ocr_pipeline, "resolve_tesseract_profile", lambda: None)
    monkeypatch.setattr(ocr_pipeline, "build_ocr_environment", lambda profile: {})
    monkeypatch.setattr(
        ocr_pipeline,
        "_smart_preflight_decision",
        lambda path: ocr_pipeline.SmartPreflightDecision("skip", "searchable", ()),
    )
    monkeypatch.setattr(
        ocr_pipeline,
        "_validate_pdf_text",
        lambda path: OcrValidationReport((1,), (), (), ()),
    )
    monkeypatch.setattr(ocr_pipeline.subprocess, "Popen", FakeProcess)

    result = run_ocr(source, tmp_path / "out", mode="smart")
    timing_names = [name for name, _value in result.timings]

    assert "PDF/OCR preflight" in timing_names
    assert "OCRmyPDF" in timing_names
    assert "Post-OCR validation" in timing_names


def test_missing_input_is_rejected(tmp_path: Path) -> None:
    with pytest.raises(OcrError, match="does not exist"):
        run_ocr(tmp_path / "missing.pdf", tmp_path / "output", executable="ocrmypdf")
