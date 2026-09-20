import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from source_doc_converter.runtime_paths import packaged_resources_directory


@dataclass(frozen=True)
class BuildManifest:
    application_version: str
    package_flavor: str | None = None
    source_commit_sha: str | None = None


def _manifest_candidates() -> tuple[Path, ...]:
    candidates: list[Path] = []
    executable_root = Path(sys.executable).resolve().parent
    candidates.append(executable_root / "build_manifest.json")
    resources = packaged_resources_directory()
    if resources is not None:
        candidates.append(resources / "build_manifest.json")
    return tuple(candidates)


def load_build_manifest(default_version: str) -> BuildManifest:
    for candidate in _manifest_candidates():
        try:
            payload = json.loads(candidate.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        return BuildManifest(
            application_version=str(payload.get("application_version") or default_version),
            package_flavor=_clean_optional(payload.get("package_flavor")),
            source_commit_sha=_clean_optional(payload.get("source_commit_sha")),
        )

    return BuildManifest(
        application_version=default_version,
        package_flavor=_clean_optional(os.environ.get("SOURCE_DOC_CONVERTER_PACKAGE_FLAVOR")),
        source_commit_sha=_clean_optional(os.environ.get("SOURCE_DOC_CONVERTER_COMMIT_SHA")),
    )


def _clean_optional(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
