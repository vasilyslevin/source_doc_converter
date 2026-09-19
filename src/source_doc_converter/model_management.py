import os
import shutil
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings, QStandardPaths

from source_doc_converter.runtime_paths import packaged_resources_directory

MODEL_DIRECTORY_ENV = "SOURCE_DOC_CONVERTER_MODEL_DIR"
LEGACY_MODEL_DIRECTORY_ENV = "FILING_DOC_CONVERTER_MODEL_DIR"
MODEL_DIRECTORY_SETTING = "models/directory"
MODEL_READY_MARKER = ".source-doc-converter-models-ready"
LEGACY_MODEL_READY_MARKER = ".filing-doc-converter-models-ready"
PACKAGED_DOWNLOADER_NAMES = ("docling-tools.exe", "docling-tools")
INTERNAL_DOCLING_TOOLS_FLAG = "--internal-docling-tools"
EXPECTED_MODEL_DIRECTORIES = (
    "docling-project--docling-layout-heron",
    "docling-project--docling-layout-heron-onnx",
    "docling-project--docling-models",
    "docling-project--DocumentFigureClassifier-v2.5",
    "docling-project--CodeFormulaV2",
)


class ModelManagementError(RuntimeError):
    """Raised when local model setup cannot be completed safely."""


@dataclass(frozen=True)
class ModelDirectoryState:
    path: Path
    source: str
    ready: bool


def _normalise_path(path: str | Path) -> Path:
    return Path(path).expanduser().resolve()


def default_model_directory() -> Path:
    data_root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    if data_root:
        return _normalise_path(Path(data_root) / "SourceDocumentConverter" / "models")
    return _normalise_path(Path.home() / ".source_doc_converter" / "models")


def legacy_default_model_directory() -> Path:
    data_root = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.GenericDataLocation
    )
    if data_root:
        return _normalise_path(Path(data_root) / "FilingDocumentConverter" / "models")
    return _normalise_path(Path.home() / ".filing_doc_converter" / "models")


def load_model_directory(
    settings: QSettings | None = None,
    *,
    environ: Mapping[str, str] | None = None,
) -> ModelDirectoryState:
    environment = os.environ if environ is None else environ
    override = environment.get(MODEL_DIRECTORY_ENV, "").strip() or environment.get(
        LEGACY_MODEL_DIRECTORY_ENV, ""
    ).strip()
    if override:
        path = _normalise_path(override)
        return ModelDirectoryState(path, "environment", models_ready(path))

    active_settings = settings if settings is not None else QSettings()
    saved = str(active_settings.value(MODEL_DIRECTORY_SETTING, "")).strip()
    if saved:
        path = _normalise_path(saved)
        return ModelDirectoryState(path, "settings", models_ready(path))

    path = default_model_directory()
    return ModelDirectoryState(path, "default", models_ready(path))


def save_model_directory(path: str | Path, settings: QSettings | None = None) -> Path:
    directory = _normalise_path(path)
    active_settings = settings if settings is not None else QSettings()
    active_settings.setValue(MODEL_DIRECTORY_SETTING, str(directory))
    active_settings.sync()
    return directory


def reset_model_directory(settings: QSettings | None = None) -> Path:
    active_settings = settings if settings is not None else QSettings()
    active_settings.remove(MODEL_DIRECTORY_SETTING)
    active_settings.sync()
    return default_model_directory()


def _directory_contains_files(directory: Path) -> bool:
    return directory.is_dir() and any(item.is_file() for item in directory.rglob("*"))


def downloaded_models_complete(path: str | Path) -> bool:
    directory = _normalise_path(path)
    return all(
        _directory_contains_files(directory / relative)
        for relative in EXPECTED_MODEL_DIRECTORIES
    )


def models_ready(path: str | Path) -> bool:
    directory = _normalise_path(path)
    marker_candidates = (
        directory / MODEL_READY_MARKER,
        directory / LEGACY_MODEL_READY_MARKER,
    )
    marker_ready = any(
        marker.is_file() and any(item.is_file() and item != marker for item in directory.rglob("*"))
        for marker in marker_candidates
    )
    return marker_ready or downloaded_models_complete(directory)


def mark_models_ready(path: str | Path) -> Path:
    directory = _normalise_path(path)
    marker = directory / MODEL_READY_MARKER
    has_model_files = directory.is_dir() and any(
        item.is_file() and item != marker for item in directory.rglob("*")
    )
    if not has_model_files:
        raise ModelManagementError("No downloaded model files were found.")
    marker.write_text("ready\n", encoding="utf-8", newline="\n")
    return marker


def is_packaged_application() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def resolve_model_downloader() -> list[str]:
    if is_packaged_application():
        if sys.platform == "darwin":
            return [str(Path(sys.executable).resolve()), INTERNAL_DOCLING_TOOLS_FLAG]
        executable_directory = Path(sys.executable).resolve().parent
        candidates = [executable_directory]
        resources = packaged_resources_directory()
        if resources is not None:
            candidates.append(resources)
        for directory in candidates:
            for name in PACKAGED_DOWNLOADER_NAMES:
                companion = directory / name
                if companion.is_file():
                    return [str(companion.resolve())]
        raise ModelManagementError(
            "The packaged docling-tools companion is missing. Reinstall or replace the "
            "application folder before downloading models."
        )

    executable = shutil.which("docling-tools")
    if executable:
        return [executable]
    raise ModelManagementError(
        "docling-tools was not found. Install the Docling optional dependencies and try again."
    )


def build_model_download_command(
    path: str | Path,
    *,
    command_prefix: list[str] | tuple[str, ...] | None = None,
) -> list[str]:
    resolved_prefix = list(command_prefix) if command_prefix is not None else resolve_model_downloader()
    if not resolved_prefix:
        raise ModelManagementError("docling-tools command prefix is empty.")
    return [
        *resolved_prefix,
        "models",
        "download",
        "-o",
        str(_normalise_path(path)),
    ]
