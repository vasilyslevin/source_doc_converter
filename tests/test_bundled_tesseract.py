import os
from pathlib import Path

from PySide6.QtCore import QSettings

from source_doc_converter import ocr_runtime
from source_doc_converter.ocr_runtime import (
    TESSERACT_PROFILE_MODE_SETTING,
    TESSERACT_PROFILE_PATH_SETTING,
    TesseractInstallation,
    TesseractRuntimeProfile,
)


def _complete_tessdata(root: Path) -> Path:
    tessdata = root / "tessdata" / "configs"
    tessdata.mkdir(parents=True)
    (tessdata / "hocr").write_text("", encoding="utf-8")
    return root / "tessdata"


def _installation(label: str, source: str, root: Path, exe_name: str = "tesseract.exe") -> TesseractInstallation:
    executable = root / exe_name
    executable.parent.mkdir(parents=True, exist_ok=True)
    executable.touch()
    tessdata = _complete_tessdata(root)
    return TesseractInstallation(
        label=label,
        source=source,
        executable=executable,
        tessdata=tessdata,
        languages=("eng", "spa"),
    )


def test_find_bundled_tesseract_requires_hocr_config(monkeypatch, tmp_path: Path) -> None:
    package_directory = tmp_path / "package"
    tesseract_directory = package_directory / "tools" / "tesseract"
    (tesseract_directory / "tessdata").mkdir(parents=True)
    (tesseract_directory / "tesseract.exe").touch()
    monkeypatch.setattr(ocr_runtime, "is_packaged_application", lambda: True)
    monkeypatch.setattr(ocr_runtime.sys, "executable", str(package_directory / "app.exe"))

    bundled = ocr_runtime.find_bundled_tesseract()

    assert bundled is None


def test_find_bundled_tesseract_prefers_packaged_folder(monkeypatch, tmp_path: Path) -> None:
    package_directory = tmp_path / "package"
    tesseract_directory = package_directory / "tools" / "tesseract"
    _complete_tessdata(tesseract_directory)
    (tesseract_directory / "tesseract.exe").touch()
    monkeypatch.setattr(ocr_runtime, "is_packaged_application", lambda: True)
    monkeypatch.setattr(ocr_runtime.sys, "executable", str(package_directory / "app.exe"))
    monkeypatch.setattr(ocr_runtime.sys, "_MEIPASS", str(tmp_path / "missing"), raising=False)

    bundled = ocr_runtime.find_bundled_tesseract()

    assert bundled is not None
    assert bundled.root == tesseract_directory
    assert bundled.executable == tesseract_directory / "tesseract.exe"


def test_build_ocr_environment_uses_profile_specific_values(tmp_path: Path) -> None:
    installation = _installation("System", "path", tmp_path / "system")
    profile = TesseractRuntimeProfile(installation, "automatic")

    env = ocr_runtime.build_ocr_environment(profile, {"PATH": str(tmp_path / "bin")})

    assert env["PATH"].split(os.pathsep)[0] == str(installation.executable.parent)
    assert env["TESSDATA_PREFIX"] == str(installation.tessdata)
    assert "TESSDATA_PREFIX" not in os.environ


def test_build_ocr_environment_does_not_set_incomplete_tessdata(tmp_path: Path) -> None:
    executable = tmp_path / "manual" / "tesseract.exe"
    executable.parent.mkdir(parents=True)
    executable.touch()
    tessdata = executable.parent / "tessdata"
    tessdata.mkdir(parents=True)
    installation = TesseractInstallation(
        label="Manual",
        source="manual",
        executable=executable,
        tessdata=tessdata,
        languages=("eng",),
    )
    profile = TesseractRuntimeProfile(installation, "manual")

    env = ocr_runtime.build_ocr_environment(profile, {"PATH": str(tmp_path / "bin"), "TESSDATA_PREFIX": "old"})

    assert env["TESSDATA_PREFIX"] == "old"


def test_resolve_profile_prefers_explicit_system_selection(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    bundled = _installation("Bundled", "bundled", tmp_path / "bundle")
    system = _installation("System", "path", tmp_path / "system", exe_name="tesseract")
    settings.setValue(TESSERACT_PROFILE_MODE_SETTING, "system")
    settings.setValue(TESSERACT_PROFILE_PATH_SETTING, str(system.executable))

    profile = ocr_runtime.resolve_tesseract_profile(settings, installations=(bundled, system))

    assert profile is not None
    assert profile.installation.executable == system.executable
    assert profile.installation.source == "path"


def test_resolve_profile_automatic_prefers_bundled_then_system(tmp_path: Path) -> None:
    settings = QSettings(str(tmp_path / "settings.ini"), QSettings.Format.IniFormat)
    bundled = _installation("Bundled", "bundled", tmp_path / "bundle")
    system = _installation("System", "path", tmp_path / "system", exe_name="tesseract")

    profile = ocr_runtime.resolve_tesseract_profile(settings, installations=(bundled, system))
    assert profile is not None
    assert profile.installation.source == "bundled"

    profile_without_bundle = ocr_runtime.resolve_tesseract_profile(settings, installations=(system,))
    assert profile_without_bundle is not None
    assert profile_without_bundle.installation.source == "path"


def test_resolve_ocrmypdf_prefers_packaged_companion(monkeypatch, tmp_path: Path) -> None:
    package_directory = tmp_path / "package"
    companion = package_directory / "ocrmypdf.exe"
    companion.parent.mkdir(parents=True, exist_ok=True)
    companion.touch()
    monkeypatch.setattr(ocr_runtime, "is_packaged_application", lambda: True)
    monkeypatch.setattr(ocr_runtime.sys, "executable", str(package_directory / "app.exe"))
    monkeypatch.setattr(ocr_runtime, "find_executable", lambda name, **kwargs: str(tmp_path / "system" / "ocrmypdf"))

    executable = ocr_runtime.resolve_ocrmypdf_executable()

    assert executable == str(companion)


def test_resolve_ocrmypdf_uses_macos_finder_paths_when_path_missing(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(ocr_runtime, "is_packaged_application", lambda: False)
    finder_paths = (
        Path("/opt/homebrew/bin"),
        Path("/opt/homebrew/sbin"),
        Path("/usr/local/bin"),
        Path("/usr/local/sbin"),
    )
    monkeypatch.setattr(ocr_runtime, "macos_finder_search_paths", lambda: finder_paths)

    def fake_find_executable(name: str, **kwargs) -> str | None:
        assert name == "ocrmypdf"
        assert kwargs["extra_directories"] == finder_paths
        return str(tmp_path / "brew" / "ocrmypdf")

    monkeypatch.setattr(ocr_runtime, "find_executable", fake_find_executable)

    executable = ocr_runtime.resolve_ocrmypdf_executable()

    assert executable == str(tmp_path / "brew" / "ocrmypdf")


def test_windows_documented_ocrmypdf_paths_include_uv_tool_bin(monkeypatch) -> None:
    monkeypatch.setenv("USERPROFILE", "C:/Users/tester")
    monkeypatch.setenv("LOCALAPPDATA", "C:/Users/tester/AppData/Local")

    paths = ocr_runtime._windows_ocrmypdf_documented_paths()

    assert any(str(path).endswith("Microsoft/WinGet/Links/ocrmypdf.exe") for path in paths)
    assert any(str(path).endswith(".local/bin/ocrmypdf.exe") for path in paths)


def test_candidate_system_executables_marks_homebrew_source(monkeypatch, tmp_path: Path) -> None:
    finder_paths = (tmp_path / "brew",)
    monkeypatch.setattr(ocr_runtime.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(ocr_runtime, "macos_finder_search_paths", lambda: finder_paths)
    monkeypatch.setattr(
        ocr_runtime,
        "find_executable",
        lambda name, **kwargs: str(finder_paths[0] / "tesseract"),
    )

    candidates = ocr_runtime._candidate_system_executables()

    assert candidates[0][0] == "homebrew"
