from pathlib import Path

from PySide6.QtCore import QSize, Qt, QThread, Signal
from PySide6.QtGui import QDragEnterEvent, QDropEvent, QShowEvent
from PySide6.QtWidgets import (
    QCheckBox,
    QFileDialog,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QMainWindow,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from source_doc_converter import ui_geometry
from source_doc_converter.ocr_pipeline import find_ocrmypdf
from source_doc_converter.ocr_worker import ProcessingWorker


class PdfDropArea(QLabel):
    paths_dropped = Signal(list)

    def __init__(self) -> None:
        super().__init__("Drop PDF files or folders here")
        self.setAcceptDrops(True)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumHeight(140)
        self.setStyleSheet(
            "QLabel { border: 2px dashed #777; border-radius: 8px; "
            "font-size: 18px; padding: 24px; }"
        )

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if self._contains_supported_path(event.mimeData().urls()):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event: QDropEvent) -> None:
        paths = [url.toLocalFile() for url in event.mimeData().urls() if url.isLocalFile()]
        if paths:
            self.paths_dropped.emit(paths)
            event.acceptProposedAction()

    @staticmethod
    def _contains_supported_path(urls: list) -> bool:
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_dir() or path.suffix.lower() == ".pdf":
                return True
        return False


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self._pdf_paths: list[Path] = []
        self._output_directory: Path | None = None
        self._processing = False
        self._completed_count = 0
        self._processing_errors: list[str] = []
        self._thread: QThread | None = None
        self._worker: ProcessingWorker | None = None

        self.setWindowTitle("Source Document Converter")

        self.drop_area = PdfDropArea()
        self.drop_area.paths_dropped.connect(self.add_paths)
        self.queue = QListWidget()
        self.queue.setAlternatingRowColors(True)
        self.queue.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.queue.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        self.queue.setMinimumHeight(220)

        self.add_files_button = QPushButton("Add PDFs")
        self.add_files_button.clicked.connect(self.choose_files)
        self.add_folder_button = QPushButton("Add Folder")
        self.add_folder_button.clicked.connect(self.choose_folder)
        self.remove_button = QPushButton("Remove Selected")
        self.remove_button.clicked.connect(self.remove_selected)
        self.clear_button = QPushButton("Clear")
        self.clear_button.clicked.connect(self.clear_queue)

        queue_controls = QHBoxLayout()
        queue_controls.addWidget(self.add_files_button)
        queue_controls.addWidget(self.add_folder_button)
        queue_controls.addStretch()
        queue_controls.addWidget(self.remove_button)
        queue_controls.addWidget(self.clear_button)

        self.output_group = QGroupBox("Output")
        output_layout = QVBoxLayout()
        output_folder_row = QHBoxLayout()
        self.output_path_edit = QLineEdit()
        self.output_path_edit.setReadOnly(True)
        self.output_path_edit.setPlaceholderText("Choose an output folder")
        self.choose_output_button = QPushButton("Choose Folder")
        self.choose_output_button.clicked.connect(self.choose_output_directory)
        output_folder_row.addWidget(self.output_path_edit)
        output_folder_row.addWidget(self.choose_output_button)

        output_types = QHBoxLayout()
        self.searchable_pdf_checkbox = QCheckBox("Searchable PDF")
        self.searchable_pdf_checkbox.setChecked(True)
        self.markdown_checkbox = QCheckBox("Markdown for AI")
        self.json_checkbox = QCheckBox("Structured JSON")
        output_types.addWidget(self.searchable_pdf_checkbox)
        output_types.addWidget(self.markdown_checkbox)
        output_types.addWidget(self.json_checkbox)
        output_types.addStretch()
        output_layout.addLayout(output_folder_row)
        output_layout.addLayout(output_types)
        self.output_group.setLayout(output_layout)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 1)
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Ready")
        self.activity_label = QLabel("Activity: Ready")

        self.process_button = QPushButton("Process Documents")
        self.process_button.setEnabled(False)
        self.process_button.clicked.connect(self.start_processing)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel_processing)

        self.searchable_pdf_checkbox.checkStateChanged.connect(self.update_process_button)
        self.markdown_checkbox.checkStateChanged.connect(self.update_process_button)
        self.json_checkbox.checkStateChanged.connect(self.update_process_button)

        action_row = QHBoxLayout()
        action_row.addWidget(self.progress_bar)
        action_row.addWidget(self.cancel_button)
        action_row.addWidget(self.process_button)

        layout = QVBoxLayout()
        layout.addWidget(self.drop_area)
        layout.addLayout(queue_controls)
        layout.addWidget(self.queue, 1)
        layout.addWidget(self.output_group)
        layout.addWidget(self.activity_label)
        layout.addLayout(action_row)

        content = QWidget()
        content.setLayout(layout)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setWidget(content)
        self.setCentralWidget(self.content_scroll)
        self.statusBar().showMessage("Add one or more PDF files")
        ui_geometry.apply_initial_geometry(self, QSize(760, 680))

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ui_geometry.clamp_widget_to_available_screen(self)

    @property
    def pdf_paths(self) -> tuple[Path, ...]:
        return tuple(self._pdf_paths)

    @property
    def output_directory(self) -> Path | None:
        return self._output_directory

    def choose_files(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Choose PDF files", "", "PDF documents (*.pdf)"
        )
        self.add_paths(paths)

    def choose_folder(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose a folder")
        if path:
            self.add_paths([path])

    def choose_output_directory(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Choose an output folder")
        if path:
            self.set_output_directory(Path(path))

    def set_output_directory(self, path: Path) -> None:
        self._output_directory = path.resolve()
        self.output_path_edit.setText(str(self._output_directory))
        self.update_process_button()

    def add_paths(self, paths: list[str]) -> None:
        candidates: list[Path] = []
        for raw_path in paths:
            path = Path(raw_path)
            if path.is_dir():
                candidates.extend(item for item in path.rglob("*") if item.is_file())
            else:
                candidates.append(path)

        known = {path.resolve() for path in self._pdf_paths}
        for candidate in sorted(candidates):
            if not candidate.is_file() or candidate.suffix.lower() != ".pdf":
                continue
            resolved = candidate.resolve()
            if resolved in known:
                continue
            self._pdf_paths.append(resolved)
            self.queue.addItem(str(resolved))
            known.add(resolved)

        if self._pdf_paths and self._output_directory is None:
            self.set_output_directory(self._pdf_paths[0].parent / "Converted")
        self._update_status()
        self.update_process_button()

    def remove_selected(self) -> None:
        rows = sorted({index.row() for index in self.queue.selectedIndexes()}, reverse=True)
        for row in rows:
            self.queue.takeItem(row)
            self._pdf_paths.pop(row)
        self._update_status()
        self.update_process_button()

    def clear_queue(self) -> None:
        self.queue.clear()
        self._pdf_paths.clear()
        self._update_status()
        self.update_process_button()

    def update_process_button(self) -> None:
        ready = bool(
            self._pdf_paths
            and self._output_directory
            and (
                self.searchable_pdf_checkbox.isChecked()
                or self.markdown_checkbox.isChecked()
                or self.json_checkbox.isChecked()
            )
            and not self._processing
        )
        self.process_button.setEnabled(ready)

    def start_processing(self) -> None:
        if self._processing or self._output_directory is None:
            return

        create_searchable_pdf = self.searchable_pdf_checkbox.isChecked()
        create_markdown = self.markdown_checkbox.isChecked()
        create_json = self.json_checkbox.isChecked()
        if not (create_searchable_pdf or create_markdown or create_json):
            return

        executable: str | None = None
        if create_searchable_pdf:
            executable = find_ocrmypdf()
            if executable is None:
                QMessageBox.critical(
                    self,
                    "OCRmyPDF not found",
                    "OCRmyPDF is not installed or is not available on the application PATH.",
                )
                return

        self._processing = True
        self._completed_count = 0
        self._processing_errors.clear()
        self._set_inputs_enabled(False)
        self.cancel_button.setEnabled(True)
        self.progress_bar.setRange(0, len(self._pdf_paths))
        self.progress_bar.setValue(0)
        self.progress_bar.setFormat("Preparing…")
        self._set_activity("Preparing")

        self._thread = QThread(self)
        self._worker = self._create_processing_worker(
            create_searchable_pdf=create_searchable_pdf,
            create_markdown=create_markdown,
            create_json=create_json,
            executable=executable,
        )
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.file_started.connect(self._on_file_started)
        self._worker.file_succeeded.connect(self._on_file_succeeded)
        self._worker.file_failed.connect(self._on_file_failed)
        self._worker.finished.connect(self._on_processing_finished)
        self._worker.finished.connect(self._thread.quit)
        self._worker.finished.connect(self._worker.deleteLater)
        self._thread.finished.connect(self._thread.deleteLater)
        self._thread.finished.connect(self._clear_worker_references)
        self._thread.start()

    def cancel_processing(self) -> None:
        if self._worker is not None:
            self.cancel_button.setEnabled(False)
            self.progress_bar.setFormat("Canceling…")
            self._set_activity("Canceling")
            self._worker.cancel()

    def _on_file_started(self, index: int, total: int, filename: str) -> None:
        self.progress_bar.setFormat(f"Processing {index} of {total}: {filename}")
        self._set_activity(f"Processing {filename}")
        self.statusBar().showMessage(f"Processing {filename}")
        item = self.queue.item(index - 1)
        if item is not None:
            self.queue.setCurrentItem(item)
            self.queue.scrollToItem(item, QListWidget.ScrollHint.EnsureVisible)

    def _on_file_succeeded(self, input_path: str, output_path: str) -> None:
        self._completed_count += 1
        self.progress_bar.setValue(self._completed_count)
        self._mark_queue_item(Path(input_path), True, output_path)

    def _on_file_failed(self, input_path: str, error: str) -> None:
        self._completed_count += 1
        self.progress_bar.setValue(self._completed_count)
        self._processing_errors.append(error)
        self._mark_queue_item(Path(input_path), False, error)
        self._set_activity(f"Failed {Path(input_path).name}")

    def _on_processing_finished(self, cancelled: bool, succeeded: int, failed: int) -> None:
        self._processing = False
        self.cancel_button.setEnabled(False)
        self._set_inputs_enabled(True)
        self.update_process_button()

        if cancelled:
            self.progress_bar.setFormat("Canceled")
            self._set_activity("Canceled")
            self.statusBar().showMessage("Processing canceled")
            return

        self.progress_bar.setValue(self.progress_bar.maximum())
        self.progress_bar.setFormat(f"Completed: {succeeded} succeeded, {failed} failed")
        self._set_activity("Completed" if failed == 0 else "Completed with failures")
        self.statusBar().showMessage("Document processing complete")
        if failed:
            QMessageBox.warning(
                self,
                "Processing completed with errors",
                "Some documents could not be processed. Select a failed item for details.",
            )
        else:
            QMessageBox.information(
                self,
                "Processing complete",
                f"Processed {succeeded} document{'s' if succeeded != 1 else ''} successfully.",
            )

    def _mark_queue_item(self, input_path: Path, succeeded: bool, detail: str) -> None:
        try:
            row = self._pdf_paths.index(input_path.resolve())
        except ValueError:
            return
        item = self.queue.item(row)
        prefix = "Completed" if succeeded else "Failed"
        item.setText(f"{prefix}: {input_path.name}")
        item.setToolTip(detail)

    def _set_inputs_enabled(self, enabled: bool) -> None:
        self.drop_area.setEnabled(enabled)
        self.output_group.setEnabled(enabled)
        for button in (
            self.add_files_button,
            self.add_folder_button,
            self.remove_button,
            self.clear_button,
        ):
            button.setEnabled(enabled)
        if not enabled:
            self.process_button.setEnabled(False)

    def _clear_worker_references(self) -> None:
        self._worker = None
        self._thread = None

    def _update_status(self) -> None:
        count = len(self._pdf_paths)
        if count == 0:
            message = "Add one or more PDF files"
            self._set_activity("Ready")
        else:
            message = f"{count} PDF file{'s' if count != 1 else ''} queued"
        self.statusBar().showMessage(message)

    def _set_activity(self, value: str) -> None:
        self.activity_label.setText(f"Activity: {value}")

    def _create_processing_worker(
        self,
        *,
        create_searchable_pdf: bool,
        create_markdown: bool,
        create_json: bool,
        executable: str | None,
    ) -> ProcessingWorker:
        if self._output_directory is None:
            raise RuntimeError("Output directory is required before starting processing.")
        return ProcessingWorker(
            tuple(self._pdf_paths),
            self._output_directory,
            create_searchable_pdf=create_searchable_pdf,
            create_markdown=create_markdown,
            create_json=create_json,
            executable=executable,
        )
