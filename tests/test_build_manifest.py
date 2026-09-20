from pathlib import Path

from source_doc_converter import build_manifest


def test_load_build_manifest_from_packaged_file(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "SourceDocumentConverter.exe"
    executable.touch()
    manifest_path = tmp_path / "build_manifest.json"
    manifest_path.write_text(
        '{"application_version":"1.2.3","package_flavor":"Lite","source_commit_sha":"deadbeef"}',
        encoding="utf-8",
    )
    monkeypatch.setattr(build_manifest.sys, "executable", str(executable))
    monkeypatch.setattr(build_manifest, "packaged_resources_directory", lambda: None)

    loaded = build_manifest.load_build_manifest("0.0.0")

    assert loaded.application_version == "1.2.3"
    assert loaded.package_flavor == "Lite"
    assert loaded.source_commit_sha == "deadbeef"


def test_load_build_manifest_falls_back_to_env(monkeypatch, tmp_path: Path) -> None:
    executable = tmp_path / "SourceDocumentConverter.exe"
    executable.touch()
    monkeypatch.setattr(build_manifest.sys, "executable", str(executable))
    monkeypatch.setattr(build_manifest, "packaged_resources_directory", lambda: None)
    monkeypatch.setenv("SOURCE_DOC_CONVERTER_PACKAGE_FLAVOR", "Full")
    monkeypatch.setenv("SOURCE_DOC_CONVERTER_COMMIT_SHA", "abc123")

    loaded = build_manifest.load_build_manifest("0.0.0")

    assert loaded.application_version == "0.0.0"
    assert loaded.package_flavor == "Full"
    assert loaded.source_commit_sha == "abc123"
