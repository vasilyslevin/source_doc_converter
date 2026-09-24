import time
from pathlib import Path
from threading import Event

from PySide6.QtCore import QObject, Signal, Slot

from source_doc_converter.markdown_bundle import (
    bundle_destination_for_inputs,
    create_markdown_bundle,
)
from source_doc_converter.ocr_pipeline import (
    DoclingResult,
    OcrCancelledError,
    OcrError,
    run_docling,
    run_ocr,
)
from source_doc_converter.ocr_runtime import TesseractRuntimeProfile


class ProcessingWorker(QObject):
    file_started = Signal(int, int, str)
    stage_changed = Signal(str)
    file_succeeded = Signal(str, str)
    file_failed = Signal(str, str)
    finished = Signal(bool, int, int)

    def __init__(
        self,
        input_paths: tuple[Path, ...],
        output_directory: Path,
        *,
        create_searchable_pdf: bool,
        create_markdown: bool,
        create_json: bool,
        create_markdown_bundle: bool = False,
        language: str = "eng",
        executable: str | None = None,
        tesseract_profile: TesseractRuntimeProfile | None = None,
        ocr_mode: str = "smart",
        analysis_mode: str = "auto",
        docling_ocr: bool = False,
        docling_device: str = "cpu",
        ocr_workers: int = 2,
        parser_threads: int = 2,
        inference_threads: int = 2,
    ) -> None:
        super().__init__()
        self._input_paths = input_paths
        self._output_directory = output_directory
        self._create_searchable_pdf = create_searchable_pdf
        self._create_markdown = create_markdown
        self._create_json = create_json
        self._create_markdown_bundle = create_markdown_bundle
        self._language = language
        self._executable = executable
        self._tesseract_profile = tesseract_profile
        self._ocr_mode = ocr_mode
        self._analysis_mode = analysis_mode
        self._docling_ocr = docling_ocr
        self._docling_device = docling_device
        self._ocr_workers = max(1, ocr_workers)
        self._parser_threads = max(1, parser_threads)
        self._inference_threads = max(1, inference_threads)
        self._cancel_event = Event()

    @Slot()
    def run(self) -> None:
        succeeded = 0
        failed = 0
        cancelled = False
        total = len(self._input_paths)
        markdown_outputs: list[tuple[Path, Path]] = []
        omitted_markdown_sources: list[str] = []
        bundle_destination: Path | None = None
        if self._create_markdown and self._create_markdown_bundle:
            bundle_destination = bundle_destination_for_inputs(
                self._input_paths,
                self._output_directory,
            )
            if bundle_destination.exists():
                message = f"Output already exists and will not be overwritten: {bundle_destination}"
                self.stage_changed.emit("Combined Markdown bundle failed: " + message)
                for input_path in self._input_paths:
                    self.file_failed.emit(str(input_path), message)
                self.finished.emit(False, 0, total)
                return
        self.stage_changed.emit(
            "Runtime: "
            + f"OCR workers={self._ocr_workers}, "
            + f"parser threads={self._parser_threads}, "
            + f"inference threads={self._inference_threads}, "
            + f"device={self._docling_device}, "
            + f"analysis mode={self._analysis_mode}"
        )
        batch_started = time.monotonic()

        for index, input_path in enumerate(self._input_paths, start=1):
            if self._cancel_event.is_set():
                cancelled = True
                break

            self.file_started.emit(index, total, input_path.name)
            success_paths: list[str] = []
            file_started = time.monotonic()
            try:
                docling_input = input_path
                if self._create_searchable_pdf:
                    self.stage_changed.emit("Running OCRmyPDF")
                    ocr_result = run_ocr(
                        input_path,
                        self._output_directory,
                        language=self._language,
                        executable=self._executable,
                        tesseract_profile=self._tesseract_profile,
                        cancel_event=self._cancel_event,
                        mode=self._ocr_mode,
                        ocr_workers=self._ocr_workers,
                    )
                    self.stage_changed.emit(
                        f"OCR mode: {ocr_result.effective_mode.title()} OCR"
                    )
                    docling_input = ocr_result.output_path
                    success_paths.append(str(ocr_result.output_path))
                    for warning in ocr_result.warnings:
                        success_paths.append(f"Warning: {warning}")
                    self._append_timings(success_paths, ocr_result.timings)

                if self._create_markdown or self._create_json:
                    self.stage_changed.emit("Loading models and analyzing pages")
                    docling_result = run_docling(
                        docling_input,
                        self._output_directory,
                        export_markdown=self._create_markdown,
                        export_json=self._create_json,
                        output_stem=input_path.stem,
                        cancel_event=self._cancel_event,
                        analysis_mode=self._analysis_mode,
                        docling_ocr=self._docling_ocr,
                        device=self._docling_device,
                        parser_threads=self._parser_threads,
                        inference_threads=self._inference_threads,
                    )
                    self.stage_changed.emit(
                        f"AI analysis mode: {docling_result.effective_analysis_mode}"
                    )
                    self.stage_changed.emit("Finalizing Markdown/JSON outputs")
                    self._append_docling_outputs(success_paths, docling_result)
                    if self._create_markdown and docling_result.markdown_path is not None:
                        markdown_outputs.append((input_path, docling_result.markdown_path))
                    for warning in docling_result.warnings:
                        success_paths.append(f"Warning: {warning}")
                    self._append_timings(success_paths, docling_result.timings)
                success_paths.append(
                    f"Timing: Total per file {time.monotonic() - file_started:.2f}s"
                )
            except OcrCancelledError:
                cancelled = True
                break
            except OcrError as error:
                failed += 1
                if self._create_markdown and self._create_markdown_bundle:
                    omitted_markdown_sources.append(input_path.name)
                self.file_failed.emit(str(input_path), str(error))
            else:
                succeeded += 1
                self.file_succeeded.emit(str(input_path), "\n".join(success_paths))
        if (
            self._create_markdown
            and self._create_markdown_bundle
            and not cancelled
            and markdown_outputs
        ):
            self.stage_changed.emit("Creating combined Markdown bundle")
            if omitted_markdown_sources:
                unique = ", ".join(dict.fromkeys(omitted_markdown_sources))
                self.stage_changed.emit(
                    "Combined Markdown bundle will omit failed sources: " + unique
                )
            try:
                bundle_path = create_markdown_bundle(
                    tuple(markdown_outputs),
                    bundle_destination
                    or bundle_destination_for_inputs(self._input_paths, self._output_directory),
                    cancel_event=self._cancel_event,
                )
            except OcrCancelledError:
                cancelled = True
            except OcrError as error:
                self.stage_changed.emit(f"Combined Markdown bundle failed: {error}")
            else:
                self.stage_changed.emit(f"Combined Markdown bundle created: {bundle_path}")
        elif self._create_markdown and self._create_markdown_bundle and not cancelled:
            self.stage_changed.emit(
                "Combined Markdown bundle skipped: no Markdown outputs were created."
            )
        elapsed = time.monotonic() - batch_started
        self.stage_changed.emit(f"Timing: Total batch {elapsed:.2f}s")
        self.finished.emit(cancelled, succeeded, failed)

    def cancel(self) -> None:
        self._cancel_event.set()

    @staticmethod
    def _append_docling_outputs(outputs: list[str], result: DoclingResult) -> None:
        if result.markdown_path is not None:
            outputs.append(str(result.markdown_path))
        if result.json_path is not None:
            outputs.append(str(result.json_path))

    @staticmethod
    def _append_timings(outputs: list[str], timings: tuple[tuple[str, float], ...]) -> None:
        for name, seconds in timings:
            outputs.append(f"Timing: {name} {seconds:.2f}s")


OcrWorker = ProcessingWorker
