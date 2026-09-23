from collections.abc import Callable
from pathlib import Path

from PySide6.QtCore import QElapsedTimer, QSettings, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QGroupBox,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QToolButton,
    QVBoxLayout,
    QWidget,
)
from PySide6.QtWidgets import (
    QListWidgetItem as QtListWidgetItem,
)

from source_doc_converter.docling_runtime import (
    _cpu_thread_count,
)
from source_doc_converter.error_dialog import ErrorDetailsDialog
from source_doc_converter.help_content import ABOUT, GETTING_STARTED, SETTINGS_GUIDE, HelpSection
from source_doc_converter.help_dialog import HelpDialog
from source_doc_converter.main_window import MainWindow
from source_doc_converter.model_management import (
    ModelDirectoryState,
    load_model_directory,
)
from source_doc_converter.ocr_runtime import (
    TESSERACT_PROFILE_MODE_SETTING,
    TESSERACT_PROFILE_PATH_SETTING,
    TesseractInstallation,
    discover_tesseract_installations,
    load_language_selection,
    resolve_tesseract_profile,
    save_language_selection,
    validate_tesseract_executable,
)
from source_doc_converter.ocr_worker import ProcessingWorker
from source_doc_converter.system_check_dialog import SystemCheckDialog
from source_doc_converter.system_diagnostics import (
    OutputAvailability,
    SystemDiagnostics,
    check_output_availability,
    check_pypdf,
)

DOCLING_OCR_SETTING = "processing/docling_ocr"
DOCLING_TABLES_SETTING = "processing/docling_tables"
AI_TABLE_ANALYSIS_SETTING = "processing/ai_table_analysis"
DOCLING_CPU_ONLY_SETTING = "processing/docling_cpu_only"
OCR_MODE_SETTING = "processing/ocr_mode"
AI_ANALYSIS_MODE_SETTING = "processing/ai_analysis_mode"
PROCESSING_PROFILE_SETTING = "processing/performance_profile"
ADVANCED_OPTIONS_SETTING = "ui/advanced_options_expanded"


def format_elapsed(milliseconds: int) -> str:
    total_seconds = max(0, milliseconds // 1000)
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours:d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"


class ApplicationWindow(MainWindow):
    def __init__(
        self,
        *,
        availability_provider: Callable[[], OutputAvailability] = check_output_availability,
        model_state_provider: Callable[[], ModelDirectoryState] = load_model_directory,
        settings: QSettings | None = None,
    ) -> None:
        self._availability_provider = availability_provider
        self._model_state_provider = model_state_provider
        self._settings = settings if settings is not None else QSettings()
        super().__init__()
        self._processing_clock = QElapsedTimer()
        self._processing_timer = QTimer(self)
        self._processing_timer.setInterval(1000)
        self._processing_timer.timeout.connect(self._refresh_processing_text)
        self._processing_stage = "Preparing"
        self._processing_file = ""
        self._tesseract_installations: tuple[TesseractInstallation, ...] = ()
        self._active_tesseract_languages: tuple[str, ...] = ()
        self._docling_controls_allowed = True
        self._migrate_table_preferences()
        self.queue.itemClicked.connect(self.show_queue_item_details)
        self._add_docling_performance_controls()
        self.searchable_pdf_checkbox.checkStateChanged.connect(self._update_advanced_relevance)
        self.markdown_checkbox.checkStateChanged.connect(self._update_advanced_relevance)
        self.json_checkbox.checkStateChanged.connect(self._update_advanced_relevance)

        help_menu = self.menuBar().addMenu("Help")
        self.getting_started_action = help_menu.addAction("Getting Started")
        self.getting_started_action.triggered.connect(self.show_getting_started)
        self.settings_guide_action = help_menu.addAction("Settings Guide")
        self.settings_guide_action.triggered.connect(self.show_settings_guide)
        self.system_check_action = help_menu.addAction("System Check")
        self.system_check_action.triggered.connect(self.show_system_check)
        self.about_action = help_menu.addAction("About")
        self.about_action.triggered.connect(self.show_about)

        self.refresh_output_availability()
        self._update_open_output_button()
        self.refresh_tesseract_runtime()

    def _setting_bool(self, key: str, default: bool) -> bool:
        value = self._settings.value(key, default)
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}

    def _migrate_table_preferences(self) -> None:
        analysis_mode = str(self._settings.value(AI_ANALYSIS_MODE_SETTING, "auto"))
        table_enabled = self._setting_bool(AI_TABLE_ANALYSIS_SETTING, False)
        if analysis_mode == "accurate_tables":
            analysis_mode = "accurate"
            table_enabled = True
        elif self._settings.contains(DOCLING_TABLES_SETTING):
            table_enabled = self._setting_bool(DOCLING_TABLES_SETTING, table_enabled)
        self._settings.setValue(AI_ANALYSIS_MODE_SETTING, analysis_mode)
        self._settings.setValue(AI_TABLE_ANALYSIS_SETTING, table_enabled)
        self._settings.setValue(DOCLING_TABLES_SETTING, table_enabled)
        self._settings.sync()

    def _add_docling_performance_controls(self) -> None:
        self.docling_ocr_checkbox = QCheckBox("Use Docling OCR for AI output")
        self.docling_ocr_checkbox.setChecked(
            self._setting_bool(DOCLING_OCR_SETTING, False)
        )
        self.docling_ocr_checkbox.setToolTip(
            "Enable only for scanned PDFs without selectable text. This is slower."
        )
        self.docling_ocr_checkbox.setAccessibleDescription(
            "Enable OCR scanned pages in AI output. This affects Markdown and JSON outputs only."
        )
        self.table_structure_checkbox = QCheckBox("Analyze table structure")
        self.table_structure_checkbox.setChecked(
            self._setting_bool(AI_TABLE_ANALYSIS_SETTING, False)
        )
        self.table_structure_checkbox.setToolTip(
            "Improves complex tables but adds substantial CPU processing time."
        )
        self.cpu_only_checkbox = QCheckBox("CPU only")
        self.cpu_only_checkbox.setChecked(
            self._setting_bool(DOCLING_CPU_ONLY_SETTING, True)
        )
        self.cpu_only_checkbox.setToolTip(
            "Uncheck to let Docling automatically use a supported GPU when available."
        )
        self.cpu_only_checkbox.setAccessibleDescription(
            "Use CPU-only processing for maximum compatibility and predictable behavior."
        )
        for checkbox in (
            self.docling_ocr_checkbox,
            self.table_structure_checkbox,
            self.cpu_only_checkbox,
        ):
            checkbox.toggled.connect(self._save_processing_preferences)

        self.ocr_mode_combo = QComboBox()
        self.ocr_mode_combo.addItem("Smart legal document (recommended)", "smart")
        self.ocr_mode_combo.addItem("Skip existing text", "skip")
        self.ocr_mode_combo.addItem("Redo OCR", "redo")
        self.ocr_mode_combo.addItem("Force OCR", "force")
        self.ocr_mode_combo.setToolTip(
            "Skip is fastest but can miss scanned bodies under digital headers. "
            "Redo is intended for mixed pages or unreliable old OCR. "
            "Force rasterizes everything and is the last-resort repair mode."
        )
        self._configure_responsive_combo(self.ocr_mode_combo, min_chars=20)
        saved_mode = str(self._settings.value(OCR_MODE_SETTING, "smart"))
        for index in range(self.ocr_mode_combo.count()):
            if self.ocr_mode_combo.itemData(index) == saved_mode:
                self.ocr_mode_combo.setCurrentIndex(index)
                break
        self.ocr_mode_combo.currentIndexChanged.connect(self._save_processing_preferences)

        ocr_mode_row = QVBoxLayout()
        ocr_mode_row.addWidget(QLabel("OCR mode:"))
        ocr_mode_row.addWidget(self.ocr_mode_combo)
        self.ai_analysis_mode_combo = QComboBox()
        self.ai_analysis_mode_combo.addItem("Auto (recommended)", "auto")
        self.ai_analysis_mode_combo.addItem("Fast Markdown", "fast")
        self.ai_analysis_mode_combo.addItem("Accurate Markdown", "accurate")
        self.ai_analysis_mode_combo.setToolTip(
            "Auto picks a mode based on source content. "
            "Fast is quickest plain-text markdown. Accurate preserves richer layout."
        )
        self._configure_responsive_combo(self.ai_analysis_mode_combo, min_chars=16)
        saved_analysis_mode = str(self._settings.value(AI_ANALYSIS_MODE_SETTING, "auto"))
        for index in range(self.ai_analysis_mode_combo.count()):
            if self.ai_analysis_mode_combo.itemData(index) == saved_analysis_mode:
                self.ai_analysis_mode_combo.setCurrentIndex(index)
                break
        self.ai_analysis_mode_combo.currentIndexChanged.connect(self._save_processing_preferences)
        self.ai_analysis_mode_combo.currentIndexChanged.connect(
            self._update_table_analysis_availability
        )
        ai_mode_row = QVBoxLayout()
        ai_mode_row.addWidget(QLabel("AI analysis mode:"))
        ai_mode_row.addWidget(self.ai_analysis_mode_combo)

        self.processing_profile_combo = QComboBox()
        self.processing_profile_combo.addItem("Maximum speed", "max_speed")
        self.processing_profile_combo.addItem("Balanced", "balanced")
        self.processing_profile_combo.addItem("Energy saver", "energy_saver")
        self.processing_profile_combo.setToolTip(
            "Maximum speed uses higher safe worker counts. "
            "Balanced is moderate. Energy saver uses 2 OCR workers and lower Docling threads."
        )
        self._configure_responsive_combo(self.processing_profile_combo, min_chars=16)
        saved_profile = str(self._settings.value(PROCESSING_PROFILE_SETTING, "balanced"))
        for index in range(self.processing_profile_combo.count()):
            if self.processing_profile_combo.itemData(index) == saved_profile:
                self.processing_profile_combo.setCurrentIndex(index)
                break
        self.processing_profile_combo.currentIndexChanged.connect(self._save_processing_preferences)
        profile_row = QVBoxLayout()
        profile_row.addWidget(QLabel("Processing profile:"))
        profile_row.addWidget(self.processing_profile_combo)

        tesseract_layout = QVBoxLayout()
        tesseract_help = QLabel(
            "Tesseract recognizes text in scanned pages and OCRmyPDF creates searchable PDFs."
        )
        tesseract_help.setWordWrap(True)
        tesseract_layout.addWidget(tesseract_help)
        tesseract_row = QVBoxLayout()
        self.tesseract_profile_combo = QComboBox()
        self._configure_responsive_combo(self.tesseract_profile_combo, min_chars=18)
        self.tesseract_profile_combo.currentIndexChanged.connect(self._on_tesseract_profile_changed)
        self.browse_tesseract_button = QPushButton("Browse Tesseract…")
        self.browse_tesseract_button.clicked.connect(self._browse_tesseract)
        self.reset_tesseract_button = QPushButton("Reset to Automatic")
        self.reset_tesseract_button.clicked.connect(self._reset_tesseract_profile)
        tesseract_row.addWidget(self.tesseract_profile_combo)
        tesseract_actions_row = QVBoxLayout()
        tesseract_actions_row.addWidget(self.browse_tesseract_button)
        tesseract_actions_row.addWidget(self.reset_tesseract_button)
        tesseract_row.addLayout(tesseract_actions_row)
        self.tesseract_languages_list = QListWidget()
        self.tesseract_languages_list.setSelectionMode(QListWidget.SelectionMode.MultiSelection)
        self.tesseract_languages_list.itemSelectionChanged.connect(self._save_selected_languages)
        tesseract_layout.addLayout(tesseract_row)
        tesseract_layout.addWidget(self.tesseract_languages_list)
        searchable_group_layout = QVBoxLayout()
        searchable_group_layout.addLayout(ocr_mode_row)
        searchable_group_layout.addLayout(tesseract_layout)
        self.searchable_pdf_group = QGroupBox("Searchable PDF / OCR")
        self.searchable_pdf_group.setLayout(searchable_group_layout)
        self.searchable_pdf_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )
        self.searchable_pdf_group.setToolTip(
            "Used only for Searchable PDF output."
        )

        ai_options_row = QVBoxLayout()
        ai_options_row.addWidget(self.docling_ocr_checkbox)
        docling_ocr_help = QLabel(
            "Runs Docling OCR for Markdown/JSON outputs only. Searchable PDF OCR uses OCRmyPDF and Tesseract."
        )
        docling_ocr_help.setWordWrap(True)
        ai_options_row.addWidget(docling_ocr_help)
        ai_options_row.addWidget(self.table_structure_checkbox)
        ai_help = QLabel(
            "Docling OCR here affects Markdown/JSON outputs only."
        )
        ai_help.setWordWrap(True)
        markdown_group_layout = QVBoxLayout()
        markdown_group_layout.addLayout(ai_mode_row)
        markdown_group_layout.addLayout(ai_options_row)
        markdown_group_layout.addWidget(ai_help)
        self.markdown_json_group = QGroupBox("Markdown and JSON analysis")
        self.markdown_json_group.setLayout(markdown_group_layout)
        self.markdown_json_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        performance_row = QVBoxLayout()
        performance_row.addWidget(self.cpu_only_checkbox)
        cpu_only_help = QLabel(
            "CPU only is the most compatible option. Disable it to allow automatic device selection."
        )
        cpu_only_help.setWordWrap(True)
        performance_row.addWidget(cpu_only_help)
        performance_help = QLabel(
            "CPU only is best for compatibility. Allowing auto device selection may use GPU where supported."
        )
        performance_help.setWordWrap(True)
        performance_layout = QVBoxLayout()
        performance_layout.addLayout(profile_row)
        performance_layout.addLayout(performance_row)
        performance_layout.addWidget(performance_help)
        self.performance_group = QGroupBox("Performance")
        self.performance_group.setLayout(performance_layout)
        self.performance_group.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        self.advanced_toggle_button = QToolButton()
        self.advanced_toggle_button.setText("5) Advanced options")
        self.advanced_toggle_button.setCheckable(True)
        self.advanced_toggle_button.setChecked(
            self._setting_bool(ADVANCED_OPTIONS_SETTING, False)
        )
        self.advanced_toggle_button.toggled.connect(self._set_advanced_panel_visible)
        settings_help_button = QPushButton("Help: Settings Guide")
        settings_help_button.setAccessibleName("Open Settings Guide")
        settings_help_button.clicked.connect(self.show_settings_guide)
        advanced_toggle_row = QVBoxLayout()
        advanced_toggle_row.addWidget(self.advanced_toggle_button)
        advanced_toggle_row.addWidget(settings_help_button)

        self.advanced_panel = QWidget()
        advanced_layout = QVBoxLayout()
        advanced_layout.addWidget(self.searchable_pdf_group)
        advanced_layout.addWidget(self.markdown_json_group)
        advanced_layout.addWidget(self.performance_group)
        self.advanced_panel.setLayout(advanced_layout)
        self.advanced_panel.setVisible(self.advanced_toggle_button.isChecked())

        output_layout = self.output_group.layout()
        if output_layout is not None:
            output_layout.addLayout(advanced_toggle_row)
            output_layout.addWidget(self.advanced_panel)
        self._update_table_analysis_availability()
        self._update_advanced_relevance()

    def _configure_responsive_combo(self, combo: QComboBox, *, min_chars: int) -> None:
        combo.setSizeAdjustPolicy(
            QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon
        )
        combo.setMinimumContentsLength(min_chars)
        combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        combo.setMinimumWidth(0)

    def _save_processing_preferences(self) -> None:
        self._settings.setValue(DOCLING_OCR_SETTING, self.docling_ocr_checkbox.isChecked())
        self._settings.setValue(
            AI_TABLE_ANALYSIS_SETTING,
            self.table_structure_checkbox.isChecked(),
        )
        self._settings.setValue(
            DOCLING_TABLES_SETTING,
            self.table_structure_checkbox.isChecked(),
        )
        self._settings.setValue(
            DOCLING_CPU_ONLY_SETTING,
            self.cpu_only_checkbox.isChecked(),
        )
        self._settings.setValue(OCR_MODE_SETTING, self.ocr_mode_combo.currentData())
        self._settings.setValue(
            AI_ANALYSIS_MODE_SETTING,
            self.ai_analysis_mode_combo.currentData(),
        )
        self._settings.setValue(
            PROCESSING_PROFILE_SETTING,
            self.processing_profile_combo.currentData(),
        )
        self._settings.setValue(
            ADVANCED_OPTIONS_SETTING,
            self.advanced_toggle_button.isChecked(),
        )
        self._settings.sync()

    def _set_advanced_panel_visible(self, visible: bool) -> None:
        self.advanced_panel.setVisible(visible)
        self._save_processing_preferences()

    def _update_table_analysis_availability(self) -> None:
        mode = str(self.ai_analysis_mode_combo.currentData() or "auto")
        available = mode in {"auto", "accurate"} and self._docling_controls_allowed
        self.table_structure_checkbox.setEnabled(available)
        if available:
            self.table_structure_checkbox.setToolTip(
                "Improves complex tables but adds substantial CPU processing time."
            )
        else:
            self.table_structure_checkbox.setToolTip(
                "Table structure analysis is available only for Auto or Accurate mode."
            )

    def _update_advanced_relevance(self) -> None:
        searchable_selected = self.searchable_pdf_checkbox.isChecked()
        ai_selected = self.markdown_checkbox.isChecked() or self.json_checkbox.isChecked()
        self.searchable_pdf_group.setEnabled(
            searchable_selected and self.searchable_pdf_checkbox.isEnabled()
        )
        self.markdown_json_group.setEnabled(
            ai_selected and self.markdown_checkbox.isEnabled() and self._docling_controls_allowed
        )

    def refresh_tesseract_runtime(self) -> None:
        self._tesseract_installations = discover_tesseract_installations()
        previous_mode = str(self._settings.value(TESSERACT_PROFILE_MODE_SETTING, "automatic"))
        previous_path = str(self._settings.value(TESSERACT_PROFILE_PATH_SETTING, ""))
        self.tesseract_profile_combo.blockSignals(True)
        self.tesseract_profile_combo.clear()
        self.tesseract_profile_combo.addItem("Automatic", ("automatic", ""))
        for installation in self._tesseract_installations:
            if installation.is_bundled:
                self.tesseract_profile_combo.addItem(
                    "Bundled Tesseract (recommended)",
                    ("bundled", str(installation.executable)),
                )
            else:
                self.tesseract_profile_combo.addItem(
                    installation.label,
                    ("system", str(installation.executable)),
                )
        selected_index = 0
        for index in range(self.tesseract_profile_combo.count()):
            mode, path = self.tesseract_profile_combo.itemData(index)
            if mode == previous_mode and (not previous_path or path == previous_path):
                selected_index = index
                break
        self.tesseract_profile_combo.setCurrentIndex(selected_index)
        self.tesseract_profile_combo.blockSignals(False)
        self._refresh_tesseract_languages()

    def _refresh_tesseract_languages(self) -> None:
        profile = resolve_tesseract_profile(
            self._settings,
            installations=self._tesseract_installations,
        )
        self.tesseract_languages_list.clear()
        self._active_tesseract_languages = profile.installation.languages if profile else ()
        selected = set(load_language_selection(self._settings))
        for language in self._active_tesseract_languages:
            item = QtListWidgetItem(language)
            self.tesseract_languages_list.addItem(item)
            item.setSelected(language in selected)
        if self.tesseract_languages_list.count() and not self.tesseract_languages_list.selectedItems():
            first = self.tesseract_languages_list.item(0)
            if first is not None:
                first.setSelected(True)
        self._save_selected_languages()

    def _on_tesseract_profile_changed(self) -> None:
        data = self.tesseract_profile_combo.currentData()
        if not data:
            return
        mode, path = data
        self._settings.setValue(TESSERACT_PROFILE_MODE_SETTING, mode)
        self._settings.setValue(TESSERACT_PROFILE_PATH_SETTING, path)
        self._settings.sync()
        self._refresh_tesseract_languages()

    def _browse_tesseract(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Tesseract executable",
            "",
            "Executables (*.exe);;All files (*)",
        )
        if not file_path:
            return
        installation = validate_tesseract_executable(file_path)
        if installation is None:
            QMessageBox.warning(
                self,
                "Invalid Tesseract selection",
                "The selected executable is not a validated Tesseract installation with "
                "a complete tessdata root (configs/hocr required).",
            )
            return
        self._settings.setValue(TESSERACT_PROFILE_MODE_SETTING, "manual")
        self._settings.setValue(TESSERACT_PROFILE_PATH_SETTING, str(installation.executable))
        self._settings.sync()
        self.refresh_tesseract_runtime()

    def _reset_tesseract_profile(self) -> None:
        self._settings.setValue(TESSERACT_PROFILE_MODE_SETTING, "automatic")
        self._settings.remove(TESSERACT_PROFILE_PATH_SETTING)
        self._settings.sync()
        self.refresh_tesseract_runtime()

    def _save_selected_languages(self) -> None:
        selected = tuple(
            item.text()
            for item in self.tesseract_languages_list.selectedItems()
            if item.text() in self._active_tesseract_languages
        )
        save_language_selection(selected or ("eng",), self._settings)

    def set_output_directory(self, path: Path) -> None:
        super().set_output_directory(path)
        if hasattr(self, "open_output_button"):
            self._update_open_output_button()

    def refresh_output_availability(self) -> None:
        self.apply_output_availability(self._availability_provider())
        pypdf = check_pypdf()
        self._set_fast_markdown_availability(
            pypdf.available,
            pypdf.error or "Fast Markdown requires pypdf support.",
        )

    def apply_output_availability(self, availability: OutputAvailability) -> None:
        self._docling_controls_allowed = availability.docling
        self.searchable_pdf_checkbox.setEnabled(availability.searchable_pdf)
        if not availability.searchable_pdf:
            self.searchable_pdf_checkbox.setChecked(False)
            self.searchable_pdf_checkbox.setToolTip(
                "Searchable PDF requires OCRmyPDF and Tesseract OCR. "
                "Ghostscript is optional/recommended for PDF/A and advanced post-processing."
            )
        else:
            self.searchable_pdf_checkbox.setToolTip("")

        for checkbox in (self.markdown_checkbox, self.json_checkbox):
            checkbox.setEnabled(availability.docling)
            if not availability.docling:
                checkbox.setChecked(False)
                checkbox.setToolTip(
                    availability.docling_reason
                    or "Markdown and JSON require Docling and downloaded local models."
                )
            else:
                checkbox.setToolTip("")

        for checkbox in (
            self.docling_ocr_checkbox,
            self.table_structure_checkbox,
            self.cpu_only_checkbox,
        ):
            checkbox.setEnabled(availability.docling)
        self._update_table_analysis_availability()
        self._update_advanced_relevance()
        self.update_process_button()

    def apply_diagnostics(self, diagnostics: SystemDiagnostics) -> None:
        ocrmypdf = diagnostics.component("ocrmypdf")
        tesseract = diagnostics.component("tesseract")
        docling = diagnostics.component("docling")
        model_state = self._model_state_provider()
        reason = None
        if not docling.available:
            reason = "Docling is not installed. Open Help > System Check for setup guidance."
        elif not model_state.ready:
            reason = (
                "Local Docling models are not ready. "
                "Open Help > System Check and download models."
            )
        self.apply_output_availability(
            OutputAvailability(
                searchable_pdf=ocrmypdf.available and tesseract.available,
                docling=docling.available and model_state.ready,
                docling_reason=reason,
            )
        )
        try:
            pypdf = diagnostics.component("pypdf")
        except KeyError:
            self._set_fast_markdown_availability(True, "")
        else:
            self._set_fast_markdown_availability(
                pypdf.available,
                pypdf.error or "Fast Markdown requires pypdf support.",
            )

    def show_system_check(self) -> None:
        dialog = SystemCheckDialog(self, settings=self._settings)
        dialog.diagnostics_updated.connect(self.apply_diagnostics)
        dialog.exec()
        self.refresh_output_availability()
        self.refresh_tesseract_runtime()

    def _show_help_dialog(self, title: str, body: str) -> None:
        dialog = HelpDialog(HelpSection(title=title, body=body), self)
        dialog.exec()

    def show_getting_started(self) -> None:
        self._show_help_dialog(GETTING_STARTED.title, GETTING_STARTED.body)

    def show_settings_guide(self) -> None:
        self._show_help_dialog(SETTINGS_GUIDE.title, SETTINGS_GUIDE.body)

    def show_about(self) -> None:
        self._show_help_dialog(ABOUT.title, ABOUT.body)

    def show_queue_item_details(self, item: QListWidgetItem) -> None:
        if not item.text().startswith("Failed:"):
            return
        detail = item.toolTip().strip()
        if not detail:
            return
        ErrorDetailsDialog(detail, self).exec()

    def start_processing(self) -> None:
        if self.searchable_pdf_checkbox.isChecked() and self._pdf_paths and self.output_directory is not None:
            profile = resolve_tesseract_profile(
                self._settings,
                installations=self._tesseract_installations,
            )
            if profile is None:
                QMessageBox.critical(
                    self,
                    "Tesseract OCR unavailable",
                    "No validated Tesseract installation is available. Open Help > System Check "
                    "and run dependency setup or select a valid installation.",
                )
                return
            selected_languages = load_language_selection(self._settings)
            missing = [lang for lang in selected_languages if lang not in profile.installation.languages]
            if missing:
                QMessageBox.critical(
                    self,
                    "Selected OCR language unavailable",
                    "The active Tesseract installation does not provide: "
                    + ", ".join(missing)
                    + ". Select available languages before processing.",
                )
                return
        self._processing_stage = "Preparing"
        self._processing_file = ""
        self._processing_clock.start()
        self._processing_timer.start()
        super().start_processing()
        if not self._processing:
            self._processing_timer.stop()
            self._processing_clock.invalidate()
            return
        if self._worker is not None:
            self._worker.stage_changed.connect(self._on_processing_stage_changed)

    def _create_processing_worker(
        self,
        *,
        create_searchable_pdf: bool,
        create_markdown: bool,
        create_json: bool,
        executable: str | None,
    ) -> ProcessingWorker:
        if self.output_directory is None:
            raise RuntimeError("Output directory is required before starting processing.")
        profile = resolve_tesseract_profile(
            self._settings,
            installations=self._tesseract_installations,
        )
        selected_languages = load_language_selection(self._settings)
        ocr_workers, parser_threads, inference_threads = self._thread_profile_values()
        analysis_mode = str(self.ai_analysis_mode_combo.currentData() or "auto")
        if self.table_structure_checkbox.isChecked() and analysis_mode in {"auto", "accurate"}:
            analysis_mode = "accurate_tables"
        device = "cpu" if self.cpu_only_checkbox.isChecked() else "auto"
        return ProcessingWorker(
            tuple(self._pdf_paths),
            self.output_directory,
            create_searchable_pdf=create_searchable_pdf,
            create_markdown=create_markdown,
            create_json=create_json,
            language="+".join(selected_languages),
            executable=executable,
            tesseract_profile=profile,
            ocr_mode=str(self.ocr_mode_combo.currentData() or "smart"),
            analysis_mode=analysis_mode,
            docling_ocr=self.docling_ocr_checkbox.isChecked(),
            docling_device=device,
            ocr_workers=ocr_workers,
            parser_threads=parser_threads,
            inference_threads=inference_threads,
        )

    def _thread_profile_values(self) -> tuple[int, int, int]:
        cpu_count = _cpu_thread_count()
        profile = str(self.processing_profile_combo.currentData() or "balanced")
        if profile == "max_speed":
            ocr_workers = max(2, min(8, cpu_count - 1))
            parser_threads = max(2, min(6, cpu_count // 2 or 2))
            inference_threads = max(2, min(6, cpu_count // 2 or 2))
            return ocr_workers, parser_threads, inference_threads
        if profile == "energy_saver":
            return 2, 2, 1
        ocr_workers = max(2, min(4, cpu_count // 2 or 2))
        parser_threads = max(2, min(4, cpu_count // 3 or 2))
        inference_threads = max(2, min(4, cpu_count // 3 or 2))
        return ocr_workers, parser_threads, inference_threads

    def open_output_directory(self) -> None:
        output_directory = self.output_directory
        if output_directory is None or not output_directory.is_dir():
            QMessageBox.warning(
                self,
                "Output folder unavailable",
                "The output folder does not exist yet.",
            )
            self._update_open_output_button()
            return

        opened = QDesktopServices.openUrl(QUrl.fromLocalFile(str(output_directory)))
        if not opened:
            QMessageBox.warning(
                self,
                "Could not open folder",
                "The operating system could not open the output folder.",
            )

    def _on_file_started(self, index: int, total: int, name: str) -> None:
        super()._on_file_started(index, total, name)
        self._processing_file = f"{index}/{total}: {name}"
        if self.searchable_pdf_checkbox.isChecked():
            self._processing_stage = "Running OCRmyPDF"
        else:
            self._processing_stage = "Loading models and analyzing pages"
        self.progress_bar.setRange(0, 0)
        self._refresh_processing_text()

    def _set_fast_markdown_availability(self, enabled: bool, reason: str) -> None:
        index = self.ai_analysis_mode_combo.findData("fast")
        if index < 0:
            return
        model = self.ai_analysis_mode_combo.model()
        item = model.item(index) if hasattr(model, "item") else None
        if item is not None:
            item.setEnabled(enabled)
        if enabled:
            self.ai_analysis_mode_combo.setToolTip(
                "Auto picks a mode based on source content. "
                "Fast is quickest plain-text markdown. Accurate preserves richer layout."
            )
            return
        if self.ai_analysis_mode_combo.currentData() == "fast":
            self.ai_analysis_mode_combo.setCurrentIndex(
                max(0, self.ai_analysis_mode_combo.findData("auto"))
            )
        self.ai_analysis_mode_combo.setToolTip(
            "Fast Markdown unavailable: "
            + reason
            + " Use Auto or Accurate Markdown."
        )

    def _on_processing_stage_changed(self, stage: str) -> None:
        self._processing_stage = stage
        self._refresh_processing_text()

    def _refresh_processing_text(self) -> None:
        if not self._processing_clock.isValid():
            return
        elapsed = format_elapsed(self._processing_clock.elapsed())
        parts = [self._processing_stage]
        if self._processing_file:
            parts.append(self._processing_file)
        parts.append(elapsed)
        self.progress_bar.setFormat(" — ".join(parts))

    def _on_file_succeeded(self, input_path: str, output_files: object) -> None:
        self.progress_bar.setRange(0, max(1, len(self._pdf_paths)))
        super()._on_file_succeeded(input_path, output_files)

    def _on_file_failed(self, input_path: str, error: str) -> None:
        self.progress_bar.setRange(0, max(1, len(self._pdf_paths)))
        super()._on_file_failed(input_path, error)

    def _on_processing_finished(self, cancelled: bool, succeeded: int, failed: int) -> None:
        self._processing_timer.stop()
        self.progress_bar.setRange(0, max(1, len(self._pdf_paths)))
        super()._on_processing_finished(cancelled, succeeded, failed)
        self._processing_clock.invalidate()
        self._update_open_output_button()

    def _update_open_output_button(self) -> None:
        output_directory = self.output_directory
        self.open_output_button.setEnabled(
            output_directory is not None and output_directory.is_dir()
        )
