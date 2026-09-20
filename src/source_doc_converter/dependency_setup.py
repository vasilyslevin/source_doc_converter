import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from platform import system
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from source_doc_converter.runtime_paths import find_executable, macos_finder_search_paths
from source_doc_converter.subprocess_utils import background_subprocess_kwargs
from source_doc_converter.system_diagnostics import (
    ComponentStatus,
    SystemDiagnostics,
    collect_system_diagnostics,
    installation_guidance,
)


@dataclass(frozen=True)
class DependencyInstallStep:
    key: str
    display_name: str
    command: tuple[str, ...]


WINDOWS_UV_WINGET_ID = "astral-sh.uv"
WINDOWS_TESSERACT_WINGET_ID = "UB-Mannheim.TesseractOCR"


class DependencySetupWorker(QObject):
    status_changed = Signal(str)
    details_changed = Signal(str)
    completed = Signal()
    failed = Signal(str)
    cancelled = Signal(str)
    finished = Signal()

    def __init__(
        self,
        *,
        diagnostics_provider=collect_system_diagnostics,
        steps_builder=None,
    ) -> None:
        super().__init__()
        self._diagnostics_provider = diagnostics_provider
        self._steps_builder = steps_builder or _default_steps
        self._cancel_event = Event()
        self._process: subprocess.Popen[str] | None = None
        self._details: list[str] = []

    @Slot()
    def run(self) -> None:
        cancelled_operation = "dependency setup"
        try:
            self.status_changed.emit("Checking dependencies…")
            diagnostics = self._diagnostics_provider()
            steps = self._steps_builder(diagnostics)
            if not steps:
                missing_ocr_tools = any(
                    not component.available
                    and component.key in {"ocrmypdf", "tesseract", "ghostscript"}
                    for component in diagnostics.components
                )
                if not missing_ocr_tools:
                    self.status_changed.emit("Ready")
                    self.completed.emit()
                    return
                if system() not in {"Windows", "Darwin"}:
                    message = (
                        "Guided OCR setup is available on Windows and macOS.\n\n"
                        f"{installation_guidance('ocrmypdf', system())}"
                    )
                    self.status_changed.emit("Manual setup required")
                    self.failed.emit(message)
                    return
                message = (
                    "Guided OCR setup is currently unavailable.\n\n"
                    f"{installation_guidance('ocrmypdf', system())}"
                )
                self.status_changed.emit("Manual setup required")
                self.failed.emit(message)
                return

            for step in steps:
                cancelled_operation = step.display_name
                if self._cancel_event.is_set():
                    self.status_changed.emit("Canceled")
                    self.cancelled.emit(f"Canceled {cancelled_operation}.")
                    return
                self.status_changed.emit(f"Installing {step.display_name}…")
                self._run_step(step)

            self.status_changed.emit("Rechecking dependencies…")
            post = self._diagnostics_provider()
            missing = [
                component.label
                for component in post.components
                if component.key in {step.key for step in steps} and not component.available
            ]
            if missing:
                message = "Dependency setup did not complete: " + ", ".join(missing)
                detail = "\n".join(self._details)
                if detail:
                    message = f"{message}\n\n{detail}"
                self.failed.emit(message)
                self.status_changed.emit("Failed")
                return
            self.status_changed.emit("Completed")
            self.completed.emit()
        except OSError as error:
            self.failed.emit(str(error))
            self.status_changed.emit("Failed")
        finally:
            self._process = None
            self.finished.emit()

    def cancel(self) -> None:
        self._cancel_event.set()
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def _run_step(self, step: DependencyInstallStep) -> None:
        command = _resolve_step_command(step)
        self._process = subprocess.Popen(
            list(command),
            shell=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            **background_subprocess_kwargs(),
        )
        while True:
            if self._cancel_event.is_set():
                self.cancel()
                self.status_changed.emit("Canceled")
                self.cancelled.emit(f"Canceled {step.display_name}.")
                return
            line = self._process.stdout.readline() if self._process.stdout is not None else ""
            if line:
                clean = line.rstrip("\r\n")
                if clean:
                    sanitized = _sanitize_detail(clean)
                    self._details.append(sanitized)
                    self.details_changed.emit(sanitized)
            elif self._process.poll() is not None:
                break
        if self._process.returncode != 0:
            detail = "\n".join(self._details).strip()
            message = f"Dependency setup failed while installing {step.display_name}."
            if detail:
                message = f"{message}\n\n{detail}"
            raise OSError(message)


def _default_steps(diagnostics: SystemDiagnostics) -> list[DependencyInstallStep]:
    active_system = system()
    missing: dict[str, ComponentStatus] = {
        component.key: component
        for component in diagnostics.components
        if not component.available
    }
    steps: list[DependencyInstallStep] = []
    if active_system == "Windows":
        if shutil.which("winget") is None:
            return []
        if "tesseract" in missing and _winget_package_available(WINDOWS_TESSERACT_WINGET_ID):
            steps.append(
                DependencyInstallStep(
                    "tesseract",
                    "Tesseract OCR",
                    ("winget", "install", "-e", "--id", WINDOWS_TESSERACT_WINGET_ID),
                )
            )
        if "ocrmypdf" in missing:
            uv_executable = _discover_windows_uv_executable()
            uv_will_be_available = uv_executable is not None
            if uv_executable is None and _winget_package_available(WINDOWS_UV_WINGET_ID):
                steps.append(
                    DependencyInstallStep(
                        "uv",
                        "uv",
                        ("winget", "install", "-e", "--id", WINDOWS_UV_WINGET_ID),
                    )
                )
                uv_will_be_available = True
            if uv_will_be_available:
                steps.append(
                    DependencyInstallStep(
                        "ocrmypdf",
                        "OCRmyPDF",
                        ("uv", "tool", "install", "ocrmypdf"),
                    )
                )
        return steps
    if active_system == "Darwin":
        brew_executable = find_executable("brew", extra_directories=macos_finder_search_paths())
        if brew_executable is None:
            return []
        if "ocrmypdf" in missing:
            steps.append(
                DependencyInstallStep(
                    "ocrmypdf",
                    "OCRmyPDF",
                    (brew_executable, "install", "ocrmypdf"),
                )
            )
        if "tesseract" in missing:
            steps.append(
                DependencyInstallStep(
                    "tesseract",
                    "Tesseract OCR",
                    (brew_executable, "install", "tesseract"),
                )
            )
        if "ghostscript" in missing:
            steps.append(
                DependencyInstallStep(
                    "ghostscript",
                    "Ghostscript",
                    (brew_executable, "install", "ghostscript"),
                )
            )
        return steps
    return steps


def _sanitize_detail(line: str) -> str:
    home = str(Path.home())
    if home:
        return line.replace(home, "<home>")
    return line


def _winget_package_available(package_id: str) -> bool:
    try:
        completed = subprocess.run(
            [
                "winget",
                "show",
                "-e",
                "--id",
                package_id,
                "--accept-source-agreements",
            ],
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            **background_subprocess_kwargs(),
        )
    except OSError:
        return False
    return completed.returncode == 0


def _windows_uv_candidate_paths() -> tuple[Path, ...]:
    paths: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        local = Path(local_app_data)
        paths.extend(
            [
                local / "Microsoft" / "WinGet" / "Links" / "uv.exe",
                local / "Programs" / "uv" / "uv.exe",
                local / "Programs" / "uv" / "bin" / "uv.exe",
            ]
        )
    program_files = os.environ.get("ProgramFiles", "").strip()
    if program_files:
        paths.append(Path(program_files) / "uv" / "uv.exe")
    return tuple(paths)


def _discover_windows_uv_executable() -> str | None:
    from_path = find_executable("uv")
    if from_path:
        return from_path
    for candidate in _windows_uv_candidate_paths():
        if candidate.is_file():
            return str(candidate.resolve())
    return None


def _resolve_step_command(step: DependencyInstallStep) -> tuple[str, ...]:
    if system() == "Windows" and step.command and step.command[0] == "uv":
        uv_executable = _discover_windows_uv_executable()
        if uv_executable is not None:
            return (uv_executable, *step.command[1:])
    return step.command
