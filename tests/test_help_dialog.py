from PySide6.QtCore import QRect, Qt

from source_doc_converter.help_content import SETTINGS_GUIDE
from source_doc_converter.help_dialog import HelpDialog


def test_help_dialog_initial_geometry_fits_normal_available_area(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(100, 80, 1600, 900),
    )
    dialog = HelpDialog(SETTINGS_GUIDE)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    available = QRect(100, 80, 1600, 900)
    assert available.contains(dialog.geometry())
    assert dialog.width() <= 1600
    assert dialog.height() <= 900


def test_help_dialog_clamps_and_keeps_scroll_usable_on_1024x768_area(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1024, 768),
    )
    dialog = HelpDialog(SETTINGS_GUIDE)
    qtbot.addWidget(dialog)
    dialog.show()
    qtbot.wait(10)

    available = QRect(0, 0, 1024, 768)
    assert available.contains(dialog.geometry())
    assert dialog.content.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    scrollbar = dialog.content.verticalScrollBar()
    assert scrollbar.maximum() >= 0
    scrollbar.setValue(scrollbar.maximum())
    assert scrollbar.value() == scrollbar.maximum()
