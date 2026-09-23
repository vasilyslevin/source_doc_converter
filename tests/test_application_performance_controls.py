from pathlib import Path

from PySide6.QtCore import QSettings

from source_doc_converter import application_window
from source_doc_converter.application_window import ApplicationWindow
from source_doc_converter.model_management import ModelDirectoryState
from source_doc_converter.system_diagnostics import OutputAvailability


def make_settings(tmp_path: Path) -> QSettings:
    return QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)


def make_window(qtbot, settings: QSettings) -> ApplicationWindow:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        model_state_provider=lambda: ModelDirectoryState(Path("models"), "settings", True),
        settings=settings,
    )
    qtbot.addWidget(window)
    return window


def test_docling_performance_controls_defaults(qtbot, tmp_path: Path) -> None:
    window = make_window(qtbot, make_settings(tmp_path))

    assert not window.docling_ocr_checkbox.isChecked()
    assert not window.table_structure_checkbox.isChecked()
    assert window.cpu_only_checkbox.isChecked()
    assert window.ai_analysis_mode_combo.currentData() == "auto"
    assert window.processing_profile_combo.currentData() == "balanced"


def test_processing_choices_persist_between_windows(qtbot, tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    first = make_window(qtbot, settings)
    first.docling_ocr_checkbox.setChecked(True)
    first.table_structure_checkbox.setChecked(True)
    first.cpu_only_checkbox.setChecked(False)
    first.ai_analysis_mode_combo.setCurrentIndex(2)
    first.processing_profile_combo.setCurrentIndex(0)

    second = make_window(qtbot, settings)

    assert second.docling_ocr_checkbox.isChecked()
    assert second.table_structure_checkbox.isChecked()
    assert not second.cpu_only_checkbox.isChecked()
    assert second.ai_analysis_mode_combo.currentData() == "accurate"
    assert second.processing_profile_combo.currentData() == "max_speed"


def test_energy_saver_profile_uses_expected_thread_budget(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(application_window, "_cpu_thread_count", lambda: 12)
    window = make_window(qtbot, make_settings(tmp_path))
    window.processing_profile_combo.setCurrentIndex(2)

    ocr_workers, parser_threads, inference_threads = window._thread_profile_values()

    assert (ocr_workers, parser_threads, inference_threads) == (2, 2, 1)
