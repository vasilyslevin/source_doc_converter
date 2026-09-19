# Source Document Converter

Source Document Converter is a local-first desktop application for preparing PDF source materials—including research papers, legal filings, reports, exhibits, and scanned records—for search, citation, and AI-assisted analysis. It creates searchable PDFs and structured Markdown or JSON while keeping documents and processing local.

## Use cases

- Academic papers and research sources that need searchable text and citation-ready extraction.
- Legal and court filings, including ECF/docket exports, while preserving legal-review workflows.
- Exhibits and supporting records that must stay linked to original PDF pagination.
- Scanned archival documents that require OCR before review or analysis.
- Reports and reference materials prepared for local search and retrieval.
- Searchable-PDF preparation for mixed digital/scanned source sets.
- Markdown/JSON preparation for AI-assisted analysis without uploading documents.

## Current features

- Drag-and-drop PDF and folder queue.
- Searchable PDF creation through OCRmyPDF and Tesseract.
- Markdown and structured JSON conversion through Docling.
- Combined OCR-to-Docling processing for scanned documents.
- Background processing with progress, cancellation, and per-file results.
- Original-file and existing-output protection.
- Stable output names and PDF page-break markers.
- System Check dialog with component versions and OCR languages.
- Guided dependency setup with one-line status and copyable setup details.
- Explicit local-model setup and download consent.
- Configurable local model directory.
- Offline-by-default Docling conversion using prefetched artifacts.
- Automatic disabling of unavailable output options.
- Privacy-safe diagnostic reports.
- Native Open Output Folder action.
- No application telemetry or automatic document uploads.

## Status

The application is functional but remains in active development. Automated tests run on Windows, macOS, and Ubuntu. Native Windows testing has successfully processed a badly scanned 50 MB, 38-page PDF into searchable PDF, Markdown, and JSON.

Use copies of documents and verify all generated material against the original PDF. A native offline smoke test and packaged-application testing remain required before production or court use.

## Installation

Python 3.11 or later is required.

```bash
python -m venv .venv
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
python -m source_doc_converter
```

Install optional conversion components as needed:

```bash
# OCRmyPDF Python package
python -m pip install -e ".[ocr]"

# Docling for Markdown and JSON
python -m pip install -e ".[docling]"

# Both optional converters
python -m pip install -e ".[full]"
```

OCRmyPDF also requires an OCR engine and supporting system components. For source installs, Tesseract must be installed and available on `PATH`.

### macOS

Homebrew provides OCRmyPDF, Tesseract, and Ghostscript:

```bash
brew install ocrmypdf tesseract ghostscript
python -m pip install -e ".[docling]"
```

For native macOS Apple Silicon package installation, checksum verification, Finder launch behavior, and signing/notarization notes, see [docs/macos.md](docs/macos.md).

### Windows

Install 64-bit Python, OCRmyPDF, and Tesseract according to their official Windows instructions, then install the application extras:

```powershell
python -m pip install -e ".[full]"
```

### Linux and WSL

Install OCRmyPDF and Tesseract using the distribution package manager, then install the Docling extra. Package names vary by distribution.

## First launch

The first launch displays a versioned privacy explanation. It states that documents are processed locally, the application has no telemetry or automatic document upload, model downloads require separate approval, and an operating-system firewall remains the strongest enforcement boundary for highly sensitive work.

Acknowledgement is stored locally through `QSettings`. The notice is shown again if its version changes.

## Local model setup

Markdown and JSON require local Docling model artifacts. The application does not download these artifacts during document processing.

1. Open **Help > System Check**.
2. Select **Choose Model Folder**.
3. Choose a dedicated directory. On one managed Windows workstation this may be `D:\mdl\source_doc_converter`; other users may choose a suitable local directory.
4. Select **Download Models**.
5. Read the network and privacy explanation.
6. Approve the download.
7. Wait until System Check reports **Ready for offline conversion**.
8. Close System Check. Markdown and JSON should become available without restarting the application.

The selected directory is persisted locally. Managed installations can override it before starting the application:

```powershell
$env:SOURCE_DOC_CONVERTER_MODEL_DIR = "D:\mdl\source_doc_converter"
python -m source_doc_converter
```

On Linux or macOS:

```bash
export SOURCE_DOC_CONVERTER_MODEL_DIR="$HOME/models/source_doc_converter"
python -m source_doc_converter
```

The environment override takes precedence over the saved selection. When active, the folder selector is disabled to make the managed configuration clear.

A successful download creates an application readiness marker. A directory containing partial or manually copied files without that marker is not treated as ready.

## Network behavior

The model setup action runs an argument list equivalent to:

```text
docling-tools models download -o <selected-directory>
```

System Check keeps a persistent in-window `Status:` line for dependency checks, guided setup, and model downloads. Use **Show Setup Details** to review full sanitized command output and copy it for troubleshooting.

Searchable-PDF OCR now uses explicit Tesseract runtime profiles. The app can use a validated bundled runtime (Full package), a validated system installation, or a validated manual executable selection. The active profile contributes both the executable and complete tessdata root for each OCR subprocess.

It may connect to model-hosting services used by Docling and its OCR dependencies, including Hugging Face or ModelScope. Those services may receive ordinary connection metadata such as IP address, request time, requested model path, and client metadata.

The downloader is not given queued document paths, document filenames, document content, extracted text, or generated outputs. Model setup and document conversion are separate operations.

During document conversion, the application:

- Requires a completed local-model setup.
- Passes the selected directory as Docling's `artifacts_path`.
- Sets `enable_remote_services=False`.
- Disables external Docling plugins.
- Enables supported offline-library environment controls.
- Refuses Markdown and JSON conversion when models are not ready.

These controls reduce unintended network access but are not a substitute for operating-system network enforcement. For highly sensitive work, prefetch models, disconnect networking or apply an outbound firewall rule, and then perform an offline smoke test.

## Using the application

1. Start the application with `python -m source_doc_converter`.
2. Open **Help > System Check** and verify the required components.
3. Complete local model setup if Markdown or JSON is required.
4. Drop PDF files or a folder into the application.
5. Select Searchable PDF, Markdown for AI, Structured JSON, or a combination.
6. Confirm or change the output folder.
7. Select **Process Documents**.
8. Use **Open Output Folder** after processing completes.

Unavailable output formats are disabled automatically. Searchable PDF depends on OCRmyPDF, Tesseract, and Ghostscript (Windows Full bundles OCRmyPDF + Tesseract but still requires external Ghostscript; Windows Lite/macOS/source installs use external OCR tools). Markdown and JSON require both Docling and completed local model setup.

## Output files

For an input named `filing.pdf`, combined processing produces:

```text
Converted/
├── filing.searchable.pdf
├── filing.md
└── filing.json
```

Docling reads `filing.searchable.pdf` during combined processing, but Markdown and JSON retain the original `filing` stem. Multi-dot filenames are also preserved.

Existing output files are not overwritten. If a later stage fails, files created during that unsuccessful attempt are rolled back when safe to do so.

Markdown output includes this page separator:

```html
<!-- PDF_PAGE_BREAK -->
```

Generated Markdown and JSON are derivative working files. The original PDF remains the authoritative source for page verification and legal citation.

## System Check

The System Check reports:

- Application, operating-system, architecture, Python, and PySide6 versions.
- OCRmyPDF availability and version.
- Tesseract source (bundled or system), version, and installed OCR languages.
- Validated Tesseract installations discovered from bundled, PATH, and documented Windows install locations.
- Docling availability and version.
- Local model readiness.
- Whether the model directory is selected, default, or managed by an environment setting.
- Platform-specific installation guidance.

The model path is visible in the interactive dialog so the user can verify it. Saved diagnostic reports include only model readiness and offline-mode status; they do not intentionally include the model path, usernames, hostnames, home-directory paths, queued document paths, output paths, environment variables, or document content.

In the main window, OCR languages are selected from the active Tesseract installation. Selected languages are persisted and passed to OCRmyPDF as `eng+spa` style values. If any selected language is unavailable in the active runtime, processing is blocked with guidance before document processing begins.

OCR mode is also persisted per user:

- **Smart legal document (recommended)** starts with skip-text and automatically retries with redo when per-page validation finds mixed/header-only text.
- **Skip existing text** is fastest but can miss scanned bodies under digital headers.
- **Redo OCR** is intended for mixed pages or unreliable old OCR.
- **Force OCR** rasterizes everything and is the last-resort repair mode.

AI analysis mode is persisted separately from OCR mode:

- **Auto (recommended)** preflights the effective PDF and uses Fast Markdown for meaningful embedded text when complex tables are not requested; otherwise it uses Accurate mode.
- **Fast Markdown** favors speed and embedded-text extraction while preserving page order and `<!-- PDF_PAGE_BREAK -->`.
- **Accurate Markdown** uses the standard Docling layout pipeline.
- **Accurate with tables** enables table-structure analysis and is the slowest option.

Processing profiles are also persisted:

- **Maximum speed**: higher safe OCR/Docling thread counts.
- **Balanced**: moderate OCR/parser/inference thread counts.
- **Energy saver**: 2 OCR workers with reduced Docling parser/inference threads.

For typical legal filings, start with **Auto** AI analysis plus **Smart** OCR.

## Offline smoke test

After model setup:

1. Close and restart the application.
2. Confirm System Check reports models ready.
3. Disconnect networking or block outbound access for the application.
4. Process a nonconfidential digital PDF into Markdown and JSON.
5. Process a nonconfidential scanned PDF into all three output types.
6. Confirm no model download starts.
7. Confirm all outputs are valid and use the expected filenames.
8. Reconnect networking only after the test is complete.

## Development

Run tests and lint checks with:

```bash
pytest
ruff check .
```

GitHub Actions for `source_doc_converter` runs both commands on Ubuntu, Windows, and macOS. Tests mock optional converters and model downloads; CI does not download Docling models or require OCRmyPDF in ordinary test jobs.

## Packaging direction

The Windows packaging workflow builds separate Full and Lite artifacts: Full bundles the app runtime, Docling tools, OCRmyPDF companion, and pinned Tesseract runtime (Ghostscript remains external and is installed via guided setup when missing), while Lite keeps OCR tools external with guided setup.

Before publishing a release, manually run the **Windows development package** workflow for the release tag and confirm the package succeeds.

## Privacy and security

- Documents are processed locally.
- The application does not include telemetry, cloud document uploads, or automatic updates.
- Model downloads occur only through the explicit setup action after consent.
- Input PDFs are never overwritten.
- Output publication rejects existing destinations.
- Diagnostic reports exclude document and user paths.
- Application-level offline controls do not replace operating-system firewall enforcement.

## License

The application source code is licensed under the MIT License. Third-party components and models retain their respective licenses. Review `THIRD_PARTY_NOTICES.md` before distributing packaged builds.
