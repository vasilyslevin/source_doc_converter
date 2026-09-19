# Source Document Converter on macOS

## Supported macOS targets

- Apple Silicon package: `SourceDocumentConverter-macOS-arm64.zip` (and optional DMG)
- Minimum supported macOS version: 12.0

This milestone provides Apple Silicon packages only.

## Install and verify

1. Download `SourceDocumentConverter-macOS-arm64.zip` (or DMG) and its `.sha256` file.
2. Verify integrity:

   ```bash
   shasum -a 256 -c SourceDocumentConverter-macOS-arm64.zip.sha256
   ```

3. Expand the ZIP (or open the DMG) and move `Source Document Converter.app` to `/Applications` if desired.
4. Open the app from Finder.

For development/ad-hoc builds, Gatekeeper may show a warning because the build is not Developer ID notarized. Use standard macOS open/confirm flows from Finder to proceed with testing.

## Clean-Mac setup and dependency discovery

The app bundle includes Python, Source Document Converter, PySide6/Qt, Docling runtime components, and companion executables required by the app bundle itself.

System OCR dependencies are discovered without relying on shell-inherited PATH and include:

- `/opt/homebrew/bin`, `/opt/homebrew/sbin`
- `/usr/local/bin`, `/usr/local/sbin`
- validated manual selections
- normal PATH lookup when available

If OCR dependencies are missing, use Homebrew commands explicitly:

```bash
brew install ocrmypdf tesseract ghostscript
```

The app does not silently install Homebrew or system packages.

## External Docling models

Docling model artifacts are intentionally external. They are **not** bundled and are never auto-downloaded during build, startup, or conversion.

Use the existing setup flow:

1. Open **Help > System Check**
2. Choose model folder
3. Select **Download Models**
4. Confirm download consent

After setup, offline processing remains available.

## Finder launch behavior

Finder-launched apps do not inherit shell PATH. Source Document Converter adds standard Homebrew prefixes to subprocess lookup so OCRmyPDF/Tesseract/Ghostscript discovery remains reliable from Finder and Terminal launches.

## Development/ad-hoc vs signed/notarized builds

- CI always creates ad-hoc signed development artifacts to validate bundle integrity.
- Optional Developer ID signing + hardened runtime + notarization + stapling run only when all required secrets are configured.
- Missing signing secrets safely skip production signing/notarization.

## Security expectations

- Do not disable Gatekeeper, SIP, or quarantine globally.
- Prefer checksum verification and standard Finder/macOS confirmation flows.
- Signed/notarized releases (when produced) are the preferred distribution artifacts.
