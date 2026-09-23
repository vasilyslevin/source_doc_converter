import os
import unicodedata
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event

from source_doc_converter.ocr_pipeline import OcrCancelledError, OcrError, OutputCollisionError

DEFAULT_BUNDLE_FILENAME = "combined_markdown.md"


def create_markdown_bundle(
    ordered_outputs: tuple[tuple[Path, Path], ...],
    destination: Path,
    *,
    cancel_event: Event | None = None,
) -> Path:
    if cancel_event is not None and cancel_event.is_set():
        raise OcrCancelledError("Processing cancelled before combined Markdown bundle.")
    if destination.exists():
        raise OutputCollisionError(
            f"Output already exists and will not be overwritten: {destination}"
        )

    sections: list[str] = []
    for source_pdf_path, markdown_path in ordered_outputs:
        if cancel_event is not None and cancel_event.is_set():
            raise OcrCancelledError("Processing cancelled during combined Markdown bundle.")
        if not markdown_path.is_file():
            raise OcrError(f"Expected Markdown output was not created: {markdown_path}")
        body = _normalize_newlines(markdown_path.read_text(encoding="utf-8", errors="strict")).strip(
            "\n"
        )
        heading = f"# Source: {_safe_source_label(source_pdf_path.name)}"
        sections.append(f"{heading}\n\n{body}" if body else f"{heading}\n")

    if not sections:
        raise OcrError("No Markdown outputs were available for combined bundling.")

    destination.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            errors="strict",
            dir=destination.parent,
            delete=False,
            newline="\n",
        ) as handle:
            content = "\n\n".join(sections) + "\n"
            handle.write(content)
            temp_path = Path(handle.name)
        if cancel_event is not None and cancel_event.is_set():
            raise OcrCancelledError("Processing cancelled during combined Markdown bundle.")
        if destination.exists():
            raise OutputCollisionError(
                f"Output already exists and will not be overwritten: {destination}"
            )
        os.replace(temp_path, destination)
        temp_path = None
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return destination


def _safe_source_label(filename: str) -> str:
    normalized = unicodedata.normalize("NFC", filename)
    cleaned = "".join(_replace_control(char) for char in normalized)
    compact = " ".join(cleaned.split())
    if not compact:
        compact = "source.pdf"
    return compact.replace("\\", "\\\\").replace("#", "\\#").replace("[", "\\[").replace("]", "\\]")


def _replace_control(char: str) -> str:
    category = unicodedata.category(char)
    if category.startswith("C"):
        return " "
    return char


def _normalize_newlines(content: str) -> str:
    return content.replace("\r\n", "\n").replace("\r", "\n")
