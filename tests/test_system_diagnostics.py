import subprocess
from importlib.machinery import ModuleSpec

from source_doc_converter import system_diagnostics
from source_doc_converter.system_diagnostics import (
    ComponentStatus,
    SystemDiagnostics,
    check_docling,
    check_ghostscript,
    check_ocrmypdf,
    check_tesseract,
)


def test_ocrmypdf_version_success(monkeypatch) -> None:
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_ocrmypdf_executable",
        lambda: "/tools/ocrmypdf",
    )
    monkeypatch.setattr(
        system_diagnostics,
        "_run_command",
        lambda command: (True, "17.11.0\n", None),
    )

    result = check_ocrmypdf()

    assert result.available
    assert result.version == "17.11.0"


def test_missing_executable(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics, "resolve_ocrmypdf_executable", lambda: None)

    result = check_ocrmypdf()

    assert not result.available
    assert result.error == "Executable not found"


def test_command_timeout(monkeypatch) -> None:
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired(args[0], timeout=5)

    monkeypatch.setattr(system_diagnostics.subprocess, "run", timeout)

    succeeded, output, error = system_diagnostics._run_command(["tool", "--version"])

    assert not succeeded
    assert output == ""
    assert error == "Command timed out"


def test_tesseract_languages(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics, "discover_tesseract_installations", lambda: ())
    monkeypatch.setattr(system_diagnostics, "resolve_tesseract_profile", lambda **kwargs: None)
    monkeypatch.setattr(
        system_diagnostics,
        "resolve_tesseract_executable",
        lambda: ("/tools/tesseract", "system"),
    )
    monkeypatch.setattr(system_diagnostics, "build_ocr_environment", lambda profile: {})
    responses = iter(
        [
            (True, "tesseract 5.5.1\n", None),
            (True, "List of available languages in data path (2):\neng\nspa\n", None),
        ]
    )
    monkeypatch.setattr(
        system_diagnostics,
        "_run_command",
        lambda command, **kwargs: next(responses),
    )

    result = check_tesseract()

    assert result.available
    assert result.version == "tesseract 5.5.1"
    assert result.details == (
        "Required for searchable PDF output.",
        "Source: system",
        "Languages: eng, spa",
    )


def test_missing_tesseract_has_clear_error(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics, "discover_tesseract_installations", lambda: ())
    monkeypatch.setattr(system_diagnostics, "resolve_tesseract_executable", lambda: (None, "missing"))

    result = check_tesseract()

    assert not result.available
    assert result.details == ("Required for searchable PDF output.",)
    assert result.error == "Executable not found"


def test_missing_docling_package(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics.importlib_util, "find_spec", lambda name: None)

    result = check_docling()

    assert not result.available
    assert result.error == "Package not installed"


def test_missing_pypdf_package(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics.importlib_util, "find_spec", lambda name: None)

    result = system_diagnostics.check_pypdf()

    assert not result.available
    assert result.error == "Package not installed"


def test_docling_version_without_importing_models(monkeypatch) -> None:
    monkeypatch.setattr(
        system_diagnostics.importlib_util,
        "find_spec",
        lambda name: ModuleSpec(name, loader=None),
    )
    monkeypatch.setattr(system_diagnostics.importlib_metadata, "version", lambda name: "2.50.0")

    result = check_docling()

    assert result.available
    assert result.version == "2.50.0"


def test_diagnostic_report_contains_no_sensitive_paths() -> None:
    report = SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="TestOS",
        operating_system_version="1",
        architecture="test-arch",
        python_version="3.12.0",
        pyside_version="6.9.0",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True, "17.0.0"),
            ComponentStatus("tesseract", "Tesseract OCR", True, "5.5.0", ("Languages: eng",)),
            ComponentStatus("ghostscript", "Ghostscript", True, "10.0.0"),
            ComponentStatus("docling", "Docling", False, error="Package not installed"),
        ),
    )

    text = report.to_text()

    assert "OCRmyPDF: Available (17.0.0)" in text
    assert "Docling: Unavailable" in text
    assert "username" not in text.lower()
    assert "secret.pdf" not in text
    assert "/home/" not in text
    assert "C:\\Users\\" not in text


def test_platform_specific_guidance() -> None:
    assert "Homebrew" in system_diagnostics.installation_guidance("ocrmypdf", "Darwin")
    assert "ghostscript" in system_diagnostics.installation_guidance("ocrmypdf", "Darwin").lower()
    assert "winget" in system_diagnostics.installation_guidance("tesseract", "Windows")
    assert "package manager" in system_diagnostics.installation_guidance("ocrmypdf", "Linux")
    assert "pypdf" in system_diagnostics.installation_guidance("pypdf", "Linux")


def test_ghostscript_missing_executable(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics, "resolve_ghostscript_executable", lambda *args, **kwargs: None)

    result = check_ghostscript()

    assert not result.available
    assert result.error == "Executable not found"


def test_ghostscript_diagnostics_on_macos_uses_source_label(monkeypatch) -> None:
    monkeypatch.setattr(system_diagnostics.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(system_diagnostics, "macos_finder_search_paths", lambda: ("/opt/homebrew/bin",))
    monkeypatch.setattr(system_diagnostics, "resolve_ghostscript_executable", lambda *args, **kwargs: "/opt/homebrew/bin/gs")
    monkeypatch.setattr(system_diagnostics, "_run_command", lambda command: (True, "10.0.0\n", None))

    result = check_ghostscript()

    assert result.available
    assert result.details == ("Required for searchable PDF output.", "Source: Homebrew")
    assert "/opt/homebrew/bin/gs" not in "\n".join(result.details)
