import os
import subprocess
import sys
from pathlib import Path

import pytest

from source_doc_converter.macos_packaging import (
    build_macos_bundle_metadata,
    normalize_macos_architecture,
)


def test_architecture_aliases_are_normalized() -> None:
    assert normalize_macos_architecture("arm64") == "arm64"
    assert normalize_macos_architecture("aarch64") == "arm64"


def test_unsupported_architecture_is_rejected() -> None:
    with pytest.raises(ValueError, match="Unsupported macOS architecture"):
        normalize_macos_architecture("x86_64")


def test_bundle_metadata_uses_source_document_converter_identity() -> None:
    metadata = build_macos_bundle_metadata(version="0.1.0a0", architecture="arm64")

    assert metadata.bundle_name == "Source Document Converter"
    assert metadata.executable_name == "SourceDocumentConverter"
    assert metadata.bundle_identifier == "com.source.document.converter"


def test_pyproject_version_extraction_works_without_environment_variable(tmp_path: Path) -> None:
    pyproject = tmp_path / "pyproject.toml"
    pyproject.write_text(
        "[project]\nversion = \"0.2.0\"\n",
        encoding="utf-8",
    )
    extractor = """
import pathlib
import sys
import tomllib
path = pathlib.Path(sys.argv[1])
data = tomllib.loads(path.read_text(encoding="utf-8"))
project = data.get("project")
if not isinstance(project, dict):
    raise SystemExit(2)
version = project.get("version")
if not isinstance(version, str) or not version.strip():
    raise SystemExit(3)
print(version.strip())
"""
    env = dict(os.environ)
    env.pop("PYPROJECT_PATH", None)

    completed = subprocess.run(
        [sys.executable, "-c", extractor, str(pyproject)],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )

    assert completed.stdout.strip() == "0.2.0"


def test_macos_build_script_signs_nested_binaries_before_bundle() -> None:
    script = (Path(__file__).parents[1] / "packaging" / "macos" / "build.sh").read_text(
        encoding="utf-8"
    )

    assert 'find "$APP_DIR/Contents" -type f' in script
    assert 'codesign --force --sign - "$TARGET"' in script
    assert 'codesign --force --sign - "$APP_DIR"' in script
    assert 'codesign --force --deep --sign - "$APP_DIR"' not in script


def test_macos_workflow_uses_internal_docling_tools_smoke_commands() -> None:
    workflow = (
        Path(__file__).parents[1] / ".github" / "workflows" / "macos-package.yml"
    ).read_text(encoding="utf-8")

    assert '"$APP_EXEC" --internal-docling-tools --runtime-check' in workflow
    assert '"$APP_EXEC" --internal-docling-tools models download --help' in workflow
    assert '"$APP_EXEC" --docling-tools --runtime-check' not in workflow
