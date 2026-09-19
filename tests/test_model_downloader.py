import subprocess
from pathlib import Path

from source_doc_converter import model_downloader
from source_doc_converter.model_downloader import ModelDownloadWorker


class FakeStdout:
    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        return ""

    def read(self) -> str:
        return "".join(self._lines)


class FakeProcess:
    def __init__(self, lines: list[str], returncode: int = 0, cancel_on_read: bool = False) -> None:
        self.returncode = returncode
        self.stdout = FakeStdout(lines)
        self._terminated = False
        self._cancel_on_read = cancel_on_read
        self._calls = 0

    def poll(self):
        self._calls += 1
        if self._cancel_on_read and self._calls == 1:
            return None
        return self.returncode

    def communicate(self, timeout=None):
        if timeout == 5 and self._cancel_on_read and not self._terminated:
            raise subprocess.TimeoutExpired("docling-tools", timeout=timeout)
        return ("", "")

    def terminate(self):
        self._terminated = True

    def kill(self):
        self.returncode = -9


def test_worker_uses_safe_subprocess_arguments(monkeypatch, qtbot, tmp_path: Path) -> None:
    captured = {}
    marked = []

    def fake_popen(command, **kwargs):
        captured["command"] = command
        captured["kwargs"] = kwargs
        return FakeProcess(["done\n"], 0)

    monkeypatch.setattr(model_downloader.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(model_downloader, "mark_models_ready", marked.append)
    worker = ModelDownloadWorker(
        tmp_path / "models", command_prefix=["SourceDocumentConverter", "--internal-docling-tools"]
    )
    completed = []
    worker.completed.connect(lambda: completed.append(True))

    worker.run()

    assert captured["command"] == [
        "SourceDocumentConverter",
        "--internal-docling-tools",
        "models",
        "download",
        "-o",
        str((tmp_path / "models").resolve()),
    ]
    assert captured["kwargs"]["shell"] is False
    assert captured["kwargs"]["encoding"] == "utf-8"
    assert marked == [(tmp_path / "models").resolve()]
    assert completed == [True]


def test_worker_reports_downloader_failure(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(
        model_downloader.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(["safe failure detail\n"], 1),
    )
    worker = ModelDownloadWorker(tmp_path / "models", command_prefix=["docling-tools"])
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert failures == ["The model download did not complete. safe failure detail"]


def test_worker_can_be_cancelled_before_start(qtbot, tmp_path: Path) -> None:
    worker = ModelDownloadWorker(tmp_path / "models", command_prefix=["docling-tools"])
    cancellations = []
    worker.cancelled.connect(lambda: cancellations.append(True))

    worker.cancel()
    worker.run()

    assert cancellations == [True]


def test_worker_terminates_a_cancelled_process(monkeypatch, qtbot, tmp_path: Path) -> None:
    process = FakeProcess([], 0, cancel_on_read=True)

    def fake_popen(*args, **kwargs):
        worker.cancel()
        return process

    monkeypatch.setattr(model_downloader.subprocess, "Popen", fake_popen)
    worker = ModelDownloadWorker(tmp_path / "models", command_prefix=["docling-tools"])

    worker.run()

    assert process._terminated
