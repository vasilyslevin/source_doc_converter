from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QSettings, QSize, Qt, QThread, QUrl, Signal
from PySide6.QtGui import QCloseEvent, QColor, QDesktopServices, QResizeEvent, QShowEvent
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from source_doc_converter import ui_geometry
from source_doc_converter.dependency_setup import DependencySetupWorker, _default_steps
from source_doc_converter.error_dialog import ErrorDetailsDialog
from source_doc_converter.model_downloader import ModelDownloadWorker
from source_doc_converter.model_management import (
    ModelDirectoryState,
    load_model_directory,
    reset_model_directory,
    save_model_directory,
)
from source_doc_converter.system_diagnostics import (
    SystemDiagnostics,
    collect_system_diagnostics,
    component_state_text,
    installation_guidance,
)

GHOSTSCRIPT_RELEASES_URL = "https://ghostscript.com/releases/"


class ActivityDetailsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Setup details")
        self.details_edit = QPlainTextEdit()
        self.details_edit.setReadOnly(True)
        self.details_edit.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        layout = QVBoxLayout()
        layout.addWidget(self.details_edit)
        layout.addWidget(buttons)
        self.setLayout(layout)
        ui_geometry.apply_initial_geometry(self, QSize(760, 420))

    def append_line(self, line: str) -> None:
        text = self.details_edit.toPlainText()
        if text:
            self.details_edit.setPlainText(f"{text}\n{line}")
        else:
            self.details_edit.setPlainText(line)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        ui_geometry.clamp_widget_to_available_screen(self)


class SystemCheckDialog(QDialog):
    diagnostics_updated = Signal(object)
    _BUTTON_TWO_COLUMN_MIN_WIDTH = 560

    def __init__(
        self,
        parent: QWidget | None = None,
        *,
        diagnostics_provider: Callable[[], SystemDiagnostics] = collect_system_diagnostics,
        settings: QSettings | None = None,
        model_worker_factory: Callable[[Path], ModelDownloadWorker] = ModelDownloadWorker,
    ) -> None:
        super().__init__(parent)
        self._diagnostics_provider = diagnostics_provider
        self._settings = settings if settings is not None else QSettings()
        self._model_worker_factory = model_worker_factory
        self._diagnostics: SystemDiagnostics | None = None
        self._model_state: ModelDirectoryState | None = None
        self._download_thread: QThread | None = None
        self._download_worker: ModelDownloadWorker | None = None
        self._dependency_thread: QThread | None = None
        self._dependency_worker: DependencySetupWorker | None = None
        self._details_dialog = ActivityDetailsDialog(self)

        self.setWindowTitle("System Check")

        self.system_label = QLabel()
        self.system_label.setWordWrap(True)
        self.activity_status_label = QLabel("Status: Ready")
        self.activity_status_label.setWordWrap(True)
        self.details_button = QPushButton("Show Setup Details")
        self.details_button.clicked.connect(self._details_dialog.show)
        status_row = QHBoxLayout()
        status_row.addWidget(self.activity_status_label, 1)
        status_row.addStretch()
        status_row.addWidget(self.details_button)

        self.component_table = QTableWidget(0, 3)
        self.component_table.setHorizontalHeaderLabels(["Component", "Status", "Details"])
        self.component_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeMode.Interactive
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.ResizeMode.Interactive
        )
        self.component_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.ResizeMode.Stretch
        )
        self.component_table.setColumnWidth(0, 150)
        self.component_table.setColumnWidth(1, 120)
        self.component_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.component_table.setSelectionMode(QTableWidget.SelectionMode.NoSelection)
        self.component_table.setWordWrap(True)
        self.component_table.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.component_table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.component_table.setMinimumWidth(0)

        self.guidance_label = QPlainTextEdit()
        self.guidance_label.setReadOnly(True)
        self.guidance_label.setLineWrapMode(QPlainTextEdit.LineWrapMode.WidgetWidth)
        self.guidance_label.setMinimumHeight(72)
        self.guidance_label.setMaximumHeight(96)
        self.guidance_label.setPlaceholderText("No installation guidance needed.")

        dependency_group = QGroupBox("Guided OCR tool setup")
        self.setup_dependencies_button = QPushButton("Install Missing OCR Tools")
        self.setup_dependencies_button.clicked.connect(self.start_dependency_setup)
        self.ghostscript_button = QPushButton("Get Ghostscript…")
        self.ghostscript_button.clicked.connect(self.open_ghostscript_download_page)
        self.ghostscript_button.setVisible(False)
        self.cancel_setup_button = QPushButton("Cancel Setup")
        self.cancel_setup_button.setEnabled(False)
        self.cancel_setup_button.clicked.connect(self.cancel_setup)
        self._dependency_buttons_layout = QGridLayout()
        self._dependency_buttons_layout.setHorizontalSpacing(8)
        self._dependency_buttons_layout.setVerticalSpacing(6)
        dependency_copy = QLabel(
            "Installs missing OCRmyPDF/Tesseract dependencies in the background. "
            "Uses Homebrew on macOS or winget on Windows after explicit confirmation. "
            "Windows Full bundles OCRmyPDF and Tesseract. "
            "Ghostscript remains optional/recommended for PDF/A and advanced post-processing."
        )
        dependency_copy.setWordWrap(True)
        dependency_layout = QVBoxLayout()
        dependency_layout.addWidget(dependency_copy)
        dependency_layout.addLayout(self._dependency_buttons_layout)
        dependency_group.setLayout(dependency_layout)

        model_group = QGroupBox("Local AI models")
        self.model_status_label = QLabel()
        self.model_status_label.setWordWrap(True)
        self.choose_model_button = QPushButton("Choose Model Folder")
        self.choose_model_button.clicked.connect(self.choose_model_directory)
        self.reset_model_button = QPushButton("Reset to Default Folder")
        self.reset_model_button.clicked.connect(self.reset_to_default_model_directory)
        self.download_model_button = QPushButton("Download Models")
        self.download_model_button.clicked.connect(self.confirm_model_download)
        self.cancel_download_button = QPushButton("Cancel Download")
        self.cancel_download_button.setEnabled(False)
        self.cancel_download_button.clicked.connect(self.cancel_model_download)
        self._model_buttons_layout = QGridLayout()
        self._model_buttons_layout.setHorizontalSpacing(8)
        self._model_buttons_layout.setVerticalSpacing(6)
        model_layout = QVBoxLayout()
        model_layout.addWidget(self.model_status_label)
        model_layout.addLayout(self._model_buttons_layout)
        model_group.setLayout(model_layout)

        self.refresh_button = QPushButton("Refresh")
        self.refresh_button.clicked.connect(self.refresh)
        self.save_button = QPushButton("Save Report")
        self.save_button.clicked.connect(self.choose_report_path)
        self.close_button = QPushButton("Close")
        self.close_button.clicked.connect(self.accept)

        buttons = QHBoxLayout()
        buttons.addWidget(self.refresh_button)
        buttons.addWidget(self.save_button)
        buttons.addStretch()
        buttons.addWidget(self.close_button)

        content_layout = QVBoxLayout()
        content_layout.setContentsMargins(8, 8, 8, 8)
        content_layout.setSpacing(6)
        content_layout.addWidget(self.system_label)
        content_layout.addLayout(status_row)
        content_layout.addWidget(self.component_table)
        content_layout.addWidget(self.guidance_label)
        content_layout.addWidget(dependency_group)
        content_layout.addWidget(model_group)
        content = QWidget()
        content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        content.setLayout(content_layout)
        self.content_scroll = QScrollArea()
        self.content_scroll.setWidgetResizable(True)
        self.content_scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.content_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.content_scroll.setWidget(content)
        layout = QVBoxLayout()
        layout.addWidget(self.content_scroll)
        layout.addLayout(buttons)
        self.setLayout(layout)
        ui_geometry.apply_initial_geometry(self, QSize(760, 600))
        self._arrange_action_button_grids(force=True)
        self.setTabOrder(self.details_button, self.setup_dependencies_button)
        self.setTabOrder(self.setup_dependencies_button, self.ghostscript_button)
        self.setTabOrder(self.ghostscript_button, self.cancel_setup_button)
        self.setTabOrder(self.cancel_setup_button, self.choose_model_button)

        self.refresh()

    @property
    def diagnostics(self) -> SystemDiagnostics | None:
        return self._diagnostics

    @property
    def model_state(self) -> ModelDirectoryState | None:
        return self._model_state

    def refresh(self) -> None:
        self.refresh_button.setEnabled(False)
        self._set_activity_status("Checking dependencies…")
        try:
            diagnostics = self._diagnostics_provider()
        finally:
            self.refresh_button.setEnabled(True)

        self._diagnostics = diagnostics
        self._populate(diagnostics)
        self.refresh_model_state()
        if not self._setup_active():
            self._set_activity_status("Ready")
        self.diagnostics_updated.emit(diagnostics)

    def refresh_model_state(self) -> None:
        state = load_model_directory(self._settings)
        self._model_state = state
        status = "Ready for offline conversion" if state.ready else "Models not installed"
        colour = "#18794e" if state.ready else "#9a6700"
        source = {
            "environment": "managed environment setting",
            "settings": "selected folder",
            "default": "application default",
        }.get(state.source, state.source)
        self.model_status_label.setText(
            f'<span style="color:{colour}">{status}</span><br>'
            f"Active folder: {state.path}<br>Source: {source}<br>"
            "Document conversion uses local model files after setup."
        )
        managed = state.source == "environment"
        active = self._download_thread is not None or self._dependency_thread is not None
        self.choose_model_button.setEnabled(not managed and not active)
        self.reset_model_button.setEnabled(
            not managed and state.source == "settings" and not active
        )
        self.choose_model_button.setToolTip(
            "The folder is controlled by SOURCE_DOC_CONVERTER_MODEL_DIR."
            if managed
            else ""
        )
        self.reset_model_button.setToolTip(
            "Clear the saved folder selection without deleting any model files."
        )
        self.download_model_button.setEnabled(not active)
        diagnostics = self._diagnostics
        self.setup_dependencies_button.setEnabled(
            bool(diagnostics and _default_steps(diagnostics)) and not active
        )

    def choose_model_directory(self) -> None:
        state = self._model_state or load_model_directory(self._settings)
        selected = QFileDialog.getExistingDirectory(
            self,
            "Choose local model folder",
            str(state.path),
        )
        if not selected:
            return
        save_model_directory(selected, self._settings)
        self.refresh_model_state()

    def reset_to_default_model_directory(self) -> None:
        reset_model_directory(self._settings)
        self.refresh_model_state()

    def confirm_model_download(self) -> None:
        state = self._model_state or load_model_directory(self._settings)
        answer = QMessageBox.question(
            self,
            "Download local AI models?",
            "This setup downloads generic Docling and OCR model files from external model "
            "hosting services such as Hugging Face or ModelScope. Downloads may be large.\n\n"
            "No queued document, document filename, extracted text, or output is supplied to "
            "the downloader. After setup, document conversion is intended to use the local "
            "model files.\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self.start_model_download(state.path)

    def start_model_download(self, model_directory: Path) -> None:
        if self._download_thread is not None or self._dependency_thread is not None:
            return
        self._download_thread = QThread(self)
        self._download_worker = self._model_worker_factory(model_directory)
        self._download_worker.moveToThread(self._download_thread)
        self._download_thread.started.connect(self._download_worker.run)
        self._download_worker.status_changed.connect(self._set_activity_status)
        self._download_worker.details_changed.connect(self._append_setup_detail)
        self._download_worker.completed.connect(self._on_download_completed)
        self._download_worker.failed.connect(self._on_download_failed)
        self._download_worker.cancelled.connect(self._on_download_cancelled)
        self._download_worker.finished.connect(self._download_thread.quit)
        self._download_worker.finished.connect(self._download_worker.deleteLater)
        self._download_thread.finished.connect(self._download_thread.deleteLater)
        self._download_thread.finished.connect(self._clear_download_references)
        self._set_setup_controls_active(True, model_download=True)
        self._download_thread.start()

    def cancel_model_download(self) -> None:
        if self._download_worker is not None:
            self.cancel_download_button.setEnabled(False)
            self._set_activity_status("Canceling model download…")
            self._download_worker.cancel()

    def start_dependency_setup(self) -> None:
        if self._download_thread is not None or self._dependency_thread is not None:
            return
        diagnostics = self._diagnostics or self._diagnostics_provider()
        steps = _default_steps(diagnostics)
        if not steps:
            QMessageBox.information(
                self,
                "Manual setup required",
                "No guided installer is available for the currently missing OCR tools.\n\n"
                "Use the guidance shown in System Check to install missing tools manually.",
            )
            return
        commands = "\n".join(f"- {' '.join(step.command)}" for step in steps)
        answer = QMessageBox.question(
            self,
            "Install missing OCR tools?",
            "This guided setup will run the following commands for missing OCR tools:\n\n"
            f"{commands}\n\nContinue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._dependency_thread = QThread(self)
        self._dependency_worker = DependencySetupWorker(
            diagnostics_provider=self._diagnostics_provider,
            steps_builder=lambda _: steps,
        )
        self._dependency_worker.moveToThread(self._dependency_thread)
        self._dependency_thread.started.connect(self._dependency_worker.run)
        self._dependency_worker.status_changed.connect(self._set_activity_status)
        self._dependency_worker.details_changed.connect(self._append_setup_detail)
        self._dependency_worker.completed.connect(self._on_dependency_setup_completed)
        self._dependency_worker.failed.connect(self._on_dependency_setup_failed)
        self._dependency_worker.cancelled.connect(self._on_dependency_setup_cancelled)
        self._dependency_worker.finished.connect(self._dependency_thread.quit)
        self._dependency_worker.finished.connect(self._dependency_worker.deleteLater)
        self._dependency_thread.finished.connect(self._dependency_thread.deleteLater)
        self._dependency_thread.finished.connect(self._clear_dependency_references)
        self._set_setup_controls_active(True, model_download=False)
        self._dependency_thread.start()

    def cancel_setup(self) -> None:
        if self._dependency_worker is not None:
            self.cancel_setup_button.setEnabled(False)
            self._set_activity_status("Canceling setup…")
            self._dependency_worker.cancel()

    def _set_setup_controls_active(self, active: bool, *, model_download: bool) -> None:
        self.choose_model_button.setEnabled(not active)
        self.reset_model_button.setEnabled(not active)
        self.download_model_button.setEnabled(not active)
        self.setup_dependencies_button.setEnabled(not active)
        if self.ghostscript_button.isVisible():
            self.ghostscript_button.setEnabled(not active)
        self.cancel_download_button.setEnabled(active and model_download)
        self.cancel_setup_button.setEnabled(active and not model_download)
        self.refresh_button.setEnabled(not active)
        self.save_button.setEnabled(not active)
        self.close_button.setEnabled(not active)

    def _set_activity_status(self, status: str) -> None:
        self.activity_status_label.setText(f"Status: {status}")

    def _append_setup_detail(self, line: str) -> None:
        self._details_dialog.append_line(line)

    def _on_download_completed(self) -> None:
        self.refresh_model_state()
        self._set_activity_status("Completed")
        QMessageBox.information(
            self,
            "Model setup complete",
            "The local model files are ready for offline document conversion.",
        )

    def _on_download_failed(self, message: str) -> None:
        self._set_activity_status("Failed")
        ErrorDetailsDialog(
            message,
            self,
            title="Model download failed",
            summary="The model download did not complete.",
        ).exec()

    def _on_download_cancelled(self) -> None:
        self._set_activity_status("Canceled")
        self.model_status_label.setText(
            "Model download canceled. Incomplete files will not be treated as ready."
        )

    def _clear_download_references(self) -> None:
        self._download_worker = None
        self._download_thread = None
        self._set_setup_controls_active(False, model_download=True)
        self.refresh_model_state()

    def _on_dependency_setup_completed(self) -> None:
        self._set_activity_status("Completed")
        self.refresh()
        QMessageBox.information(
            self,
            "Dependency setup complete",
            "Dependency checks finished successfully.",
        )

    def _on_dependency_setup_failed(self, message: str) -> None:
        self._set_activity_status("Failed")
        ErrorDetailsDialog(
            message,
            self,
            title="Dependency setup failed",
            summary="Guided dependency setup did not complete.",
        ).exec()

    def _on_dependency_setup_cancelled(self, message: str) -> None:
        self._set_activity_status("Canceled")
        self._append_setup_detail(message)

    def _clear_dependency_references(self) -> None:
        self._dependency_worker = None
        self._dependency_thread = None
        self._set_setup_controls_active(False, model_download=False)
        self.refresh_model_state()

    def _setup_active(self) -> bool:
        return self._download_thread is not None or self._dependency_thread is not None

    def _populate(self, diagnostics: SystemDiagnostics) -> None:
        build_lines = []
        if diagnostics.package_flavor:
            build_lines.append(f"Package {diagnostics.package_flavor}")
        if diagnostics.source_commit_sha:
            build_lines.append(f"Commit {diagnostics.source_commit_sha}")
        build_info = f"<br>{'; '.join(build_lines)}" if build_lines else ""
        self.system_label.setText(
            f"Source Document Converter {diagnostics.application_version}<br>"
            f"{diagnostics.operating_system} {diagnostics.operating_system_version} "
            f"({diagnostics.architecture})<br>"
            f"Python {diagnostics.python_version}; PySide6 {diagnostics.pyside_version}"
            f"{build_info}"
        )

        self.component_table.setRowCount(len(diagnostics.components))
        missing_components: list[str] = []
        ghostscript_missing = False
        for row, component in enumerate(diagnostics.components):
            self.component_table.setItem(row, 0, QTableWidgetItem(component.label))
            status_item = QTableWidgetItem(component_state_text(component))
            if component.available:
                status_color = "#18794e"
            elif component.key == "ghostscript":
                status_color = "#9a6700"
            else:
                status_color = "#b42318"
            status_item.setForeground(QColor(status_color))
            self.component_table.setItem(row, 1, status_item)
            details = []
            if component.version:
                details.append(component.version)
            details.extend(component.details)
            if component.error:
                details.append(component.error)
            detail_text = "; ".join(details)
            wrapped_detail_text = self._wrap_unbroken_segments(detail_text)
            detail_item = QTableWidgetItem(wrapped_detail_text)
            detail_item.setToolTip(detail_text)
            self.component_table.setItem(row, 2, detail_item)
            if not component.available:
                missing_components.append(component.key)
                if component.key == "ghostscript":
                    ghostscript_missing = True

        guidance = [installation_guidance(component) for component in missing_components]
        self.guidance_label.setPlainText("\n".join(dict.fromkeys(guidance)))
        self.component_table.setColumnWidth(0, min(max(self.component_table.columnWidth(0), 120), 180))
        self.component_table.setColumnWidth(1, min(max(self.component_table.columnWidth(1), 100), 160))
        self._arrange_action_button_grids()
        has_guided_steps = bool(_default_steps(diagnostics))
        self.setup_dependencies_button.setEnabled(has_guided_steps and not self._setup_active())
        show_ghostscript_action = diagnostics.operating_system == "Windows" and ghostscript_missing
        self.ghostscript_button.setVisible(show_ghostscript_action)
        self.ghostscript_button.setEnabled(show_ghostscript_action and not self._setup_active())

    def choose_report_path(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self,
            "Save system report",
            "source-document-converter-system-check.txt",
            "Text files (*.txt)",
        )
        if path:
            self.save_report(Path(path))

    def save_report(self, path: Path) -> None:
        if self._diagnostics is None:
            raise RuntimeError("No diagnostic report is available")
        state = self._model_state or load_model_directory(self._settings)
        model_status = "Ready" if state.ready else "Not ready"
        content = (
            self._diagnostics.to_text().rstrip()
            + "\n\nLocal model setup\n"
            + f"Models: {model_status}\n"
            + "Offline conversion: Enabled by default\n"
        )
        path.write_text(content, encoding="utf-8", newline="\n")

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._setup_active():
            QMessageBox.information(
                self,
                "Setup in progress",
                "Cancel active setup operations before closing System Check.",
            )
            event.ignore()
            return
        super().closeEvent(event)

    def showEvent(self, event: QShowEvent) -> None:
        super().showEvent(event)
        self._arrange_action_button_grids(force=True)
        ui_geometry.clamp_widget_to_available_screen(self)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        self._arrange_action_button_grids()

    def _arrange_action_button_grids(self, *, force: bool = False) -> None:
        viewport_width = self.content_scroll.viewport().width() if hasattr(self, "content_scroll") else 0
        use_two_columns = viewport_width >= self._BUTTON_TWO_COLUMN_MIN_WIDTH
        signature = (use_two_columns, viewport_width)
        if not force and getattr(self, "_button_layout_signature", None) == signature:
            return
        self._button_layout_signature = signature
        self._rebuild_dependency_buttons_layout(use_two_columns)
        self._rebuild_model_buttons_layout(use_two_columns)

    def _rebuild_dependency_buttons_layout(self, use_two_columns: bool) -> None:
        while self._dependency_buttons_layout.count():
            self._dependency_buttons_layout.takeAt(0)
        if use_two_columns:
            self._dependency_buttons_layout.addWidget(self.setup_dependencies_button, 0, 0)
            self._dependency_buttons_layout.addWidget(self.ghostscript_button, 0, 1)
            self._dependency_buttons_layout.addWidget(self.cancel_setup_button, 1, 0)
            self._dependency_buttons_layout.setColumnStretch(2, 1)
            return
        self._dependency_buttons_layout.addWidget(self.setup_dependencies_button, 0, 0)
        self._dependency_buttons_layout.addWidget(self.ghostscript_button, 1, 0)
        self._dependency_buttons_layout.addWidget(self.cancel_setup_button, 2, 0)
        self._dependency_buttons_layout.setColumnStretch(0, 1)

    def _rebuild_model_buttons_layout(self, use_two_columns: bool) -> None:
        while self._model_buttons_layout.count():
            self._model_buttons_layout.takeAt(0)
        if use_two_columns:
            self._model_buttons_layout.addWidget(self.choose_model_button, 0, 0)
            self._model_buttons_layout.addWidget(self.reset_model_button, 0, 1)
            self._model_buttons_layout.addWidget(self.download_model_button, 1, 0)
            self._model_buttons_layout.addWidget(self.cancel_download_button, 1, 1)
            self._model_buttons_layout.setColumnStretch(2, 1)
            return
        self._model_buttons_layout.addWidget(self.choose_model_button, 0, 0)
        self._model_buttons_layout.addWidget(self.reset_model_button, 1, 0)
        self._model_buttons_layout.addWidget(self.download_model_button, 2, 0)
        self._model_buttons_layout.addWidget(self.cancel_download_button, 3, 0)
        self._model_buttons_layout.setColumnStretch(0, 1)

    @staticmethod
    def _wrap_unbroken_segments(text: str, *, chunk_size: int = 24) -> str:
        if not text:
            return text
        pieces: list[str] = []
        token: list[str] = []
        for char in text:
            if char.isspace():
                if token:
                    pieces.append(SystemCheckDialog._wrap_token("".join(token), chunk_size))
                    token.clear()
                pieces.append(char)
                continue
            token.append(char)
        if token:
            pieces.append(SystemCheckDialog._wrap_token("".join(token), chunk_size))
        return "".join(pieces)

    @staticmethod
    def _wrap_token(token: str, chunk_size: int) -> str:
        if len(token) <= chunk_size:
            return token
        return "\u200b".join(
            token[start : start + chunk_size] for start in range(0, len(token), chunk_size)
        )

    def open_ghostscript_download_page(self) -> None:
        answer = QMessageBox.question(
            self,
            "Open Ghostscript download page?",
            "Ghostscript is optional. Standard searchable PDF works without it.\n\n"
            "Ghostscript is only needed for PDF/A and advanced OCRmyPDF post-processing.\n\n"
            "Open the official Ghostscript releases page in your browser now?\n"
            "After installation, click Refresh to recheck.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        if not QDesktopServices.openUrl(QUrl(GHOSTSCRIPT_RELEASES_URL)):
            QMessageBox.warning(
                self,
                "Unable to open browser",
                "The Ghostscript download page could not be opened. "
                f"Please open it manually: {GHOSTSCRIPT_RELEASES_URL}",
            )
