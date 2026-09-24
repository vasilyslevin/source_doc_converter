import platform
from pathlib import Path

from PySide6 import __version__ as PYSIDE_VERSION
from PySide6.QtCore import QPoint, QRect, QSettings, QUrl, qVersion
from PySide6.QtGui import QGuiApplication

from source_doc_converter import application_window
from source_doc_converter import main_window as base_main_window
from source_doc_converter.application_window import (
    AI_ANALYSIS_MODE_SETTING,
    AI_TABLE_ANALYSIS_SETTING,
    COMBINED_MARKDOWN_BUNDLE_SETTING,
    OCR_MODE_SETTING,
    PROCESSING_PROFILE_SETTING,
    ApplicationWindow,
)
from source_doc_converter.model_management import ModelDirectoryState
from source_doc_converter.ocr_runtime import (
    TESSERACT_LANGUAGES_SETTING,
    TESSERACT_PROFILE_MODE_SETTING,
    TESSERACT_PROFILE_PATH_SETTING,
    TesseractInstallation,
)
from source_doc_converter.system_diagnostics import (
    ComponentStatus,
    OutputAvailability,
    SystemDiagnostics,
)


def ready_models() -> ModelDirectoryState:
    return ModelDirectoryState(Path("models"), "settings", True)


def missing_models() -> ModelDirectoryState:
    return ModelDirectoryState(Path("models"), "settings", False)


def sample_installation(tmp_path: Path, *, source: str = "bundled") -> TesseractInstallation:
    executable = tmp_path / source / ("tesseract.exe" if source == "bundled" else "tesseract")
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()
    tessdata = executable.parent / "tessdata" / "configs"
    tessdata.mkdir(parents=True)
    (tessdata / "hocr").write_text("", encoding="utf-8")
    return TesseractInstallation(
        label="Bundled Tesseract (recommended)" if source == "bundled" else "System PATH",
        source=source,
        executable=executable,
        tessdata=executable.parent / "tessdata",
        languages=("eng", "spa"),
    )


def assert_reachable_with_optional_horizontal_scroll(window: ApplicationWindow, control) -> None:
    viewport = window.content_scroll.viewport()
    position = control.mapTo(viewport, QPoint(0, 0))
    if position.x() + control.width() <= viewport.width():
        return
    horizontal = window.content_scroll.horizontalScrollBar()
    assert horizontal.maximum() > 0
    horizontal.setValue(horizontal.maximum())
    position = control.mapTo(viewport, QPoint(0, 0))
    assert position.x() + control.width() <= viewport.width()


def test_unavailable_components_disable_outputs(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(False, False)
    )
    qtbot.addWidget(window)

    assert not window.searchable_pdf_checkbox.isEnabled()
    assert not window.searchable_pdf_checkbox.isChecked()
    assert not window.markdown_checkbox.isEnabled()
    assert not window.json_checkbox.isEnabled()


def test_available_components_enable_outputs(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    assert window.searchable_pdf_checkbox.isEnabled()
    assert window.searchable_pdf_checkbox.isChecked()
    assert window.markdown_checkbox.isEnabled()
    assert window.json_checkbox.isEnabled()
    assert not window.combined_markdown_bundle_checkbox.isEnabled()


def test_diagnostics_update_output_availability(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(False, False),
        model_state_provider=ready_models,
    )
    qtbot.addWidget(window)
    diagnostics = SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="TestOS",
        operating_system_version="1",
        architecture="test",
        python_version="3.12",
        pyside_version="6.9",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True),
            ComponentStatus("tesseract", "Tesseract OCR", True),
            ComponentStatus("ghostscript", "Ghostscript", True),
            ComponentStatus("docling", "Docling", True),
        ),
    )

    window.apply_diagnostics(diagnostics)

    assert window.searchable_pdf_checkbox.isEnabled()
    assert window.markdown_checkbox.isEnabled()
    assert window.json_checkbox.isEnabled()


def test_missing_models_disable_only_docling_outputs(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        model_state_provider=missing_models,
    )
    qtbot.addWidget(window)
    diagnostics = SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="TestOS",
        operating_system_version="1",
        architecture="test",
        python_version="3.12",
        pyside_version="6.9",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True),
            ComponentStatus("tesseract", "Tesseract OCR", True),
            ComponentStatus("ghostscript", "Ghostscript", True),
            ComponentStatus("docling", "Docling", True),
        ),
    )

    window.apply_diagnostics(diagnostics)

    assert window.searchable_pdf_checkbox.isEnabled()
    assert not window.markdown_checkbox.isEnabled()
    assert not window.json_checkbox.isEnabled()
    assert "models are not ready" in window.markdown_checkbox.toolTip()


def test_missing_ghostscript_keeps_searchable_pdf_enabled(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        model_state_provider=ready_models,
    )
    qtbot.addWidget(window)
    diagnostics = SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="TestOS",
        operating_system_version="1",
        architecture="test",
        python_version="3.12",
        pyside_version="6.9",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True),
            ComponentStatus("tesseract", "Tesseract OCR", True),
            ComponentStatus("ghostscript", "Ghostscript", False),
            ComponentStatus("docling", "Docling", True),
        ),
    )

    window.apply_diagnostics(diagnostics)

    assert window.searchable_pdf_checkbox.isEnabled()


def test_missing_pypdf_disables_fast_markdown_option(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        application_window,
        "check_pypdf",
        lambda: ComponentStatus("pypdf", "pypdf", False, error="Package not installed"),
    )
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
    )
    qtbot.addWidget(window)

    fast_index = window.ai_analysis_mode_combo.findData("fast")
    fast_item = window.ai_analysis_mode_combo.model().item(fast_index)
    assert fast_item is not None
    assert not fast_item.isEnabled()


def test_open_output_folder_uses_desktop_services(monkeypatch, qtbot, tmp_path: Path) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)
    window.set_output_directory(tmp_path)
    opened_urls: list[QUrl] = []
    monkeypatch.setattr(
        application_window.QDesktopServices,
        "openUrl",
        lambda url: opened_urls.append(url) or True,
    )

    window.open_output_directory()

    assert window.open_output_button.isEnabled()
    assert len(opened_urls) == 1
    assert Path(opened_urls[0].toLocalFile()).resolve() == tmp_path.resolve()


def test_open_output_button_waits_for_existing_folder(qtbot, tmp_path: Path) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    window.set_output_directory(tmp_path / "not-created")

    assert not window.open_output_button.isEnabled()


def test_tesseract_selection_persists_and_resets(monkeypatch, qtbot, tmp_path: Path) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)

    window.tesseract_profile_combo.setCurrentIndex(1)
    assert str(settings.value(TESSERACT_PROFILE_MODE_SETTING, "")) == "system"
    assert str(settings.value(TESSERACT_PROFILE_PATH_SETTING, "")) == str(installation.executable)

    window._reset_tesseract_profile()
    assert str(settings.value(TESSERACT_PROFILE_MODE_SETTING, "")) == "automatic"
    assert str(settings.value(TESSERACT_PROFILE_PATH_SETTING, "")) == ""


def test_missing_selected_language_blocks_processing(monkeypatch, qtbot, tmp_path: Path) -> None:
    installation = sample_installation(tmp_path, source="path")
    constrained = TesseractInstallation(
        label=installation.label,
        source=installation.source,
        executable=installation.executable,
        tessdata=installation.tessdata,
        languages=("eng",),
    )
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (constrained,),
    )
    settings = QSettings(str(tmp_path / "settings2.ini"), QSettings.Format.IniFormat)
    settings.setValue(TESSERACT_LANGUAGES_SETTING, "eng+spa")
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    settings.setValue(TESSERACT_LANGUAGES_SETTING, "eng+spa")
    warnings = []
    monkeypatch.setattr(application_window.QMessageBox, "critical", lambda *args, **kwargs: warnings.append(args[2]))
    monkeypatch.setattr(base_main_window, "find_ocrmypdf", lambda: "/tools/ocrmypdf")
    window.queue.addItem(str(tmp_path / "filing.pdf"))
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")

    window.start_processing()

    assert warnings
    assert "does not provide" in warnings[0]


def test_selected_languages_are_passed_to_worker(monkeypatch, qtbot, tmp_path: Path) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    settings = QSettings(str(tmp_path / "settings3.ini"), QSettings.Format.IniFormat)
    settings.setValue(TESSERACT_LANGUAGES_SETTING, "eng+spa")
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")

    worker = window._create_processing_worker(
        create_searchable_pdf=True,
        create_markdown=False,
        create_json=False,
        executable="/tools/ocrmypdf",
    )

    assert worker._language == "eng+spa"


def test_ocr_mode_selection_is_persisted_and_passed_to_worker(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    settings = QSettings(str(tmp_path / "settings4.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")

    window.ocr_mode_combo.setCurrentIndex(2)

    assert str(settings.value(OCR_MODE_SETTING, "")) == "redo"
    worker = window._create_processing_worker(
        create_searchable_pdf=True,
        create_markdown=False,
        create_json=False,
        executable="/tools/ocrmypdf",
    )
    assert worker._ocr_mode == "redo"


def test_ai_mode_and_profile_are_persisted_and_passed_to_worker(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    monkeypatch.setattr(application_window, "_cpu_thread_count", lambda: 8)
    settings = QSettings(str(tmp_path / "settings5.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")
    window.ai_analysis_mode_combo.setCurrentIndex(1)
    window.processing_profile_combo.setCurrentIndex(2)
    window.cpu_only_checkbox.setChecked(True)
    window.markdown_checkbox.setChecked(True)
    window.combined_markdown_bundle_checkbox.setChecked(True)

    assert str(settings.value(AI_ANALYSIS_MODE_SETTING, "")) == "fast"
    assert str(settings.value(PROCESSING_PROFILE_SETTING, "")) == "energy_saver"
    assert settings.value(COMBINED_MARKDOWN_BUNDLE_SETTING, False, type=bool) is True
    worker = window._create_processing_worker(
        create_searchable_pdf=True,
        create_markdown=True,
        create_json=False,
        executable="/tools/ocrmypdf",
    )
    assert worker._analysis_mode == "fast"
    assert worker._ocr_workers == 2
    assert worker._parser_threads == 2
    assert worker._inference_threads == 1
    assert worker._create_markdown_bundle is True


def test_combined_markdown_bundle_requires_markdown_output(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    assert not window.combined_markdown_bundle_checkbox.isEnabled()
    assert "Markdown for AI" in window.combined_markdown_bundle_checkbox.toolTip()

    window.markdown_checkbox.setChecked(True)
    assert window.combined_markdown_bundle_checkbox.isEnabled()
    assert "this job only" in window.combined_markdown_bundle_checkbox.toolTip()

    window.markdown_checkbox.setChecked(False)
    window.json_checkbox.setChecked(True)
    assert not window.combined_markdown_bundle_checkbox.isEnabled()


def test_combined_markdown_bundle_default_off_and_persisted(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "bundle.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)

    assert window.combined_markdown_bundle_checkbox.isChecked() is False
    window.markdown_checkbox.setChecked(True)
    window.combined_markdown_bundle_checkbox.setChecked(True)
    assert settings.value(COMBINED_MARKDOWN_BUNDLE_SETTING, False, type=bool) is True

    reloaded = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(reloaded)
    reloaded.markdown_checkbox.setChecked(True)
    assert reloaded.combined_markdown_bundle_checkbox.isChecked() is True


def test_auto_analysis_with_table_request_uses_table_mode_without_overwriting_selection(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    settings = QSettings(str(tmp_path / "settings6.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")
    window.ai_analysis_mode_combo.setCurrentIndex(0)
    window.table_structure_checkbox.setChecked(True)

    worker = window._create_processing_worker(
        create_searchable_pdf=False,
        create_markdown=True,
        create_json=False,
        executable=None,
    )

    assert window.ai_analysis_mode_combo.currentData() == "auto"
    assert worker._analysis_mode == "accurate_tables"


def test_legacy_accurate_tables_migrates_to_single_table_setting(monkeypatch, qtbot, tmp_path: Path) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    settings = QSettings(str(tmp_path / "settings7.ini"), QSettings.Format.IniFormat)
    settings.setValue(AI_ANALYSIS_MODE_SETTING, "accurate_tables")
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)

    assert window.ai_analysis_mode_combo.currentData() == "accurate"
    assert window.table_structure_checkbox.isChecked()
    assert str(settings.value(AI_ANALYSIS_MODE_SETTING, "")) == "accurate"
    assert settings.value(AI_TABLE_ANALYSIS_SETTING, False, type=bool) is True


def test_help_menu_has_required_entries(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    assert window.getting_started_action.text() == "Getting Started"
    assert window.settings_guide_action.text() == "Settings Guide"
    assert window.system_check_action.text() == "System Check"
    assert window.about_action.text() == "About"


def test_open_output_button_is_grouped_with_processing_controls(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    assert window.open_output_button.parentWidget() is window.actions_group


def test_advanced_groups_follow_output_selection(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)

    window.searchable_pdf_checkbox.setChecked(False)
    window.markdown_checkbox.setChecked(False)
    window.json_checkbox.setChecked(False)
    window.update_process_button()
    assert not window.searchable_pdf_group.isEnabled()
    assert not window.markdown_json_group.isEnabled()

    window.searchable_pdf_checkbox.setChecked(True)
    window.markdown_checkbox.setChecked(True)
    window.update_process_button()
    assert window.searchable_pdf_group.isEnabled()
    assert window.markdown_json_group.isEnabled()


def test_table_preference_is_preserved_when_fast_mode_is_selected(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(
        application_window,
        "check_pypdf",
        lambda: ComponentStatus("pypdf", "pypdf", True),
    )
    settings = QSettings(str(tmp_path / "settings8.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window.markdown_checkbox.setChecked(True)
    window.table_structure_checkbox.setChecked(True)
    window.ai_analysis_mode_combo.setCurrentIndex(window.ai_analysis_mode_combo.findData("fast"))

    assert not window.table_structure_checkbox.isEnabled()
    assert window.table_structure_checkbox.isChecked()
    assert settings.value(AI_TABLE_ANALYSIS_SETTING, False, type=bool) is True

    window.ai_analysis_mode_combo.setCurrentIndex(window.ai_analysis_mode_combo.findData("auto"))
    assert window.table_structure_checkbox.isEnabled()
    assert window.table_structure_checkbox.isChecked()


def test_table_preference_is_preserved_when_docling_temporarily_unavailable(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings9.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window.markdown_checkbox.setChecked(True)
    window.table_structure_checkbox.setChecked(True)

    window.apply_output_availability(
        OutputAvailability(True, False, "Docling unavailable")
    )
    assert not window.table_structure_checkbox.isEnabled()
    assert window.table_structure_checkbox.isChecked()
    assert settings.value(AI_TABLE_ANALYSIS_SETTING, False, type=bool) is True

    window.apply_output_availability(OutputAvailability(True, True))
    assert window.table_structure_checkbox.isChecked()
    window.markdown_checkbox.setChecked(True)
    assert window.table_structure_checkbox.isEnabled()
    assert window.table_structure_checkbox.isChecked()


def test_fast_mode_ignores_table_analysis_even_if_preference_remains_checked(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    installation = sample_installation(tmp_path, source="path")
    monkeypatch.setattr(
        application_window,
        "discover_tesseract_installations",
        lambda: (installation,),
    )
    monkeypatch.setattr(
        application_window,
        "check_pypdf",
        lambda: ComponentStatus("pypdf", "pypdf", True),
    )
    settings = QSettings(str(tmp_path / "settings10.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window._pdf_paths.append(tmp_path / "filing.pdf")
    window.set_output_directory(tmp_path / "out")
    window.table_structure_checkbox.setChecked(True)
    window.ai_analysis_mode_combo.setCurrentIndex(window.ai_analysis_mode_combo.findData("fast"))

    worker = window._create_processing_worker(
        create_searchable_pdf=False,
        create_markdown=True,
        create_json=False,
        executable=None,
    )

    assert window.table_structure_checkbox.isChecked()
    assert worker._analysis_mode == "fast"


def test_advanced_controls_remain_reachable_on_constrained_width(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)
    window.advanced_toggle_button.setChecked(True)
    window.resize(620, 760)
    window.show()
    qtbot.wait(10)

    controls = (
        window.searchable_pdf_checkbox,
        window.markdown_checkbox,
        window.json_checkbox,
        window.tesseract_profile_combo,
        window.browse_tesseract_button,
        window.reset_tesseract_button,
        window.docling_ocr_checkbox,
        window.table_structure_checkbox,
        window.cpu_only_checkbox,
        window.process_button,
        window.cancel_button,
        window.open_output_button,
    )
    for control in controls:
        assert_reachable_with_optional_horizontal_scroll(window, control)


def test_advanced_controls_reflow_for_large_font_size_hints(qtbot) -> None:
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True)
    )
    qtbot.addWidget(window)
    window.advanced_toggle_button.setChecked(True)
    window.resize(620, 820)
    window.setStyleSheet("QWidget { font-size: 18pt; }")
    window.show()
    qtbot.wait(10)

    controls = (
        window.tesseract_profile_combo,
        window.browse_tesseract_button,
        window.reset_tesseract_button,
        window.docling_ocr_checkbox,
        window.table_structure_checkbox,
        window.cpu_only_checkbox,
    )
    for control in controls:
        assert_reachable_with_optional_horizontal_scroll(window, control)


def test_advanced_layout_fits_large_viewport_without_outer_scrollbars(
    monkeypatch,
    qtbot,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1800, 1200),
    )
    settings = QSettings(str(tmp_path / "layout-default.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window.advanced_toggle_button.setChecked(True)
    window.resize(1560, 980)
    window.show()
    qtbot.wait(20)

    diagnostics = {
        "window": (window.width(), window.height()),
        "viewport": (
            window.content_scroll.viewport().width(),
            window.content_scroll.viewport().height(),
        ),
        "scroll": (
            window.content_scroll.horizontalScrollBar().maximum(),
            window.content_scroll.verticalScrollBar().maximum(),
        ),
        "content_size_hint": (
            window.content_scroll.widget().sizeHint().width(),
            window.content_scroll.widget().sizeHint().height(),
        ),
        "drop": (window.drop_area.height(), window.drop_area.sizeHint().height()),
        "queue_group": (window.queue_group.height(), window.queue_group.sizeHint().height()),
        "queue": (window.queue.height(), window.queue.maximumHeight()),
        "output_group": (window.output_group.height(), window.output_group.sizeHint().height()),
        "actions_group": (window.actions_group.height(), window.actions_group.sizeHint().height()),
        "output_width": window.output_group.contentsRect().width(),
        "available_output_width": (
            window.content_scroll.viewport().width()
            - window._wide_left_column.minimumSizeHint().width()
            - window._content_layout.horizontalSpacing()
            - window._content_layout.contentsMargins().left()
            - window._content_layout.contentsMargins().right()
        ),
        "advanced_two_column": window._advanced_two_column,
        "python_version": platform.python_version(),
        "pyside_version": PYSIDE_VERSION,
        "qt_version": qVersion(),
        "qt_platform": QGuiApplication.platformName(),
        "dpi": None,
        "font_metrics": (
            window.fontMetrics().height(),
            window.fontMetrics().averageCharWidth(),
        ),
    }
    screen = window.screen() or QGuiApplication.primaryScreen()
    if screen is not None:
        diagnostics["dpi"] = screen.logicalDotsPerInch()
    assert window.content_scroll.horizontalScrollBar().maximum() == 0, diagnostics
    assert window.content_scroll.verticalScrollBar().maximum() == 0, diagnostics
    needed_for_two_columns = (
        window.searchable_pdf_group.minimumSizeHint().width()
        + max(
            window.markdown_json_group.minimumSizeHint().width(),
            window.performance_group.minimumSizeHint().width(),
        )
        + window._advanced_layout.horizontalSpacing()
    )
    assert window.output_group.contentsRect().width() >= needed_for_two_columns
    assert window.markdown_json_group.geometry().x() > window.searchable_pdf_group.geometry().x()


def test_advanced_layout_keeps_controls_reachable_with_larger_font(monkeypatch, qtbot, tmp_path: Path) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1800, 1200),
    )
    settings = QSettings(str(tmp_path / "layout-large-font.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window.setStyleSheet("QWidget { font-size: 14pt; }")
    window.advanced_toggle_button.setChecked(True)
    window.resize(1560, 980)
    window.show()
    qtbot.wait(20)

    diagnostics = {
        "window": (window.width(), window.height()),
        "viewport": (
            window.content_scroll.viewport().width(),
            window.content_scroll.viewport().height(),
        ),
        "scroll": (
            window.content_scroll.horizontalScrollBar().maximum(),
            window.content_scroll.verticalScrollBar().maximum(),
        ),
        "output_width": window.output_group.contentsRect().width(),
        "advanced_two_column": window._advanced_two_column,
    }
    assert window.content_scroll.horizontalScrollBar().maximum() == 0, diagnostics
    if window._advanced_two_column:
        needed_for_two_columns = (
            window.searchable_pdf_group.minimumSizeHint().width()
            + max(
                window.markdown_json_group.minimumSizeHint().width(),
                window.performance_group.minimumSizeHint().width(),
            )
            + window._advanced_layout.horizontalSpacing()
        )
        assert window.output_group.contentsRect().width() >= needed_for_two_columns
    window.content_scroll.verticalScrollBar().setValue(
        window.content_scroll.verticalScrollBar().maximum()
    )
    assert_reachable_with_optional_horizontal_scroll(window, window.process_button)


def test_advanced_layout_reflows_to_single_column_on_narrower_width(qtbot, tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "layout-narrow.ini"), QSettings.Format.IniFormat)
    window = ApplicationWindow(
        availability_provider=lambda: OutputAvailability(True, True),
        settings=settings,
    )
    qtbot.addWidget(window)
    window.advanced_toggle_button.setChecked(True)
    window.resize(760, 900)
    window.show()
    qtbot.wait(20)

    assert window.content_scroll.horizontalScrollBar().maximum() == 0
    assert not window._advanced_two_column
