import multiprocessing
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from source_doc_converter.application_window import ApplicationWindow
from source_doc_converter.model_management import (
    INTERNAL_DOCLING_TOOLS_FLAG,
    is_packaged_application,
    resolve_model_downloader,
)
from source_doc_converter.privacy_notice import show_first_run_privacy_notice
from source_doc_converter.runtime_paths import (
    build_subprocess_path,
    packaged_resources_directory,
)
from source_doc_converter.settings_migration import (
    APPLICATION_NAME,
    ORGANIZATION_NAME,
    migrate_legacy_settings,
)

PACKAGE_SMOKE_TEST_FLAG = "--package-smoke-test"


def prepare_packaged_path() -> None:
    if not is_packaged_application():
        return
    executable_directory = Path(sys.executable).resolve().parent
    os.environ["PATH"] = build_subprocess_path(include_app_directory=executable_directory)


def _prepare_frozen_multiprocessing() -> None:
    multiprocessing.freeze_support()


def run_package_smoke_test() -> int:
    from pypdf import PdfReader, PdfWriter

    window = ApplicationWindow()
    window.close()
    downloader_command = resolve_model_downloader()
    if is_packaged_application() and sys.platform == "darwin":
        expected = [str(Path(sys.executable).resolve()), INTERNAL_DOCLING_TOOLS_FLAG]
        if downloader_command != expected:
            raise RuntimeError(
                "Packaged macOS model downloader command is misconfigured; "
                "expected internal docling-tools dispatch."
            )
    with TemporaryDirectory(prefix="sdc-package-smoke-") as directory:
        round_trip = Path(directory) / "pypdf-round-trip.pdf"
        writer = PdfWriter()
        writer.add_blank_page(width=72, height=72)
        with round_trip.open("wb") as handle:
            writer.write(handle)
        reader = PdfReader(str(round_trip))
        if len(reader.pages) != 1:
            raise RuntimeError("Packaged pypdf smoke test expected a one-page round-trip PDF.")
    _ = PdfReader
    return 0


def run_docling_tools_command(arguments: list[str]) -> int:
    from source_doc_converter import docling_tools_entry

    previous_argv = sys.argv
    try:
        sys.argv = ["docling-tools", *arguments]
        return docling_tools_entry.main()
    finally:
        sys.argv = previous_argv


def main() -> int:
    _prepare_frozen_multiprocessing()
    prepare_packaged_path()
    if INTERNAL_DOCLING_TOOLS_FLAG in sys.argv:
        index = sys.argv.index(INTERNAL_DOCLING_TOOLS_FLAG)
        return run_docling_tools_command(sys.argv[index + 1 :])
    smoke_test = PACKAGE_SMOKE_TEST_FLAG in sys.argv
    arguments = [argument for argument in sys.argv if argument != PACKAGE_SMOKE_TEST_FLAG]
    application = QApplication(arguments)
    application.setOrganizationName(ORGANIZATION_NAME)
    application.setApplicationName(APPLICATION_NAME)
    migrate_legacy_settings()
    resources_directory = packaged_resources_directory() or Path(__file__).parent
    icon_path = resources_directory / "source_doc_converter" / "assets" / "app_icon.svg"
    if not icon_path.is_file():
        icon_path = Path(__file__).parent / "assets" / "app_icon.svg"
    if icon_path.is_file():
        application.setWindowIcon(QIcon(str(icon_path)))
    if smoke_test:
        return run_package_smoke_test()

    window = ApplicationWindow()
    window.show()
    show_first_run_privacy_notice(window)
    return application.exec()


if __name__ == "__main__":
    raise SystemExit(main())
