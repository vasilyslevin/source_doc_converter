import os
import sys
from pathlib import Path
from types import ModuleType

from source_doc_converter import app as application_entry
from source_doc_converter import docling_tools_entry, ocrmypdf_entry


def test_package_smoke_test_checks_window_and_companion(monkeypatch) -> None:
    events = []

    class FakeWindow:
        def __init__(self) -> None:
            events.append("window")

        def close(self) -> None:
            events.append("closed")

    monkeypatch.setattr(application_entry, "ApplicationWindow", FakeWindow)
    monkeypatch.setattr(
        application_entry,
        "resolve_model_downloader",
        lambda: events.append("companion") or ["docling-tools.exe"],
    )
    monkeypatch.setattr(application_entry, "is_packaged_application", lambda: False)
    pypdf_module = ModuleType("pypdf")
    pypdf_module.PdfReader = type("FakePdfReader", (), {})
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)

    assert application_entry.run_package_smoke_test() == 0
    assert events == ["window", "closed", "companion"]


def test_prepare_packaged_path_is_noop(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "SourceDocumentConverter.exe"
    monkeypatch.setattr(application_entry.sys, "executable", str(executable))
    monkeypatch.setenv("PATH", str(tmp_path / "existing"))
    monkeypatch.setattr(application_entry, "is_packaged_application", lambda: False)

    application_entry.prepare_packaged_path()

    assert os.environ["PATH"] == str(tmp_path / "existing")


def test_prepare_packaged_path_includes_app_and_macos_prefixes(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "SourceDocumentConverter"
    monkeypatch.setattr(application_entry.sys, "executable", str(executable))
    monkeypatch.setattr(application_entry, "is_packaged_application", lambda: True)
    monkeypatch.setattr(application_entry, "build_subprocess_path", lambda **_: "A:B:C")
    monkeypatch.setenv("PATH", "old")

    application_entry.prepare_packaged_path()

    assert os.environ["PATH"] == "A:B:C"


def test_main_calls_freeze_support(monkeypatch) -> None:
    called = []
    monkeypatch.setattr(application_entry.multiprocessing, "freeze_support", lambda: called.append(True))
    monkeypatch.setattr(application_entry, "prepare_packaged_path", lambda: None)
    monkeypatch.setattr(application_entry, "QApplication", lambda args: type("A", (), {"setOrganizationName": lambda *a: None, "setApplicationName": lambda *a: None, "setWindowIcon": lambda *a: None, "exec": lambda self: 0})())
    monkeypatch.setattr(application_entry, "migrate_legacy_settings", lambda: None)
    monkeypatch.setattr(application_entry, "ApplicationWindow", lambda: type("W", (), {"show": lambda self: None})())
    monkeypatch.setattr(application_entry, "show_first_run_privacy_notice", lambda window: None)
    monkeypatch.setattr(application_entry, "QIcon", lambda path: object())
    monkeypatch.setattr(application_entry.sys, "argv", ["source-doc-converter"])

    assert application_entry.main() == 0
    assert called == [True]


def test_docling_tools_entry_invokes_upstream_cli(monkeypatch) -> None:
    calls = []
    docling_module = ModuleType("docling")
    cli_module = ModuleType("docling.cli")
    tools_module = ModuleType("docling.cli.tools")
    tools_module.app = lambda **kwargs: calls.append(kwargs)
    monkeypatch.setitem(sys.modules, "docling", docling_module)
    monkeypatch.setitem(sys.modules, "docling.cli", cli_module)
    monkeypatch.setitem(sys.modules, "docling.cli.tools", tools_module)

    assert docling_tools_entry.main() == 0
    assert calls == [{"prog_name": "docling-tools"}]


def test_ocrmypdf_entry_invokes_upstream_cli(monkeypatch) -> None:
    calls = []
    ocrmypdf_module = ModuleType("ocrmypdf")
    main_module = ModuleType("ocrmypdf.__main__")
    main_module.run = lambda: calls.append("run") or 0
    monkeypatch.setitem(sys.modules, "ocrmypdf", ocrmypdf_module)
    monkeypatch.setitem(sys.modules, "ocrmypdf.__main__", main_module)

    assert ocrmypdf_entry.main() == 0
    assert calls == ["run"]


def test_main_dispatches_docling_tools_mode_without_gui(monkeypatch) -> None:
    calls = []
    monkeypatch.setattr(application_entry.multiprocessing, "freeze_support", lambda: None)
    monkeypatch.setattr(application_entry, "prepare_packaged_path", lambda: None)
    monkeypatch.setattr(application_entry, "QApplication", lambda args: (_ for _ in ()).throw(AssertionError("QApplication should not be created")))
    monkeypatch.setattr(
        application_entry,
        "run_docling_tools_command",
        lambda arguments: calls.append(arguments) or 0,
    )
    monkeypatch.setattr(
        application_entry.sys,
        "argv",
        ["source-doc-converter", "--internal-docling-tools", "--runtime-check"],
    )

    assert application_entry.main() == 0
    assert calls == [["--runtime-check"]]


def test_main_propagates_internal_docling_tools_exit_code(monkeypatch) -> None:
    monkeypatch.setattr(application_entry.multiprocessing, "freeze_support", lambda: None)
    monkeypatch.setattr(application_entry, "prepare_packaged_path", lambda: None)
    monkeypatch.setattr(application_entry, "run_docling_tools_command", lambda arguments: 17)
    monkeypatch.setattr(
        application_entry.sys,
        "argv",
        ["source-doc-converter", "--internal-docling-tools", "models", "download", "--help"],
    )

    assert application_entry.main() == 17


def test_package_smoke_test_requires_internal_macos_dispatch(monkeypatch, tmp_path: Path) -> None:
    class FakeWindow:
        def close(self) -> None:
            return None

    executable = tmp_path / "SourceDocumentConverter"
    monkeypatch.setattr(application_entry, "ApplicationWindow", FakeWindow)
    monkeypatch.setattr(application_entry, "is_packaged_application", lambda: True)
    monkeypatch.setattr(application_entry.sys, "platform", "darwin", raising=False)
    monkeypatch.setattr(application_entry.sys, "executable", str(executable))
    monkeypatch.setattr(
        application_entry,
        "resolve_model_downloader",
        lambda: [str(executable.resolve()), "--internal-docling-tools"],
    )
    pypdf_module = ModuleType("pypdf")
    pypdf_module.PdfReader = type("FakePdfReader", (), {})
    monkeypatch.setitem(sys.modules, "pypdf", pypdf_module)

    assert application_entry.run_package_smoke_test() == 0
