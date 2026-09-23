from pathlib import Path

from PySide6.QtCore import QPoint, QRect, Qt
from PySide6.QtWidgets import QScrollArea

from source_doc_converter.main_window import MainWindow


def make_pdf(path: Path) -> Path:
    path.write_bytes(b"%PDF-1.4\n")
    return path


def test_window_launches(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.windowTitle() == "Source Document Converter"
    assert window.queue.count() == 0
    assert window.searchable_pdf_checkbox.isChecked()
    assert window.markdown_checkbox.isEnabled()
    assert window.json_checkbox.isEnabled()
    assert not window.process_button.isEnabled()
    assert not window.cancel_button.isEnabled()


def test_adds_only_unique_pdf_files(qtbot, tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "filing.pdf")
    text = tmp_path / "notes.txt"
    text.write_text("not a PDF", encoding="utf-8")

    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([str(pdf), str(pdf), str(text)])

    assert window.pdf_paths == (pdf.resolve(),)
    assert window.queue.count() == 1
    assert window.output_directory is None
    assert not window.process_button.isEnabled()
    assert "choose an output folder" in window.next_step_label.text().lower()


def test_adds_pdfs_from_folder(qtbot, tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    first = make_pdf(tmp_path / "first.pdf")
    second = make_pdf(nested / "second.PDF")

    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([str(tmp_path)])

    assert set(window.pdf_paths) == {first.resolve(), second.resolve()}
    assert window.queue.count() == 2


def test_process_requires_any_output_selection(qtbot, tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "filing.pdf")
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([str(pdf)])
    window.set_output_directory(tmp_path / "out")

    window.searchable_pdf_checkbox.setChecked(False)
    assert not window.process_button.isEnabled()

    window.markdown_checkbox.setChecked(True)
    assert window.process_button.isEnabled()


def test_clear_disables_processing(qtbot, tmp_path: Path) -> None:
    pdf = make_pdf(tmp_path / "filing.pdf")
    window = MainWindow()
    qtbot.addWidget(window)
    window.add_paths([str(pdf)])

    window.clear_queue()

    assert window.pdf_paths == ()
    assert not window.process_button.isEnabled()


def test_queue_remains_scrollable_while_processing(qtbot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(760, 360)
    window.show()
    paths = []
    for index in range(60):
        paths.append(str(make_pdf(tmp_path / f"doc-{index:03d}.pdf")))
    window.add_paths(paths)
    qtbot.wait(10)
    scrollbar = window.queue.verticalScrollBar()
    assert scrollbar.maximum() > 0

    window._processing = True
    window._set_inputs_enabled(False)

    assert window.queue.isEnabled()
    assert window.queue.viewport().isEnabled()
    assert scrollbar.isEnabled()
    scrollbar.setValue(scrollbar.maximum())
    assert scrollbar.value() == scrollbar.maximum()
    window.queue.setCurrentRow(0)
    qtbot.keyClick(window.queue, Qt.Key.Key_End)
    assert window.queue.currentRow() == window.queue.count() - 1


def test_file_started_selects_item_without_continuous_scroll_hijack(qtbot, tmp_path: Path) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(760, 360)
    window.show()
    paths = []
    for index in range(60):
        paths.append(str(make_pdf(tmp_path / f"queue-{index:03d}.pdf")))
    window.add_paths(paths)
    qtbot.wait(10)

    scrollbar = window.queue.verticalScrollBar()
    scrollbar.setValue(0)
    window._on_file_started(45, 60, "queue-044.pdf")
    assert window.queue.currentRow() == 44
    assert scrollbar.value() > 0

    scrollbar.setValue(0)
    window._set_activity("Manual review")
    assert scrollbar.value() == 0


def test_initial_window_geometry_is_clamped_to_available_screen(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(50, 50, 700, 520),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)

    assert QRect(50, 50, 700, 520).contains(window.geometry())
    assert window.width() <= 700
    assert window.height() <= 520


def test_bottom_controls_remain_reachable_when_height_is_constrained(monkeypatch, qtbot) -> None:
    monkeypatch.setattr(
        "source_doc_converter.ui_geometry.available_geometry_for_widget",
        lambda _: QRect(0, 0, 1024, 520),
    )
    window = MainWindow()
    qtbot.addWidget(window)
    window.show()
    qtbot.wait(10)

    assert isinstance(window.centralWidget(), QScrollArea)
    scroll_area = window.centralWidget()
    scrollbar = scroll_area.verticalScrollBar()
    assert scrollbar.maximum() >= 0
    scrollbar.setValue(scrollbar.maximum())
    button_top = window.process_button.mapTo(scroll_area.viewport(), QPoint(0, 0)).y()
    assert button_top + window.process_button.height() <= scroll_area.viewport().height()


def test_add_buttons_remain_inside_drop_area(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)

    assert window.add_files_button.parentWidget() is window.drop_area
    assert window.add_folder_button.parentWidget() is window.drop_area


def test_queue_is_bounded_when_window_is_tall(qtbot) -> None:
    window = MainWindow()
    qtbot.addWidget(window)
    window.resize(1200, 1000)
    window.show()
    qtbot.wait(10)

    assert window.queue.maximumHeight() <= 240
    assert window.queue.height() <= 240
