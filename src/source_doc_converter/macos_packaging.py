from dataclasses import dataclass


@dataclass(frozen=True)
class MacOSBundleMetadata:
    bundle_identifier: str
    bundle_name: str
    executable_name: str
    minimum_system_version: str
    architecture: str
    short_version: str
    bundle_version: str


def normalize_macos_architecture(value: str) -> str:
    normalized = value.strip().lower()
    aliases = {
        "arm64": "arm64",
        "aarch64": "arm64",
    }
    if normalized not in aliases:
        raise ValueError(f"Unsupported macOS architecture: {value}")
    return aliases[normalized]


def build_macos_bundle_metadata(
    *,
    version: str,
    architecture: str,
    minimum_system_version: str = "12.0",
) -> MacOSBundleMetadata:
    normalized_arch = normalize_macos_architecture(architecture)
    return MacOSBundleMetadata(
        bundle_identifier="com.source.document.converter",
        bundle_name="Source Document Converter",
        executable_name="SourceDocumentConverter",
        minimum_system_version=minimum_system_version,
        architecture=normalized_arch,
        short_version=version,
        bundle_version=version,
    )
