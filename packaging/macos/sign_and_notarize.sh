#!/usr/bin/env bash
set -euo pipefail

APP_PATH="${1:?app path required}"
ARCH="${2:?arch required}"
if [[ "$ARCH" != "arm64" ]]; then
  echo "Only Apple Silicon arm64 notarization artifacts are supported (received: $ARCH)." >&2
  exit 2
fi

required_vars=(MACOS_CERT_BASE64 MACOS_CERT_PASSWORD MACOS_SIGNING_IDENTITY APPLE_API_KEY_ID APPLE_API_ISSUER_ID APPLE_API_PRIVATE_KEY_BASE64)
missing=()
present=0
for key in "${required_vars[@]}"; do
  if [[ -n "${!key:-}" ]]; then
    present=$((present + 1))
  else
    missing+=("$key")
  fi
done

if [[ "$present" -eq 0 ]]; then
  echo "Skipping Developer ID signing/notarization: no signing secrets provided." >&2
  exit 0
fi

if [[ "${#missing[@]}" -gt 0 ]]; then
  echo "Signing/notarization configuration is incomplete; missing: ${missing[*]}" >&2
  exit 1
fi

KEYCHAIN_PATH="$RUNNER_TEMP/source-doc-converter-signing.keychain-db"
CERT_PATH="$RUNNER_TEMP/source-doc-converter-signing.p12"
API_KEY_PATH="$RUNNER_TEMP/AuthKey_${APPLE_API_KEY_ID}.p8"
PROFILE_NAME="SourceDocumentConverter-notarytool"

echo "$MACOS_CERT_BASE64" | base64 --decode > "$CERT_PATH"
echo "$APPLE_API_PRIVATE_KEY_BASE64" | base64 --decode > "$API_KEY_PATH"

security create-keychain -p "$MACOS_CERT_PASSWORD" "$KEYCHAIN_PATH"
security set-keychain-settings -lut 21600 "$KEYCHAIN_PATH"
security unlock-keychain -p "$MACOS_CERT_PASSWORD" "$KEYCHAIN_PATH"
security import "$CERT_PATH" -k "$KEYCHAIN_PATH" -P "$MACOS_CERT_PASSWORD" -T /usr/bin/codesign
security list-keychains -d user -s "$KEYCHAIN_PATH"

codesign --force --deep --options runtime --sign "$MACOS_SIGNING_IDENTITY" "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

NOTARIZE_ZIP_PATH="$(dirname "$APP_PATH")/SourceDocumentConverter-macOS-$ARCH-notarize.zip"
ZIP_PATH="$(dirname "$APP_PATH")/SourceDocumentConverter-macOS-$ARCH.zip"
ZIP_SHA_PATH="${ZIP_PATH}.sha256"
DMG_PATH="$(dirname "$APP_PATH")/SourceDocumentConverter-macOS-$ARCH.dmg"
DMG_SHA_PATH="${DMG_PATH}.sha256"
ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$NOTARIZE_ZIP_PATH"

xcrun notarytool store-credentials "$PROFILE_NAME" \
  --key "$API_KEY_PATH" \
  --key-id "$APPLE_API_KEY_ID" \
  --issuer "$APPLE_API_ISSUER_ID"

xcrun notarytool submit "$NOTARIZE_ZIP_PATH" --keychain-profile "$PROFILE_NAME" --wait
xcrun stapler staple "$APP_PATH"
codesign --verify --deep --strict "$APP_PATH"

ditto -c -k --sequesterRsrc --keepParent "$APP_PATH" "$ZIP_PATH"
shasum -a 256 "$ZIP_PATH" > "$ZIP_SHA_PATH"
if [[ -f "$DMG_PATH" ]] && command -v hdiutil >/dev/null 2>&1; then
  APP_NAME="$(basename "$APP_PATH")"
  DMG_STAGE_DIR="$(mktemp -d "$(dirname "$APP_PATH")/dmg-stage.XXXXXX")"
  trap 'rm -rf "$DMG_STAGE_DIR"' EXIT
  ditto "$APP_PATH" "$DMG_STAGE_DIR/$APP_NAME"
  hdiutil create -volname "Source Document Converter ($ARCH)" \
    -srcfolder "$DMG_STAGE_DIR" \
    -ov -format UDZO "$DMG_PATH"
  shasum -a 256 "$DMG_PATH" > "$DMG_SHA_PATH"
  rm -rf "$DMG_STAGE_DIR"
  trap - EXIT
fi
rm -f "$NOTARIZE_ZIP_PATH"
