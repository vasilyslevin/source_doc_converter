import os
import re
import unicodedata
from hashlib import sha1
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import Event

from source_doc_converter.ocr_pipeline import (
    OcrCancelledError,
    OcrError,
    OutputCollisionError,
    OutputPathTooLongError,
)

DEFAULT_BUNDLE_STEM = "combined_markdown"
_MAX_BUNDLE_FILENAME_CHARS = 120
_MAX_BUNDLE_PATH_CHARS = 240
_WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def bundle_destination_for_inputs(
    input_paths: tuple[Path, ...],
    output_directory: Path,
) -> Path:
    return output_directory / bundle_filename_for_inputs(input_paths, output_directory)


def bundle_filename_for_inputs(
    input_paths: tuple[Path, ...],
    output_directory: Path | None = None,
) -> str:
    stem = _bundle_stem_for_inputs(input_paths)
    filename = f"{stem}.md"
    if _needs_shortened_bundle_name(filename, output_directory):
        return _shortened_bundle_filename(stem, len(input_paths), output_directory)
    return filename


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
        body = _read_markdown_body(markdown_path).strip("\n")
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


def _bundle_stem_for_inputs(input_paths: tuple[Path, ...]) -> str:
    if not input_paths:
        return DEFAULT_BUNDLE_STEM
    occurrences: dict[str, int] = {}
    tokens: list[str] = []
    for input_path in input_paths:
        token = _safe_bundle_token(input_path.stem) or "source"
        occurrences[token] = occurrences.get(token, 0) + 1
        count = occurrences[token]
        tokens.append(token if count == 1 else f"{token}_{count}")
    stem = "_".join(tokens)
    if len(tokens) == 1:
        return f"{stem}_bundle"
    return stem


def _safe_bundle_token(stem: str) -> str:
    normalized = unicodedata.normalize("NFC", stem)
    safe_chars: list[str] = []
    for char in normalized:
        if char.isascii() and (char.isalnum() or char in "._-"):
            safe_chars.append(char)
        else:
            safe_chars.append("_")
    token = re.sub(r"_+", "_", "".join(safe_chars)).strip(" ._-")
    if not token:
        return ""
    if token.upper() in _WINDOWS_RESERVED_NAMES:
        return f"file_{token}"
    return token


def _needs_shortened_bundle_name(filename: str, output_directory: Path | None) -> bool:
    if len(filename) > _MAX_BUNDLE_FILENAME_CHARS:
        return True
    if output_directory is None:
        return False
    return len(str(output_directory / filename)) > _MAX_BUNDLE_PATH_CHARS


def _shortened_bundle_filename(
    stem: str,
    source_count: int,
    output_directory: Path | None,
) -> str:
    digest = sha1(stem.encode("utf-8")).hexdigest()[:10]
    discriminator = f"{source_count}src_{digest}"
    minimum_filename = f"{discriminator}.md"
    available_name_chars = _MAX_BUNDLE_FILENAME_CHARS
    if output_directory is not None:
        available_name_chars = min(
            available_name_chars,
            _MAX_BUNDLE_PATH_CHARS
            - len(str(output_directory))
            - 1
        )
    if available_name_chars < len(minimum_filename):
        raise OutputPathTooLongError(
            "Output path is too long to create a safe combined Markdown bundle filename. "
            "Choose a shorter output folder."
        )

    prefix_budget = available_name_chars - len(minimum_filename)
    if prefix_budget < 2:
        return minimum_filename

    trimmed_stem = stem[: prefix_budget - 1].rstrip("._-")
    if not trimmed_stem:
        return minimum_filename
    return f"{trimmed_stem}_{discriminator}.md"


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
    return re.sub(r"\r\n?|\n", "\n", content)


def _read_markdown_body(markdown_path: Path) -> str:
    with markdown_path.open("r", encoding="utf-8", errors="strict", newline="") as handle:
        return _normalize_newlines(handle.read())
