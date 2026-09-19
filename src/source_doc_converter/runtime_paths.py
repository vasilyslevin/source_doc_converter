import os
import platform
import shutil
import sys
from pathlib import Path

MACOS_FINDER_PATHS = (
    "/opt/homebrew/bin",
    "/opt/homebrew/sbin",
    "/usr/local/bin",
    "/usr/local/sbin",
)


def is_packaged_application() -> bool:
    return bool(getattr(sys, "frozen", False) or "__compiled__" in globals())


def _dedupe_paths(paths: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for entry in paths:
        value = entry.strip()
        if not value:
            continue
        key = value.casefold() if os.name == "nt" else value
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def packaged_contents_directory(executable: str | Path | None = None) -> Path | None:
    if not is_packaged_application():
        return None
    candidate = Path(executable if executable is not None else sys.executable).resolve()
    parent = candidate.parent
    if parent.name == "MacOS" and parent.parent.name == "Contents":
        return parent.parent
    return None


def packaged_resources_directory(executable: str | Path | None = None) -> Path | None:
    contents = packaged_contents_directory(executable)
    if contents is not None:
        resources = contents / "Resources"
        if resources.is_dir():
            return resources
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        path = Path(meipass).resolve()
        if path.is_dir():
            return path
    return None


def macos_finder_search_paths(*, system: str | None = None) -> tuple[Path, ...]:
    active_system = system or platform.system()
    if active_system != "Darwin":
        return ()
    return tuple(Path(path) for path in MACOS_FINDER_PATHS)


def build_subprocess_path(
    *,
    include_app_directory: Path | None = None,
    environ: dict[str, str] | None = None,
    system: str | None = None,
) -> str:
    base = os.environ if environ is None else environ
    entries = []
    if include_app_directory is not None:
        entries.append(str(include_app_directory))
    entries.extend(str(path) for path in macos_finder_search_paths(system=system))
    entries.extend(base.get("PATH", "").split(os.pathsep))
    return os.pathsep.join(_dedupe_paths(entries))


def find_executable(
    name: str,
    *,
    extra_directories: tuple[Path, ...] = (),
) -> str | None:
    resolved = shutil.which(name)
    if resolved:
        return resolved
    for directory in extra_directories:
        candidate = directory / name
        if candidate.is_file():
            return str(candidate.resolve())
    return None
