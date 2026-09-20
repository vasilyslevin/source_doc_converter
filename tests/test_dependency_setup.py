from pathlib import Path

from source_doc_converter import dependency_setup
from source_doc_converter.dependency_setup import DependencyInstallStep, DependencySetupWorker
from source_doc_converter.system_diagnostics import ComponentStatus, SystemDiagnostics


def diagnostics(missing: tuple[str, ...]) -> SystemDiagnostics:
    return SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="Windows",
        operating_system_version="11",
        architecture="x64",
        python_version="3.12",
        pyside_version="6.9",
        components=tuple(
            ComponentStatus(key, key, key not in missing)
            for key in ("ocrmypdf", "tesseract", "ghostscript", "docling")
        ),
    )


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        return ""


class FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = FakeStdout(lines)
        self.returncode = returncode
        self.terminated = False

    def poll(self):
        return self.returncode

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.returncode = -9

    def communicate(self, timeout=None):
        return ("", "")


def test_dependency_setup_status_transitions(monkeypatch, qtbot) -> None:
    checks = iter((diagnostics(("ocrmypdf",)), diagnostics(())))
    monkeypatch.setattr(
        dependency_setup.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(["installing OCRmyPDF\n"], 0),
    )
    worker = DependencySetupWorker(
        diagnostics_provider=lambda: next(checks),
        steps_builder=lambda _: [
            DependencyInstallStep("ocrmypdf", "OCRmyPDF", ("winget", "install")),
        ],
    )
    statuses = []
    worker.status_changed.connect(statuses.append)

    worker.run()

    assert statuses[0] == "Checking dependencies…"
    assert "Installing OCRmyPDF…" in statuses
    assert "Rechecking dependencies…" in statuses
    assert statuses[-1] == "Completed"


def test_dependency_setup_cancellation_reports_target(monkeypatch, qtbot) -> None:
    process = FakeProcess([], 0)
    worker = DependencySetupWorker(
        diagnostics_provider=lambda: diagnostics(("tesseract",)),
        steps_builder=lambda _: [
            DependencyInstallStep("tesseract", "Tesseract OCR", ("winget", "install")),
        ],
    )

    def fake_popen(*args, **kwargs):
        worker.cancel()
        return process

    monkeypatch.setattr(dependency_setup.subprocess, "Popen", fake_popen)
    cancelled = []
    worker.cancelled.connect(cancelled.append)

    worker.run()

    assert cancelled
    assert "Tesseract OCR" in cancelled[0]


def test_dependency_setup_failure_preserves_full_details(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        dependency_setup.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(["line one\n", "line two\n"], 1),
    )
    worker = DependencySetupWorker(
        diagnostics_provider=lambda: diagnostics(("ocrmypdf",)),
        steps_builder=lambda _: [
            DependencyInstallStep("ocrmypdf", "OCRmyPDF", ("winget", "install")),
        ],
    )
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures
    assert "line one" in failures[0]
    assert "line two" in failures[0]


def test_dependency_setup_reports_uv_install_failure(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        dependency_setup.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(["uv install failed\n"], 1),
    )
    worker = DependencySetupWorker(
        diagnostics_provider=lambda: diagnostics(("ocrmypdf",)),
        steps_builder=lambda _: [
            DependencyInstallStep("uv", "uv", ("winget", "install", "-e", "--id", "astral-sh.uv")),
        ],
    )
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures
    assert "installing uv" in failures[0].lower()
    assert "uv install failed" in failures[0]


def test_default_steps_on_macos_require_homebrew(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Darwin")
    monkeypatch.setattr(dependency_setup, "find_executable", lambda *_args, **_kwargs: None)

    steps = dependency_setup._default_steps(diagnostics(("ocrmypdf", "tesseract", "ghostscript")))

    assert steps == []


def test_default_steps_on_macos_use_finder_safe_homebrew_path(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Darwin")
    monkeypatch.setattr(
        dependency_setup,
        "macos_finder_search_paths",
        lambda: ("/opt/homebrew/bin", "/usr/local/bin"),
    )

    def fake_find_executable(name: str, **kwargs) -> str | None:
        assert name == "brew"
        assert kwargs["extra_directories"] == ("/opt/homebrew/bin", "/usr/local/bin")
        return "/opt/homebrew/bin/brew"

    monkeypatch.setattr(dependency_setup, "find_executable", fake_find_executable)

    steps = dependency_setup._default_steps(diagnostics(("ocrmypdf",)))

    assert len(steps) == 1
    assert steps[0].command == ("/opt/homebrew/bin/brew", "install", "ocrmypdf")


def test_default_steps_on_windows_with_only_missing_ghostscript(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Windows")
    monkeypatch.setattr(dependency_setup.shutil, "which", lambda _: "winget")
    monkeypatch.setattr(dependency_setup, "_winget_package_available", lambda _package_id: True)

    steps = dependency_setup._default_steps(diagnostics(("ghostscript",)))

    assert steps == []


def test_default_steps_on_windows_with_missing_uv_adds_uv_and_ocrmypdf(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Windows")
    monkeypatch.setattr(dependency_setup.shutil, "which", lambda _: "winget")
    monkeypatch.setattr(dependency_setup, "_discover_windows_uv_executable", lambda: None)
    monkeypatch.setattr(dependency_setup, "_winget_package_available", lambda _package_id: True)

    steps = dependency_setup._default_steps(diagnostics(("ocrmypdf",)))

    assert [step.key for step in steps] == ["uv", "ocrmypdf"]
    assert steps[0].command == ("winget", "install", "-e", "--id", "astral-sh.uv")
    assert steps[1].command == ("uv", "tool", "install", "ocrmypdf")


def test_default_steps_on_windows_with_existing_uv_installs_ocrmypdf_only(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Windows")
    monkeypatch.setattr(dependency_setup.shutil, "which", lambda _: "winget")
    monkeypatch.setattr(
        dependency_setup,
        "_discover_windows_uv_executable",
        lambda: "C:/Users/test/.local/bin/uv.exe",
    )
    monkeypatch.setattr(dependency_setup, "_winget_package_available", lambda _package_id: True)

    steps = dependency_setup._default_steps(diagnostics(("ocrmypdf",)))

    assert [step.key for step in steps] == ["ocrmypdf"]
    assert steps[0].command == ("uv", "tool", "install", "ocrmypdf")


def test_default_steps_on_windows_skips_ocrmypdf_when_uv_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Windows")
    monkeypatch.setattr(dependency_setup.shutil, "which", lambda _: "winget")
    monkeypatch.setattr(dependency_setup, "_discover_windows_uv_executable", lambda: None)
    monkeypatch.setattr(
        dependency_setup,
        "_winget_package_available",
        lambda package_id: package_id != "astral-sh.uv",
    )

    steps = dependency_setup._default_steps(diagnostics(("ocrmypdf",)))

    assert [step.key for step in steps] == []


def test_resolve_uv_step_command_after_winget_install(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Windows")
    monkeypatch.setattr(
        dependency_setup,
        "_discover_windows_uv_executable",
        lambda: str(tmp_path / "links" / "uv.exe"),
    )
    command = dependency_setup._resolve_step_command(
        DependencyInstallStep("ocrmypdf", "OCRmyPDF", ("uv", "tool", "install", "ocrmypdf"))
    )

    assert command == (str(tmp_path / "links" / "uv.exe"), "tool", "install", "ocrmypdf")


def test_dependency_setup_reports_manual_setup_when_no_guided_installer(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(dependency_setup, "system", lambda: "Darwin")
    worker = DependencySetupWorker(
        diagnostics_provider=lambda: diagnostics(("ocrmypdf", "tesseract", "ghostscript")),
        steps_builder=lambda _: [],
    )
    failures = []
    completed = []
    statuses = []
    worker.failed.connect(failures.append)
    worker.completed.connect(lambda: completed.append(True))
    worker.status_changed.connect(statuses.append)

    worker.run()

    assert not completed
    assert failures
    assert "Homebrew" in failures[0]
    assert statuses[-1] == "Manual setup required"
