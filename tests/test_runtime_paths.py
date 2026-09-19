import os
from pathlib import Path

from source_doc_converter import runtime_paths


def test_macos_finder_search_paths_are_known_prefixes() -> None:
    paths = runtime_paths.macos_finder_search_paths(system="Darwin")

    assert tuple(path.as_posix() for path in paths) == runtime_paths.MACOS_FINDER_PATHS


def test_build_subprocess_path_dedupes_entries(tmp_path: Path) -> None:
    executable_directory = tmp_path / "app"
    existing_path = os.pathsep.join((str(executable_directory), str(tmp_path / "bin")))
    path = runtime_paths.build_subprocess_path(
        include_app_directory=executable_directory,
        environ={"PATH": existing_path},
        system="Linux",
    )

    assert path.split(os.pathsep)[0] == str(executable_directory)
    assert path.count(str(executable_directory)) == 1


def test_find_executable_uses_extra_directories(monkeypatch, tmp_path: Path) -> None:
    binary = tmp_path / "bin" / "tesseract"
    binary.parent.mkdir(parents=True)
    binary.write_text("", encoding="utf-8")
    monkeypatch.setattr(runtime_paths.shutil, "which", lambda name: None)

    resolved = runtime_paths.find_executable("tesseract", extra_directories=(binary.parent,))

    assert resolved == str(binary.resolve())
