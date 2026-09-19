import os
import platform
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QSettings

from source_doc_converter.model_management import is_packaged_application
from source_doc_converter.runtime_paths import (
    find_executable,
    macos_finder_search_paths,
    packaged_contents_directory,
    packaged_resources_directory,
)
from source_doc_converter.subprocess_utils import background_subprocess_kwargs

TESSERACT_PROFILE_MODE_SETTING = "ocr/tesseract_profile_mode"
TESSERACT_PROFILE_PATH_SETTING = "ocr/tesseract_profile_path"
TESSERACT_LANGUAGES_SETTING = "ocr/tesseract_languages"
OCRMYPDF_PATH_SETTING = "ocr/ocrmypdf_path"
GHOSTSCRIPT_PATH_SETTING = "ocr/ghostscript_path"


@dataclass(frozen=True)
class BundledTesseract:
    root: Path
    executable: Path
    tessdata: Path


@dataclass(frozen=True)
class TesseractInstallation:
    label: str
    source: str
    executable: Path
    tessdata: Path
    languages: tuple[str, ...]

    @property
    def is_bundled(self) -> bool:
        return self.source == "bundled"


@dataclass(frozen=True)
class TesseractRuntimeProfile:
    installation: TesseractInstallation
    mode: str


def _candidate_bundle_roots() -> tuple[Path, ...]:
    roots: list[Path] = []
    executable_root = Path(sys.executable).resolve().parent
    roots.append(executable_root / "tools" / "tesseract")
    contents = packaged_contents_directory()
    if contents is not None:
        roots.append(contents / "Resources" / "tools" / "tesseract")
        roots.append(contents / "Frameworks" / "tools" / "tesseract")
    resources = packaged_resources_directory()
    if resources is not None:
        roots.append(resources / "tools" / "tesseract")
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass).resolve() / "tools" / "tesseract")
    return tuple(roots)


def _is_complete_tessdata_root(path: Path) -> bool:
    return path.is_dir() and (path / "configs" / "hocr").is_file()


def find_bundled_tesseract() -> BundledTesseract | None:
    if not is_packaged_application():
        return None
    for root in _candidate_bundle_roots():
        tessdata = root / "tessdata"
        if not _is_complete_tessdata_root(tessdata):
            continue
        for executable_name in ("tesseract.exe", "tesseract"):
            executable = root / executable_name
            if executable.is_file():
                return BundledTesseract(root=root, executable=executable, tessdata=tessdata)
    return None


def _manual_setting_path(settings: QSettings | None, key: str) -> Path | None:
    active = settings if settings is not None else QSettings()
    raw = str(active.value(key, "")).strip()
    if not raw:
        return None
    candidate = Path(raw).expanduser()
    if not candidate.is_file():
        return None
    return candidate.resolve()


def _windows_ocrmypdf_documented_paths() -> tuple[Path, ...]:
    roots: list[Path] = []
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.append(Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "ocrmypdf.exe")
        roots.append(Path(local_app_data) / "Programs" / "OCRmyPDF" / "ocrmypdf.exe")
    roots.append(Path("C:/Program Files/OCRmyPDF/ocrmypdf.exe"))
    return tuple(roots)


def resolve_ocrmypdf_executable(settings: QSettings | None = None) -> str | None:
    manual = _manual_setting_path(settings, OCRMYPDF_PATH_SETTING)
    if manual is not None:
        return str(manual)

    if is_packaged_application():
        executable_root = Path(sys.executable).resolve().parent
        for companion_name in ("ocrmypdf.exe", "ocrmypdf"):
            companion = executable_root / companion_name
            if companion.is_file():
                return str(companion)
        resources = packaged_resources_directory()
        if resources is not None:
            for companion_name in ("ocrmypdf.exe", "ocrmypdf"):
                companion = resources / companion_name
                if companion.is_file():
                    return str(companion)

    resolved = find_executable("ocrmypdf", extra_directories=macos_finder_search_paths())
    if resolved:
        return resolved

    if os.name == "nt":
        for candidate in _windows_ocrmypdf_documented_paths():
            if candidate.is_file():
                return str(candidate.resolve())
    return None


def _windows_ghostscript_documented_paths() -> tuple[Path, ...]:
    roots: list[Path] = []
    for executable_name in ("gswin64c.exe", "gswin32c.exe"):
        roots.extend(
            [
                Path("C:/Program Files/gs") / executable_name,
                Path("C:/Program Files (x86)/gs") / executable_name,
            ]
        )
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.extend(
            [
                Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "gswin64c.exe",
                Path(local_app_data) / "Microsoft" / "WinGet" / "Links" / "gswin32c.exe",
            ]
        )
    matches: list[Path] = []
    for root in roots:
        if root.name.lower().startswith("gswin") and root.parent.name.lower() == "gs":
            matches.extend(sorted(root.parent.glob(f"**/{root.name}")))
        else:
            matches.append(root)
    return tuple(matches)


def resolve_ghostscript_executable(settings: QSettings | None = None) -> str | None:
    manual = _manual_setting_path(settings, GHOSTSCRIPT_PATH_SETTING)
    if manual is not None:
        return str(manual)

    if os.name == "nt":
        for candidate_name in ("gswin64c", "gswin32c", "gs"):
            resolved = find_executable(candidate_name)
            if resolved:
                return resolved
        for candidate in _windows_ghostscript_documented_paths():
            if candidate.is_file():
                return str(candidate.resolve())
        return None

    return find_executable("gs", extra_directories=macos_finder_search_paths())


def _windows_documented_paths() -> tuple[Path, ...]:
    roots = [
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ]
    local_app_data = os.environ.get("LOCALAPPDATA", "").strip()
    if local_app_data:
        roots.append(Path(local_app_data) / "Programs" / "Tesseract-OCR" / "tesseract.exe")
    return tuple(roots)


def _candidate_system_executables() -> tuple[tuple[str, Path], ...]:
    candidates: list[tuple[str, Path]] = []
    if platform.system() == "Darwin":
        for prefix in macos_finder_search_paths():
            candidates.append(("homebrew", prefix / "tesseract"))
    path_exec = find_executable("tesseract", extra_directories=macos_finder_search_paths())
    if path_exec:
        source = "path"
        if platform.system() == "Darwin":
            resolved_path = Path(path_exec).resolve(strict=False)
            for prefix in macos_finder_search_paths():
                try:
                    resolved_path.relative_to(prefix.resolve(strict=False))
                    source = "homebrew"
                    break
                except ValueError:
                    continue
        candidates.append((source, Path(path_exec)))
    if os.name == "nt":
        for path in _windows_documented_paths():
            candidates.append(("known-location", path))
    deduped: list[tuple[str, Path]] = []
    seen: set[str] = set()
    for source, path in candidates:
        resolved = str(path.resolve(strict=False))
        if resolved.casefold() in seen:
            continue
        seen.add(resolved.casefold())
        deduped.append((source, path))
    return tuple(deduped)


def _infer_tessdata(executable: Path) -> Path | None:
    direct = executable.parent / "tessdata"
    if _is_complete_tessdata_root(direct):
        return direct
    share = executable.parent.parent / "share" / "tessdata"
    if _is_complete_tessdata_root(share):
        return share
    return None


def _list_languages(executable: Path, tessdata: Path) -> tuple[str, ...]:
    env = dict(os.environ)
    env["TESSDATA_PREFIX"] = str(tessdata)
    completed = subprocess.run(
        [str(executable), "--list-langs"],
        shell=False,
        check=False,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
        **background_subprocess_kwargs(),
    )
    if completed.returncode != 0:
        return ()
    output = (completed.stdout or completed.stderr or "").splitlines()
    lines = [line.strip() for line in output if line.strip()]
    if lines and "available languages" in lines[0].lower():
        lines = lines[1:]
    return tuple(lines)


def discover_tesseract_installations() -> tuple[TesseractInstallation, ...]:
    installations: list[TesseractInstallation] = []
    bundled = find_bundled_tesseract()
    if bundled is not None:
        languages = _list_languages(bundled.executable, bundled.tessdata)
        if languages:
            installations.append(
                TesseractInstallation(
                    label="Bundled Tesseract (recommended)",
                    source="bundled",
                    executable=bundled.executable,
                    tessdata=bundled.tessdata,
                    languages=languages,
                )
            )
    for source, executable in _candidate_system_executables():
        if not executable.is_file():
            continue
        tessdata = _infer_tessdata(executable)
        if tessdata is None:
            continue
        languages = _list_languages(executable, tessdata)
        if not languages:
            continue
        label = (
            f"System PATH ({executable})"
            if source == "path"
            else (
                f"Homebrew installation ({executable})"
                if source == "homebrew"
                else f"Windows installation ({executable})"
            )
        )
        installations.append(
            TesseractInstallation(
                label=label,
                source=source,
                executable=executable.resolve(),
                tessdata=tessdata.resolve(),
                languages=languages,
            )
        )
    return tuple(installations)


def validate_tesseract_executable(path: str | Path) -> TesseractInstallation | None:
    executable = Path(path).expanduser().resolve()
    if not executable.is_file():
        return None
    tessdata = _infer_tessdata(executable)
    if tessdata is None:
        return None
    languages = _list_languages(executable, tessdata)
    if not languages:
        return None
    return TesseractInstallation(
        label=f"Manual selection ({executable})",
        source="manual",
        executable=executable,
        tessdata=tessdata,
        languages=languages,
    )


def load_language_selection(settings: QSettings | None = None) -> tuple[str, ...]:
    active = settings if settings is not None else QSettings()
    raw = str(active.value(TESSERACT_LANGUAGES_SETTING, "eng")).strip()
    parts = [value.strip() for value in raw.replace(",", "+").split("+") if value.strip()]
    return tuple(dict.fromkeys(parts or ["eng"]))


def save_language_selection(languages: tuple[str, ...], settings: QSettings | None = None) -> None:
    active = settings if settings is not None else QSettings()
    serialized = "+".join(languages or ("eng",))
    active.setValue(TESSERACT_LANGUAGES_SETTING, serialized)
    active.sync()


def resolve_tesseract_profile(
    settings: QSettings | None = None,
    *,
    installations: tuple[TesseractInstallation, ...] | None = None,
) -> TesseractRuntimeProfile | None:
    candidates = installations if installations is not None else discover_tesseract_installations()
    active = settings if settings is not None else QSettings()
    mode = str(active.value(TESSERACT_PROFILE_MODE_SETTING, "automatic")).strip() or "automatic"
    explicit = str(active.value(TESSERACT_PROFILE_PATH_SETTING, "")).strip()
    if mode == "manual" and explicit:
        manual = validate_tesseract_executable(explicit)
        if manual is not None:
            return TesseractRuntimeProfile(manual, "manual")

    bundled = next((item for item in candidates if item.is_bundled), None)
    systems = tuple(item for item in candidates if not item.is_bundled)
    if mode == "bundled" and bundled is not None:
        return TesseractRuntimeProfile(bundled, "bundled")
    if mode == "system" and explicit:
        match = next(
            (
                item
                for item in systems
                if str(item.executable).casefold() == str(Path(explicit).resolve()).casefold()
            ),
            None,
        )
        if match is not None:
            return TesseractRuntimeProfile(match, "system")

    if bundled is not None:
        return TesseractRuntimeProfile(bundled, "automatic")
    if systems:
        return TesseractRuntimeProfile(systems[0], "automatic")
    return None


def resolve_tesseract_executable(
    settings: QSettings | None = None,
) -> tuple[str | None, str]:
    profile = resolve_tesseract_profile(settings)
    if profile is None:
        return None, "missing"
    return str(profile.installation.executable), profile.installation.source


def build_ocr_environment(
    profile: TesseractRuntimeProfile | None,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    base = dict(os.environ if environ is None else environ)
    if profile is None:
        return base

    executable_root = str(profile.installation.executable.parent)
    path_entries = base.get("PATH", "").split(os.pathsep) if base.get("PATH") else []
    normalized = {entry.casefold() for entry in path_entries}
    if executable_root.casefold() not in normalized:
        path_entries = [executable_root, *path_entries]
        base["PATH"] = os.pathsep.join(path_entries)

    tessdata = profile.installation.tessdata
    if _is_complete_tessdata_root(tessdata):
        base["TESSDATA_PREFIX"] = str(tessdata)
    return base
