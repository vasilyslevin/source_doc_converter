#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
OUTPUT_DIR="${OUTPUT_DIR:-$REPO_ROOT/build/macos}"
ARCH="${ARCH:-$(uname -m)}"
MIN_MACOS_VERSION="${MIN_MACOS_VERSION:-12.0}"
PYTHON_BIN="${PYTHON_BIN:-python}"
APP_NAME="Source Document Converter.app"
EXECUTABLE_NAME="SourceDocumentConverter"
DIST_DIR="$OUTPUT_DIR/dist"
WORK_DIR="$OUTPUT_DIR/work"
SPEC_DIR="$OUTPUT_DIR/spec"
ICON_PATH="$OUTPUT_DIR/SourceDocumentConverter.icns"
ICON_SOURCE="$REPO_ROOT/src/source_doc_converter/assets/app_icon.svg"
GUI_ENTRY="$SCRIPT_DIR/SourceDocumentConverter.py"
PACKAGE_NOTES="$SCRIPT_DIR/PACKAGING_NOTES.txt"
PYPROJECT_PATH="$REPO_ROOT/pyproject.toml"
TORCHVISION_RUNTIME_HOOK="$REPO_ROOT/packaging/windows/pyi_rth_torchvision.py"

case "$ARCH" in
  arm64) ;;
  aarch64) ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH" >&2; exit 2 ;;
esac

HOST_ARCH="$(uname -m)"
case "$HOST_ARCH" in
  arm64|aarch64) ;;
  *)
    echo "Apple Silicon runner is required; current host architecture is $HOST_ARCH" >&2
    exit 2
    ;;
esac

rm -rf "$OUTPUT_DIR"
mkdir -p "$DIST_DIR" "$WORK_DIR" "$SPEC_DIR"

PROJECT_VERSION="$("$PYTHON_BIN" -c '
import pathlib
import sys
import tomllib

path = pathlib.Path(sys.argv[1])
try:
    data = tomllib.loads(path.read_text(encoding="utf-8"))
except FileNotFoundError:
    raise SystemExit(f"pyproject.toml was not found: {path}")
except OSError as error:
    raise SystemExit(f"Unable to read pyproject.toml at {path}: {error}")
except tomllib.TOMLDecodeError as error:
    raise SystemExit(f"Invalid TOML in {path}: {error}")

project = data.get("project")
if not isinstance(project, dict):
    raise SystemExit(f"Missing [project] table in {path}")
version = project.get("version")
if not isinstance(version, str) or not version.strip():
    raise SystemExit(f"Missing or empty project.version in {path}")
print(version.strip())
' "$PYPROJECT_PATH")"

SCIPY_ARRAY_API_NAMESPACE="$("$PYTHON_BIN" -c '
import importlib
from scipy import ndimage

array_api_namespaces = (
    "scipy._external.array_api_compat",
    "scipy._lib.array_api_compat",
)
detected_namespace = None
for namespace in array_api_namespaces:
    try:
        importlib.import_module(f"{namespace}.numpy.fft")
    except ModuleNotFoundError:
        continue
    detected_namespace = namespace
    break

if detected_namespace is None:
    raise SystemExit(
        "SciPy array API compatibility module is unavailable "
        "(expected scipy._external.array_api_compat.numpy.fft or scipy._lib.array_api_compat.numpy.fft)."
    )

result = ndimage.gaussian_filter1d([1.0, 2.0, 3.0], sigma=0.1)
if len(result) != 3:
    raise SystemExit("SciPy ndimage pre-freeze check produced an unexpected result.")

print(detected_namespace)
')"
if [[ -z "$SCIPY_ARRAY_API_NAMESPACE" ]]; then
  echo "Could not detect SciPy array API compatibility namespace." >&2
  exit 1
fi

TORCHVISION_INFO_JSON="$("$PYTHON_BIN" -c '
import importlib.metadata
import importlib.util
import json
import subprocess
from pathlib import Path

from packaging.requirements import Requirement
from packaging.version import Version
import torch
import torchvision

torch_version = Version(torch.__version__.split("+", 1)[0])
torchvision_version = Version(torchvision.__version__.split("+", 1)[0])
requires_dist = importlib.metadata.metadata("torchvision").get_all("Requires-Dist") or []
torch_requirement = None
for item in requires_dist:
    requirement = Requirement(item)
    if requirement.name.lower() == "torch":
        torch_requirement = requirement
        break
if torch_requirement is None:
    raise SystemExit("torchvision metadata does not declare a torch dependency.")
if not torch_requirement.specifier.contains(str(torch_version), prereleases=True):
    raise SystemExit(
        f"Incompatible torch/torchvision pair: torch {torch.__version__} does not satisfy {torch_requirement.specifier}."
    )

spec = importlib.util.find_spec("torchvision")
if spec is None or spec.submodule_search_locations is None:
    raise SystemExit("torchvision package was not found")
torchvision_root = Path(next(iter(spec.submodule_search_locations)))
matches = sorted(torchvision_root.glob("_C*.so"))
if not matches:
    raise SystemExit("torchvision native extension _C.so was not found")
extension = matches[0]

architectures = subprocess.check_output(["lipo", "-archs", str(extension)], text=True).strip().split()
if "arm64" not in architectures:
    raise SystemExit(f"torchvision native extension does not include arm64: {extension}")

if not torchvision.extension._has_ops():
    raise SystemExit("Torchvision native operators are unavailable in this build environment.")
boxes = torch.tensor([[0.0, 0.0, 1.0, 1.0], [0.1, 0.1, 1.1, 1.1]])
scores = torch.tensor([0.9, 0.8])
if torchvision.ops.nms(boxes, scores, 0.5).numel() == 0:
    raise SystemExit("Torchvision NMS pre-freeze check returned no detections.")

torch_lib_dir = Path(torch.__file__).resolve().parent / "lib"
if not torch_lib_dir.is_dir():
    raise SystemExit(f"Torch library directory was not found: {torch_lib_dir}")
dylibs = sorted(torch_lib_dir.glob("*.dylib"))
if not dylibs:
    raise SystemExit(f"Torch library directory does not contain dylib files: {torch_lib_dir}")

print(
    json.dumps(
        {
            "torch_version": str(torch_version),
            "torchvision_version": str(torchvision_version),
            "torch_requirement": str(torch_requirement.specifier),
            "torchvision_extension": str(extension),
            "torchvision_root": str(torchvision_root),
            "torch_lib_dir": str(torch_lib_dir),
        }
    )
)
')"
if [[ -z "$TORCHVISION_INFO_JSON" ]]; then
  echo "Could not inspect the installed torch/torchvision runtime." >&2
  exit 1
fi
TORCHVISION_EXTENSION="$("$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.argv[1])["torchvision_extension"])' "$TORCHVISION_INFO_JSON")"
TORCH_LIB_DIRECTORY="$("$PYTHON_BIN" -c 'import json, sys; print(json.loads(sys.argv[1])["torch_lib_dir"])' "$TORCHVISION_INFO_JSON")"
if [[ ! -f "$TORCHVISION_EXTENSION" ]]; then
  echo "Could not locate the installed torchvision native extension: $TORCHVISION_EXTENSION" >&2
  exit 1
fi
if [[ ! -d "$TORCH_LIB_DIRECTORY" ]]; then
  echo "Could not locate the installed torch library directory: $TORCH_LIB_DIRECTORY" >&2
  exit 1
fi

"$PYTHON_BIN" "$SCRIPT_DIR/create_icns.py" "$ICON_SOURCE" "$ICON_PATH"

COMMON_ARGS=(
  -m PyInstaller
  --noconfirm
  --clean
  --onedir
  "--target-architecture=$ARCH"
  "--paths=$REPO_ROOT/src"
  "--distpath=$DIST_DIR"
  "--specpath=$SPEC_DIR"
  "--osx-bundle-identifier=com.source.document.converter"
)

DOCLING_ARGS=(
  --collect-all=docling
  --collect-all=docling_core
  --collect-all=docling_parse
  --collect-all=pypdf
  --collect-all=rapidocr
  --collect-all=transformers
  "--collect-submodules=$SCIPY_ARRAY_API_NAMESPACE.numpy"
  --collect-binaries=torch
  --collect-binaries=torchvision
  "--add-binary=$TORCHVISION_EXTENSION:torchvision"
  "--add-binary=$TORCH_LIB_DIRECTORY/*.dylib:torch/lib"
  "--runtime-hook=$TORCHVISION_RUNTIME_HOOK"
  --hidden-import=docling.cli.tools
  --hidden-import=docling.document_converter
)

"$PYTHON_BIN" "${COMMON_ARGS[@]}" "${DOCLING_ARGS[@]}" \
  "--workpath=$WORK_DIR/$EXECUTABLE_NAME" \
  "--name=$EXECUTABLE_NAME" \
  "--windowed" \
  "--icon=$ICON_PATH" \
  "--add-data=$REPO_ROOT/src/source_doc_converter/assets/app_icon.svg:source_doc_converter/assets" \
  "$GUI_ENTRY"

APP_DIR="$DIST_DIR/$EXECUTABLE_NAME.app"
if [[ ! -d "$APP_DIR" ]]; then
  echo "PyInstaller did not produce $EXECUTABLE_NAME.app" >&2
  exit 1
fi
RENAMED_APP_DIR="$DIST_DIR/$APP_NAME"
mv "$APP_DIR" "$RENAMED_APP_DIR"
APP_DIR="$RENAMED_APP_DIR"

PACKAGED_TORCHVISION_EXTENSIONS=()
while IFS= read -r -d '' EXTENSION; do
  PACKAGED_TORCHVISION_EXTENSIONS+=("$EXTENSION")
done < <(find "$APP_DIR" -type f -path '*/torchvision/_C*.so' -print0)
if [[ "${#PACKAGED_TORCHVISION_EXTENSIONS[@]}" -eq 0 ]]; then
  echo "Packaged torchvision native extension _C.so was not found." >&2
  exit 1
fi
for EXTENSION in "${PACKAGED_TORCHVISION_EXTENSIONS[@]}"; do
  EXT_ARCHS="$(lipo -archs "$EXTENSION" 2>/dev/null || true)"
  echo "$EXTENSION => $EXT_ARCHS"
  echo "$EXT_ARCHS" | grep -Eq '(^| )arm64( |$)' || {
    echo "Missing arm64 slice in packaged torchvision extension: $EXTENSION" >&2
    exit 1
  }
done

PACKAGED_TORCH_LIB_DIR="$(find "$APP_DIR" -type d \( -path '*/torch/lib' -o -path '*/_internal/torch/lib' \) -print | head -n 1)"
if [[ -z "$PACKAGED_TORCH_LIB_DIR" ]]; then
  echo "Packaged torch library directory was not found in torch/lib or _internal/torch/lib." >&2
  exit 1
fi
if ! find "$PACKAGED_TORCH_LIB_DIR" -maxdepth 1 -name '*.dylib' -type f | grep -q .; then
  echo "Packaged torch library directory does not contain dylib files: $PACKAGED_TORCH_LIB_DIR" >&2
  exit 1
fi

cp "$REPO_ROOT/LICENSE" "$APP_DIR/Contents/Resources/LICENSE"
cp "$REPO_ROOT/THIRD_PARTY_NOTICES.md" "$APP_DIR/Contents/Resources/THIRD_PARTY_NOTICES.md"
cp "$PACKAGE_NOTES" "$APP_DIR/Contents/Resources/PACKAGING_NOTES.txt"

PLIST="$APP_DIR/Contents/Info.plist"
set_or_add_plist() {
  local key="$1"
  local type="$2"
  local value="$3"
  /usr/libexec/PlistBuddy -c "Set :$key $value" "$PLIST" 2>/dev/null || \
    /usr/libexec/PlistBuddy -c "Add :$key $type $value" "$PLIST"
}

set_or_add_plist "CFBundleDisplayName" "string" "Source Document Converter"
set_or_add_plist "CFBundleName" "string" "Source Document Converter"
set_or_add_plist "CFBundleExecutable" "string" "$EXECUTABLE_NAME"
set_or_add_plist "CFBundleShortVersionString" "string" "$PROJECT_VERSION"
set_or_add_plist "CFBundleVersion" "string" "$PROJECT_VERSION"
set_or_add_plist "LSMinimumSystemVersion" "string" "$MIN_MACOS_VERSION"
/usr/libexec/PlistBuddy -c "Delete :LSArchitecturePriority" "$PLIST" 2>/dev/null || true
/usr/libexec/PlistBuddy -c "Add :LSArchitecturePriority array" "$PLIST"
/usr/libexec/PlistBuddy -c "Add :LSArchitecturePriority:0 string $ARCH" "$PLIST"

SIGN_TARGETS=()
while IFS= read -r -d '' TARGET; do
  SIGN_TARGETS+=("$TARGET")
done < <(find "$APP_DIR/Contents" -type f \( -perm -111 -o -name "*.dylib" -o -name "*.so" \) -print0)
for TARGET in "${SIGN_TARGETS[@]}"; do
  codesign --force --sign - "$TARGET"
done
codesign --force --sign - "$APP_DIR"
codesign --verify --deep --strict "$APP_DIR"

(
  cd "$DIST_DIR"
  ZIP_NAME="SourceDocumentConverter-macOS-$ARCH.zip"
  ditto -c -k --sequesterRsrc --keepParent "$APP_NAME" "$ZIP_NAME"
  shasum -a 256 "$ZIP_NAME" > "$ZIP_NAME.sha256"
)

if command -v hdiutil >/dev/null 2>&1; then
  DMG_NAME="SourceDocumentConverter-macOS-$ARCH.dmg"
  DMG_STAGE_DIR="$(mktemp -d "$DIST_DIR/dmg-stage.XXXXXX")"
  trap 'rm -rf "$DMG_STAGE_DIR"' EXIT
  ditto "$APP_DIR" "$DMG_STAGE_DIR/$APP_NAME"
  hdiutil create -volname "Source Document Converter ($ARCH)" \
    -srcfolder "$DMG_STAGE_DIR" \
    -ov -format UDZO "$DIST_DIR/$DMG_NAME"
  rm -rf "$DMG_STAGE_DIR"
  trap - EXIT
  shasum -a 256 "$DIST_DIR/$DMG_NAME" > "$DIST_DIR/$DMG_NAME.sha256"
fi

echo "Created macOS build at $APP_DIR"
