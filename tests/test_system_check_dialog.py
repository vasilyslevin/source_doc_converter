from pathlib import Path

from PySide6.QtCore import Qt

from source_doc_converter.system_check_dialog import SystemCheckDialog
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


def test_dialog_displays_component_status(qtbot) -> None:
    dialog = SystemCheckDialog(diagnostics_provider=sample_diagnostics)
    qtbot.addWidget(dialog)

    assert dialog.component_table.rowCount() == 3
    assert dialog.component_table.item(0, 0).text() == "OCRmyPDF"
    assert dialog.component_table.item(0, 1).text() == "Available"
    assert dialog.component_table.item(2, 1).text() == "Unavailable"
    assert "Docling" in dialog.guidance_label.text()
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

    labels = [label.text() for label in dialog.findChildren(type(dialog.guidance_label))]

    assert any("Windows Full bundles OCRmyPDF and Tesseract" in text for text in labels)
    assert any("Ghostscript remains optional/recommended" in text for text in labels)
