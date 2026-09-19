from pathlib import Path

from source_doc_converter import system_diagnostics
from source_doc_converter.model_management import ModelDirectoryState


def test_docling_output_requires_installed_local_models(monkeypatch) -> None:
    monkeypatch.setattr(
        system_diagnostics,
        "_python_package_available",
        lambda package: package == "docling",
    )
    monkeypatch.setattr(
        system_diagnostics,
        "load_model_directory",
        lambda: ModelDirectoryState(Path("models"), "settings", False),
    )
    monkeypatch.setattr(system_diagnostics, "resolve_ocrmypdf_executable", lambda: "/tools/ocrmypdf")
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_tesseract_executable",
        lambda: ("/tools/tesseract", "system"),
    )
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_ghostscript_executable",
        lambda: "/tools/gs",
    )

    availability = system_diagnostics.check_output_availability()

    assert availability.searchable_pdf
    assert not availability.docling
    assert availability.docling_reason is not None
    assert "models are not ready" in availability.docling_reason


def test_docling_output_is_available_when_package_and_models_are_ready(monkeypatch) -> None:
    monkeypatch.setattr(
        system_diagnostics,
        "_python_package_available",
        lambda package: package == "docling",
    )
    monkeypatch.setattr(
        system_diagnostics,
        "load_model_directory",
        lambda: ModelDirectoryState(Path("models"), "settings", True),
    )
    monkeypatch.setattr(system_diagnostics, "resolve_ocrmypdf_executable", lambda: None)
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_tesseract_executable",
        lambda: (None, "missing"),
    )
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_ghostscript_executable",
        lambda: "/tools/gs",
    )

    availability = system_diagnostics.check_output_availability()

    assert not availability.searchable_pdf
    assert availability.docling
    assert availability.docling_reason is None


def test_searchable_pdf_does_not_require_ghostscript(monkeypatch) -> None:
    monkeypatch.setattr(
        system_diagnostics,
        "_python_package_available",
        lambda package: package == "docling",
    )
    monkeypatch.setattr(
        system_diagnostics,
        "load_model_directory",
        lambda: ModelDirectoryState(Path("models"), "settings", True),
    )
    monkeypatch.setattr(system_diagnostics, "resolve_ocrmypdf_executable", lambda: "/tools/ocrmypdf")
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_tesseract_executable",
        lambda: ("/tools/tesseract", "system"),
    )
    monkeypatch.setattr(system_diagnostics, "resolve_ghostscript_executable", lambda: None)

    availability = system_diagnostics.check_output_availability()

    assert availability.searchable_pdf
