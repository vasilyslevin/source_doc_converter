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
    def __init__(self, lines: list[str], returncode: int = 0) -> None:
        self.stdout = FakeStdout(lines)
        self.returncode = returncode

    def poll(self):
        return self.returncode

    def terminate(self):
        self.returncode = -15

    def kill(self):
        self.returncode = -9

    def communicate(self, timeout=None):
        return ("", "")


def test_multiline_downloader_failure_is_preserved(monkeypatch, qtbot, tmp_path: Path) -> None:
    output_lines = ["first warning\n", "Traceback: useful cause\n", "final exception\n"]
    monkeypatch.setattr(
        model_downloader.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(output_lines, 1),
    )
    worker = ModelDownloadWorker(tmp_path / "models", command_prefix=["docling-tools"])
    failures = []
    worker.failed.connect(failures.append)

    worker.run()

    assert len(failures) == 1
    assert "first warning" in failures[0]
    assert "final exception" in failures[0]


def test_status_streams_artifact_name_and_real_sizes(monkeypatch, qtbot, tmp_path: Path) -> None:
    lines = [
        "Downloading https://example.test/models/artifact.bin\n",
        "  12.0 MB / 50.0 MB\n",
    ]
    monkeypatch.setattr(
        model_downloader.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess(lines, 0),
    )
    monkeypatch.setattr(model_downloader, "mark_models_ready", lambda path: None)
    worker = ModelDownloadWorker(tmp_path / "models", command_prefix=["docling-tools"])
    statuses = []
    worker.status_changed.connect(statuses.append)

    worker.run()

    assert any("artifact.bin" in status for status in statuses)
    assert any("12.0 MB / 50.0 MB" in status for status in statuses)
    assert all("%" not in status for status in statuses)


def test_worker_sanitizes_model_path_in_details(monkeypatch, qtbot, tmp_path: Path) -> None:
    model_dir = (tmp_path / "models").resolve()
    line = f"writing file {model_dir / 'private.bin'}\n"
    monkeypatch.setattr(
        model_downloader.subprocess,
        "Popen",
        lambda *args, **kwargs: FakeProcess([line], 1),
    )
    worker = ModelDownloadWorker(model_dir, command_prefix=["docling-tools"])
    details = []
    worker.details_changed.connect(details.append)

    worker.run()

    assert details
    assert "<model-directory>" in details[0]
    assert str(model_dir) not in details[0]
