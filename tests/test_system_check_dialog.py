from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt, QUrl
from PySide6.QtWidgets import QMessageBox

from source_doc_converter.system_check_dialog import (
    GHOSTSCRIPT_RELEASES_URL,
    SystemCheckDialog,
)
from source_doc_converter.system_diagnostics import ComponentStatus, SystemDiagnostics


def sample_diagnostics() -> SystemDiagnostics:
    return SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="TestOS",
        operating_system_version="1",
        architecture="test-arch",
        python_version="3.12.0",
        pyside_version="6.9.0",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True, "17.0.0"),
            ComponentStatus(
                "tesseract",
                "Tesseract OCR",
                True,
                "5.5.0",
                ("Languages: eng, spa",),
            ),
            ComponentStatus("docling", "Docling", False, error="Package not installed"),
        ),
        package_flavor="Lite",
        source_commit_sha="abc1234",
    )


def _assert_visible_in_scroll_viewport(dialog: SystemCheckDialog, control) -> None:
    viewport = dialog.content_scroll.viewport()
    position = control.mapTo(viewport, QPoint(0, 0))
    assert position.x() >= 0
    assert position.y() >= 0
    assert position.x() + control.width() <= viewport.width()
    assert position.y() + control.height() <= viewport.height()


def test_dialog_displays_component_status(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)

    assert dialog.component_table.rowCount() == 3
    assert dialog.component_table.item(0, 0).text() == "OCRmyPDF"
    assert dialog.component_table.item(0, 1).text() == "Available"
    assert dialog.component_table.item(2, 1).text() == "Unavailable"
    assert "Docling" in dialog.guidance_label.toPlainText()
    assert "Package Lite" in dialog.system_label.text()
    assert "Commit abc1234" in dialog.system_label.text()


def test_refresh_emits_updated_diagnostics(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    reports = []
    dialog.diagnostics_updated.connect(reports.append)

    dialog.refresh()

    assert reports == [sample_diagnostics()]


def test_dialog_shows_persistent_status_line(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog.show()

    assert dialog.activity_status_label.text().startswith("Status:")
    assert dialog.details_button.isEnabled()
    assert dialog.activity_status_label.geometry().left() < dialog.details_button.geometry().left()


def test_save_report_writes_privacy_safe_text(qtbot, tmp_path: Path) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    destination = tmp_path / "diagnostics.txt"

    dialog.save_report(destination)

    content = destination.read_text(encoding="utf-8")
    assert "Source Document Converter - System Check" in content
    assert "Docling: Unavailable" in content
    assert "secret.pdf" not in content
    assert "/home/" not in content
    assert "C:\\Users\\" not in content


def test_status_row_details_button_opens_shared_dialog_during_active_setup(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog._append_setup_detail("setup output line")
    dialog._set_setup_controls_active(True, model_download=False)

    assert dialog.details_button.isEnabled()
    qtbot.mouseClick(dialog.details_button, Qt.MouseButton.LeftButton)

    assert dialog._details_dialog.isVisible()
    assert "setup output line" in dialog._details_dialog.details_edit.toPlainText()


def test_dialog_guided_setup_text_mentions_windows_full_ghostscript_requirement(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)

    labels = [label.text() for label in dialog.findChildren(type(dialog.activity_status_label))]

    assert any("Windows Full bundles OCRmyPDF and Tesseract" in text for text in labels)
    assert any("Ghostscript remains optional/recommended" in text for text in labels)


def _windows_diagnostics_with_missing_ghostscript() -> SystemDiagnostics:
    return SystemDiagnostics(
        application_version="0.1.0a0",
        operating_system="Windows",
        operating_system_version="11",
        architecture="x86_64",
        python_version="3.12.0",
        pyside_version="6.9.0",
        components=(
            ComponentStatus("ocrmypdf", "OCRmyPDF", True, "17.0.0"),
            ComponentStatus("tesseract", "Tesseract OCR", True, "5.5.0"),
            ComponentStatus(
                "ghostscript",
                "Ghostscript",
                False,
                details=("Optional — not installed. Standard searchable PDF output works without Ghostscript.",),
            ),
            ComponentStatus("docling", "Docling", True, "2.50.0"),
        ),
    )


def test_missing_ghostscript_shows_optional_state_and_windows_action(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=_windows_diagnostics_with_missing_ghostscript)
    qtbot.addWidget(dialog)

    status_row = next(
        row
        for row in range(dialog.component_table.rowCount())
        if dialog.component_table.item(row, 0).text() == "Ghostscript"
    )
    assert dialog.component_table.item(status_row, 1).text() == "Optional — not installed"
    assert not dialog.ghostscript_button.isHidden()
    assert dialog.ghostscript_button.isEnabled()


def test_windows_ghostscript_link_cancel_does_not_open_browser(monkeypatch, qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=_windows_diagnostics_with_missing_ghostscript)
    qtbot.addWidget(dialog)
    opened: list[QUrl] = []
    monkeypatch.setattr(
        "source_doc_converter.system_check_dialog.QDesktopServices.openUrl",
        lambda url: opened.append(url) or True,
    )
    monkeypatch.setattr(
        "source_doc_converter.system_check_dialog.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.No,
    )

    dialog.open_ghostscript_download_page()

    assert opened == []


def test_windows_ghostscript_link_opens_official_page_after_confirmation(monkeypatch, qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=_windows_diagnostics_with_missing_ghostscript)
    qtbot.addWidget(dialog)
    opened: list[QUrl] = []
    monkeypatch.setattr(
        "source_doc_converter.system_check_dialog.QDesktopServices.openUrl",
        lambda url: opened.append(url) or True,
    )
    monkeypatch.setattr(
        "source_doc_converter.system_check_dialog.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )

    dialog.open_ghostscript_download_page()

    assert len(opened) == 1
    assert opened[0].toString() == GHOSTSCRIPT_RELEASES_URL


def test_system_check_and_setup_details_are_clamped_to_available_screen(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(100, 120, 700, 520),
    )
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)
    details = dialog._details_dialog
    details.show()
    qtbot.wait(10)

    available = QRect(100, 120, 700, 520)
    assert available.contains(dialog.geometry())
    assert available.contains(details.geometry())


def test_system_check_long_unbroken_path_does_not_force_width_past_cap(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 640, 480),
    )
    long_token = "C:\\" + ("verylongsegment" * 30)

    def diagnostics() -> SystemDiagnostics:
        return SystemDiagnostics(
            application_version="0.1.0a0",
            operating_system="Windows",
            operating_system_version="11",
            architecture="x86_64",
            python_version="3.12.0",
            pyside_version="6.9.0",
            components=(
                ComponentStatus("ocrmypdf", "OCRmyPDF", False, error=long_token),
                ComponentStatus("tesseract", "Tesseract OCR", True, "5.5.0"),
                ComponentStatus("ghostscript", "Ghostscript", True, "10.0.0"),
                ComponentStatus("docling", "Docling", True, "2.50.0"),
            ),
        )

    dialog = SystemCheckDialog(diagnostics_provider=diagnostics)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    assert dialog.width() <= 640
    assert dialog.content_scroll.horizontalScrollBar().maximum() == 0


def test_system_check_summary_actions_fit_large_viewport_without_outer_scroll(
    monkeypatch, qtbot
) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1800, 1200),
    )
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog.resize(1400, 900)
    dialog.show()
    qtbot.wait(20)

    assert dialog.content_scroll.horizontalScrollBar().maximum() == 0
    assert dialog.content_scroll.verticalScrollBar().maximum() == 0
    for control in (
        dialog.activity_status_label,
        dialog.details_button,
        dialog.component_table,
        dialog.setup_dependencies_button,
        dialog.choose_model_button,
    ):
        _assert_visible_in_scroll_viewport(dialog, control)


def test_system_check_large_font_keeps_primary_actions_reachable(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1800, 1200),
    )
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog.setStyleSheet("QWidget { font-size: 14pt; }")
    dialog.resize(1400, 900)
    dialog.show()
    qtbot.wait(20)

    assert dialog.content_scroll.horizontalScrollBar().maximum() == 0
    dialog.content_scroll.verticalScrollBar().setValue(
        dialog.content_scroll.verticalScrollBar().maximum()
    )
    close_position = dialog.close_button.mapTo(dialog, QPoint(0, 0))
    assert close_position.x() >= 0
    assert close_position.y() >= 0
    assert close_position.x() + dialog.close_button.width() <= dialog.width()
    assert close_position.y() + dialog.close_button.height() <= dialog.height()


def test_system_check_resize_large_small_large_clears_stale_overflow(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1800, 1200),
    )
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)
    dialog.resize(1400, 900)
    dialog.show()
    qtbot.wait(20)
    assert dialog.content_scroll.horizontalScrollBar().maximum() == 0
    assert dialog.content_scroll.verticalScrollBar().maximum() == 0

    dialog.resize(1024, 640)
    qtbot.wait(20)
    assert dialog.content_scroll.verticalScrollBar().maximum() >= 0

    dialog.resize(1400, 900)
    qtbot.wait(20)
    assert dialog.content_scroll.horizontalScrollBar().maximum() == 0
    assert dialog.content_scroll.verticalScrollBar().maximum() == 0
