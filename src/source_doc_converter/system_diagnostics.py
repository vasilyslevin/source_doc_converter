import importlib.metadata as importlib_metadata
import importlib.util as importlib_util
import platform
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass

from PySide6 import __version__ as PYSIDE_VERSION

from source_doc_converter import __version__
from source_doc_converter.model_management import load_model_directory
from source_doc_converter.ocr_runtime import (
    build_ocr_environment,
    discover_tesseract_installations,
    resolve_ghostscript_executable,
    resolve_ocrmypdf_executable,
    resolve_tesseract_executable,
    resolve_tesseract_profile,
)
from source_doc_converter.runtime_paths import find_executable, macos_finder_search_paths
from source_doc_converter.subprocess_utils import background_subprocess_kwargs


@dataclass(frozen=True)
class ComponentStatus:
    key: str
    label: str
    available: bool
    version: str | None = None
    details: tuple[str, ...] = ()
    error: str | None = None


@dataclass(frozen=True)
class OutputAvailability:
    searchable_pdf: bool
    docling: bool
    docling_reason: str | None = None


@dataclass(frozen=True)
class SystemDiagnostics:
    application_version: str
    operating_system: str
    operating_system_version: str
    architecture: str
    python_version: str
    pyside_version: str
    components: tuple[ComponentStatus, ...]

    def component(self, key: str) -> ComponentStatus:
        for component in self.components:
            if component.key == key:
                return component
        raise KeyError(key)

    def to_text(self) -> str:
        lines = [
            "Source Document Converter - System Check",
            f"Application: {self.application_version}",
            f"Operating system: {self.operating_system} {self.operating_system_version}",
            f"Architecture: {self.architecture}",
            f"Python: {self.python_version}",
            f"PySide6: {self.pyside_version}",
            "",
            "Components:",
        ]
        for component in self.components:
            state = "Available" if component.available else "Unavailable"
            version = f" ({component.version})" if component.version else ""
            lines.append(f"- {component.label}: {state}{version}")
            for detail in component.details:
                lines.append(f"  - {detail}")
            if component.error:
                lines.append(f"  - Error: {component.error}")
        return "\n".join(lines) + "\n"


def _run_command(
    command: list[str],
    *,
    timeout: float = 30.0,
    env: Mapping[str, str] | None = None,
) -> tuple[bool, str, str | None]:
    try:
        completed = subprocess.run(
            command,
            shell=False,
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=dict(env) if env is not None else None,
            **background_subprocess_kwargs(),
        )
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except OSError as error:
        return False, "", str(error)

    output = (completed.stdout or completed.stderr).strip()
    if completed.returncode != 0:
        return False, output, f"Command exited with status {completed.returncode}"
    return True, output, None


def _first_line(text: str) -> str | None:
    for line in text.splitlines():
        value = line.strip()
        if value:
            return value
    return None


def _python_package_available(package: str) -> bool:
    try:
        return importlib_util.find_spec(package) is not None
    except (ImportError, ValueError):
        return False


def check_output_availability() -> OutputAvailability:
    docling_installed = _python_package_available("docling")
    models_ready = load_model_directory().ready if docling_installed else False
    ghostscript_ready = resolve_ghostscript_executable() is not None
    reason = None
    if not docling_installed:
        reason = "Docling is not installed. Open Help > System Check for setup guidance."
    elif not models_ready:
        reason = "Local Docling models are not ready. Open Help > System Check and download models."
    return OutputAvailability(
        searchable_pdf=resolve_ocrmypdf_executable() is not None
        and resolve_tesseract_executable()[0] is not None
        and ghostscript_ready,
        docling=docling_installed and models_ready,
        docling_reason=reason,
    )


def check_ocrmypdf() -> ComponentStatus:
    executable = resolve_ocrmypdf_executable()
    if executable is None:
        return ComponentStatus("ocrmypdf", "OCRmyPDF", False, error="Executable not found")

    succeeded, output, error = _run_command([executable, "--version"])
    details = ("Required for searchable PDF output.",)
    if platform.system() == "Darwin":
        prefixes = tuple(str(path) for path in macos_finder_search_paths())
        if any(executable.startswith(f"{prefix}/") or executable == prefix for prefix in prefixes):
            details += ("Source: Homebrew",)
        else:
            details += ("Source: PATH/manual selection",)
    elif platform.system() == "Windows":
        details += ("Source: PATH/winget/manual selection",)
    return ComponentStatus(
        "ocrmypdf",
        "OCRmyPDF",
        succeeded,
        version=_first_line(output),
        details=details,
        error=error,
    )


def check_tesseract() -> ComponentStatus:
    installations = discover_tesseract_installations()
    profile = resolve_tesseract_profile(installations=installations)
    executable, source = resolve_tesseract_executable()
    if executable is None:
        return ComponentStatus(
            "tesseract",
            "Tesseract OCR",
            False,
            details=("Required for searchable PDF output.",),
            error="Executable not found",
        )

    succeeded, output, error = _run_command(
        [executable, "--version"],
        env=build_ocr_environment(profile),
    )
    if not succeeded:
        return ComponentStatus(
            "tesseract",
            "Tesseract OCR",
            False,
            version=_first_line(output),
            details=(f"Source: {source}",),
            error=error,
        )

    languages_ok, languages_output, languages_error = _run_command(
        [executable, "--list-langs"],
        env=build_ocr_environment(profile),
    )
    languages = ()
    if languages_ok:
        lines = [line.strip() for line in languages_output.splitlines() if line.strip()]
        languages = tuple(lines[1:] if lines and "available languages" in lines[0].lower() else lines)

    details_list = [f"Source: {source}"]
    details_list.insert(0, "Required for searchable PDF output.")
    if installations:
        details_list.append(f"Validated installs: {len(installations)}")
        details_list.append(
            "Installations: " + ", ".join(installation.label for installation in installations)
        )
    if languages:
        details_list.append(f"Languages: {', '.join(languages)}")
    return ComponentStatus(
        "tesseract",
        "Tesseract OCR",
        True,
        version=_first_line(output),
        details=tuple(details_list),
        error=languages_error,
    )


def check_ghostscript() -> ComponentStatus:
    executable = resolve_ghostscript_executable()
    if executable is None:
        return ComponentStatus("ghostscript", "Ghostscript", False, error="Executable not found")

    succeeded, output, error = _run_command([executable, "--version"])
    details = ("Required for searchable PDF output.",)
    if platform.system() == "Darwin":
        if any(
            executable == str(prefix) or executable.startswith(f"{prefix!s}/")
            for prefix in macos_finder_search_paths()
        ):
            details += ("Source: Homebrew",)
        else:
            details += ("Source: PATH/manual selection",)
    elif platform.system() == "Windows":
        details += ("Source: PATH/winget/manual selection",)
    return ComponentStatus(
        "ghostscript",
        "Ghostscript",
        succeeded,
        version=_first_line(output),
        details=details,
        error=error,
    )


def check_python_package(distribution: str, label: str) -> ComponentStatus:
    try:
        spec = importlib_util.find_spec(distribution)
    except (ImportError, ValueError) as error:
        return ComponentStatus(distribution, label, False, error=str(error))
    if spec is None:
        return ComponentStatus(distribution, label, False, error="Package not installed")

    try:
        version = importlib_metadata.version(distribution)
    except importlib_metadata.PackageNotFoundError:
        version = "Installed; version unavailable"
    return ComponentStatus(distribution, label, True, version=version)


def check_docling() -> ComponentStatus:
    return check_python_package("docling", "Docling")


def check_pypdf() -> ComponentStatus:
    return check_python_package("pypdf", "pypdf")


def check_homebrew() -> ComponentStatus:
    if platform.system() != "Darwin":
        return ComponentStatus("homebrew", "Homebrew", True, details=("Not required on this platform.",))
    executable = find_executable("brew", extra_directories=macos_finder_search_paths())
    if executable is None:
        return ComponentStatus(
            "homebrew",
            "Homebrew",
            False,
            details=("Required for guided OCR tool installation.",),
            error="Executable not found",
        )
    succeeded, output, error = _run_command([executable, "--version"])
    return ComponentStatus(
        "homebrew",
        "Homebrew",
        succeeded,
        version=_first_line(output),
        details=("Required for guided OCR tool installation.",),
        error=error,
    )


def installation_guidance(component: str, operating_system: str | None = None) -> str:
    system = operating_system or platform.system()
    if component == "docling":
        return 'Install the Docling extra: python -m pip install ".[docling]"'
    if component == "pypdf":
        return "Install pypdf: python -m pip install pypdf"
    if component == "ghostscript":
        if system == "Darwin":
            return "Install Ghostscript with Homebrew: brew install ghostscript"
        if system == "Windows":
            return "Install Ghostscript with winget: winget install -e --id ArtifexSoftware.GhostScript"
        return "Install Ghostscript using your Linux distribution package manager."
    if component == "homebrew" and system == "Darwin":
        return "Install Homebrew first: https://brew.sh/"
    if system == "Darwin":
        return "Install OCR tools with Homebrew: brew install ocrmypdf tesseract ghostscript"
    if system == "Windows":
        return "Install OCR tools with winget: winget install -e --id OCRmyPDF.OCRmyPDF UB-Mannheim.TesseractOCR ArtifexSoftware.GhostScript"
    return "Install OCRmyPDF and Tesseract using your Linux distribution package manager."


def collect_system_diagnostics() -> SystemDiagnostics:
    base_components = (
        check_ocrmypdf(),
        check_tesseract(),
        check_ghostscript(),
        check_pypdf(),
        check_docling(),
    )
    components = (
        (check_homebrew(),) + base_components
        if platform.system() == "Darwin"
        else base_components
    )
    return SystemDiagnostics(
        application_version=__version__,
        operating_system=platform.system(),
        operating_system_version=platform.release(),
        architecture=platform.machine(),
        python_version=platform.python_version(),
        pyside_version=PYSIDE_VERSION,
        components=components,
    )
