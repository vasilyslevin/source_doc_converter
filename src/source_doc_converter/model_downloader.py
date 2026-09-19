import os
import re
import subprocess
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from source_doc_converter.model_management import (
    ModelManagementError,
    build_model_download_command,
    mark_models_ready,
)
from source_doc_converter.subprocess_utils import background_subprocess_kwargs

_SIZE_PROGRESS = re.compile(
    r"(?P<downloaded>\d+(?:\.\d+)?)\s*(?P<unit>[KMGTP]?B)\s*/\s*"
    r"(?P<total>\d+(?:\.\d+)?)\s*(?P<total_unit>[KMGTP]?B)",
    re.IGNORECASE,
)
_DOWNLOAD_NAME = re.compile(
    r"(?:downloading|fetching|retrieving)\s+(?P<name>[A-Za-z0-9._\-/]+)",
    re.IGNORECASE,
)
_URL_NAME = re.compile(r"https?://\S*/(?P<name>[^/\s?#]+)")


class ModelDownloadWorker(QObject):
    status_changed = Signal(str)
    details_changed = Signal(str)
    progress_changed = Signal(object)
    completed = Signal()
    failed = Signal(str)
    cancelled = Signal()
    finished = Signal()

    def __init__(
        self,
        model_directory: Path,
        *,
        command_prefix: list[str] | tuple[str, ...] | None = None,
    ) -> None:
        super().__init__()
        self._model_directory = model_directory.resolve()
        self._command_prefix = list(command_prefix) if command_prefix is not None else None
        self._cancel_event = Event()
        self._process: subprocess.Popen[str] | None = None
        self._detail_lines: list[str] = []

    @Slot()
    def run(self) -> None:
        try:
            if self._cancel_event.is_set():
                self.status_changed.emit("Canceled")
                self.cancelled.emit()
                return

            command = build_model_download_command(
                self._model_directory,
                command_prefix=self._command_prefix,
            )
            self._model_directory.mkdir(parents=True, exist_ok=True)
            self.status_changed.emit("Preparing download…")
            self.progress_changed.emit(None)
            self._process = subprocess.Popen(
                command,
                shell=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                **background_subprocess_kwargs(),
            )
            self.status_changed.emit("Downloading Docling model files…")
            output = self._read_output()

            if self._process.returncode != 0:
                detail = output.strip()
                message = "The model download did not complete."
                if detail:
                    separator = "\n\n" if "\n" in detail else " "
                    message = f"{message}{separator}{detail}"
                self.failed.emit(message)
                self.status_changed.emit("Failed")
                return

            self.status_changed.emit("Verifying checksum…")
            mark_models_ready(self._model_directory)
            self.status_changed.emit("Completed")
            self.completed.emit()
        except (OSError, ModelManagementError) as error:
            self.failed.emit(str(error))
            self.status_changed.emit("Failed")
        finally:
            self._process = None
            self.finished.emit()

    def cancel(self) -> None:
        self._cancel_event.set()

    def _stop_process(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        process.terminate()
        try:
            process.communicate(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.communicate()

    def _read_output(self) -> str:
        process = self._process
        if process is None:
            return ""
        while True:
            if self._cancel_event.is_set():
                self.status_changed.emit("Canceled")
                self._stop_process()
                self.cancelled.emit()
                return "\n".join(self._detail_lines)
            line = process.stdout.readline() if process.stdout is not None else ""
            if line:
                sanitized = _sanitize_output_line(line, self._model_directory)
                if sanitized:
                    self._detail_lines.append(sanitized)
                    self.details_changed.emit(sanitized)
                    line_status = _status_from_line(sanitized)
                    if line_status:
                        self.status_changed.emit(line_status)
                    size = _size_progress_from_line(sanitized)
                    if size is not None:
                        self.progress_changed.emit(size)
            elif process.poll() is not None:
                break
        remainder = ""
        if process.stdout is not None:
            remainder = process.stdout.read() or ""
        if remainder:
            for line in remainder.splitlines():
                sanitized = _sanitize_output_line(line, self._model_directory)
                if sanitized:
                    self._detail_lines.append(sanitized)
                    self.details_changed.emit(sanitized)
        return "\n".join(self._detail_lines)


def _sanitize_output_line(line: str, model_directory: Path) -> str:
    stripped = line.rstrip("\r\n")
    if not stripped:
        return ""
    sanitized = stripped.replace(str(model_directory), "<model-directory>")
    home = str(Path.home())
    if home:
        sanitized = sanitized.replace(home, "<home>")
    return sanitized


def _status_from_line(line: str) -> str | None:
    size = _size_progress_from_line(line)
    if size is not None:
        downloaded, total = size
        return f"Downloading Docling model files… {downloaded} / {total}"
    for pattern in (_URL_NAME, _DOWNLOAD_NAME):
        match = pattern.search(line)
        if match:
            name = os.path.basename(match.group("name"))
            if name:
                return f"Downloading {name}…"
    if "checksum" in line.lower() and "verify" in line.lower():
        return "Verifying checksum…"
    return None


def _size_progress_from_line(line: str) -> tuple[str, str] | None:
    match = _SIZE_PROGRESS.search(line)
    if not match:
        return None
    downloaded = f"{match.group('downloaded')} {match.group('unit').upper()}"
    total = f"{match.group('total')} {match.group('total_unit').upper()}"
    return downloaded, total
