import importlib
import os
import sys
from pathlib import Path

_DLL_DIRECTORY_HANDLES = []


def _candidate_runtime_roots() -> list[Path]:
    roots: list[Path] = []
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        roots.append(Path(meipass))
    exe_dir = Path(sys.executable).resolve().parent
    roots.extend([exe_dir, exe_dir / "_internal"])
    if sys.platform == "darwin":
        roots.append(exe_dir.parent / "Frameworks")

    unique_roots: list[Path] = []
    seen = set()
    for root in roots:
        normalized = root.resolve(strict=False)
        if normalized not in seen:
            seen.add(normalized)
            unique_roots.append(normalized)
    return unique_roots


def _format_checked_directories(checked: list[Path], bundle_root: Path | None) -> str:
    formatted: list[str] = []
    for directory in checked:
        if bundle_root is not None:
            try:
                relative = directory.relative_to(bundle_root)
                formatted.append(f"<bundle>\\{relative}")
                continue
            except ValueError:
                pass
        formatted.append(f"<runtime>\\{directory.name}")
    return ", ".join(formatted)


def _load_torchvision_extension() -> None:
    import torch

    runtime_roots = _candidate_runtime_roots()
    bundle_root = runtime_roots[0] if runtime_roots else None
    extension_suffixes = ("_C*.pyd", "_C*.so")
    extension = None
    checked_directories: list[Path] = []
    for root in runtime_roots:
        candidate = root / "torchvision"
        checked_directories.append(candidate)
        matches = []
        for pattern in extension_suffixes:
            matches.extend(candidate.glob(pattern))
        matches = sorted(matches)
        if matches:
            extension = matches[0]
            break

    if extension is None:
        checked = _format_checked_directories(checked_directories, bundle_root)
        raise RuntimeError(
            "Packaged torchvision native extension _C.pyd was not found. "
            f"Checked: {checked}"
        )

    dll_directories = [extension.parent]
    for root in runtime_roots:
        torch_lib = root / "torch" / "lib"
        if torch_lib.is_dir():
            dll_directories.append(torch_lib)

    if sys.platform == "win32" and hasattr(os, "add_dll_directory"):
        for directory in dll_directories:
            _DLL_DIRECTORY_HANDLES.append(os.add_dll_directory(str(directory)))

    try:
        torch.ops.load_library(str(extension))
        importlib.import_module("torchvision")
    except Exception as error:
        checked = _format_checked_directories(dll_directories, bundle_root)
        raise RuntimeError(
            "Could not load packaged torchvision native extension. "
            f"DLL directories: {checked}"
        ) from error


_load_torchvision_extension()
