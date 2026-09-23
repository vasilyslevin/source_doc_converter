from dataclasses import dataclass


@dataclass(frozen=True)
class HelpSection:
    title: str
    body: str


GETTING_STARTED = HelpSection(
    title="Getting Started",
    body="""
1. Add PDFs or Add Folder in the drop area to queue source documents.
2. Review the queue and remove items you do not want to process.
3. Choose an output folder. Nothing runs until you do this.
4. Select output types: Searchable PDF, Markdown for AI, and/or Structured JSON.
5. Optionally expand Advanced options to tune OCR, AI behavior, performance, and Markdown bundling.
6. Click Process Documents.
7. Review progress/activity and use Open Output Folder when processing finishes.

Fresh-install behavior:
- Adding a file only queues it.
- No processing starts automatically.
- The source document is never modified in place.
- You must choose an output folder before processing.
- Default processing creates Searchable PDF only.
- Combined Markdown bundle stays off unless you explicitly enable it.
- Markdown/JSON require selecting those outputs and having local Docling models ready.
""".strip(),
)

SETTINGS_GUIDE = HelpSection(
    title="Settings Guide",
    body="""
What each output creates:
- Searchable PDF: Uses OCRmyPDF + Tesseract to add searchable/selectable text to a PDF.
- Markdown for AI: Uses Docling to create markdown for AI workflows.
- Structured JSON: Uses Docling to create structured extraction data.
- Create combined Markdown bundle: Adds one extra `combined_markdown.md` file from Markdown outputs generated in the current job while preserving each individual Markdown file.

Searchable PDF / OCR settings (these affect Searchable PDF output):
- OCR mode: Smart legal document (recommended) checks whether a page already has usable text and handles common legal-document mixes of digital text + scanned pages safely.
- Skip existing text: Keeps existing embedded text and OCRs only pages that have no text layer.
- Redo OCR: Replaces existing OCR text when old OCR appears unreliable (for example, bad copy quality or garbled text).
- Force OCR: Rasterizes and OCRs all pages. It is slower and can reduce existing PDF structure/fidelity, so use it only as a repair option.
- Tesseract selection:
  - Automatic: Chooses the best validated installation available.
  - Bundled: Uses the app-provided Tesseract package when present.
  - System: Uses a detected OS installation on your PATH.
  - Manual/Browse: Lets you select a specific executable path.
  - Reset to Automatic: Returns selection control to automatic mode.
- OCR languages:
  - eng: English text.
  - osd: Orientation/script detection.
  - Selected languages only: Choosing only needed languages usually improves speed and can reduce recognition errors.

Markdown and JSON analysis settings (these affect Markdown/JSON outputs):
- AI analysis mode:
  - Auto (recommended): Chooses a mode based on document characteristics.
  - Fast Markdown: Is quickest and favors simpler/plain extraction.
  - Accurate Markdown: Preserves richer layout/structure but uses more processing.
- Analyze table structure: Improves extraction of complex tables for accurate Markdown/JSON analysis and adds extra processing time.
- OCR scanned pages in AI output: Runs Docling OCR for Markdown/JSON generation only. This is separate from OCRmyPDF/Tesseract, which are used for Searchable PDF output.
- Create combined Markdown bundle: Is available only when Markdown for AI is selected and creates one additional file after individual Markdown outputs are written.

Performance settings:
- Maximum speed: Uses more worker/thread capacity to finish sooner.
- Balanced: Keeps moderate resource use and speed.
- Energy saver: Reduces concurrency to lower system load.
- CPU only enabled: Uses CPU for maximum compatibility and predictable behavior.
- CPU only disabled: Allows automatic device selection when supported by your environment; this does not guarantee GPU acceleration.

Component roles and setup:
- OCRmyPDF + Tesseract: Power Searchable PDF creation.
- Docling: Powers Markdown for AI and Structured JSON and requires local model setup/download.
- Ghostscript: Is optional/recommended for PDF/A and advanced PDF post-processing support.

Which controls apply and why some are disabled:
- Searchable PDF / OCR controls: Are used only when Searchable PDF output is selected.
- Markdown and JSON analysis controls: Are used only when Markdown for AI and/or Structured JSON is selected.
- Create combined Markdown bundle: Is disabled unless Markdown for AI is selected because the bundle uses Markdown outputs only.
- Analyze table structure: Is enabled only when AI analysis mode supports it (Auto or Accurate).
- Controls disabled state: Is intentional when an output is not selected or when required runtime components are unavailable.
- Valid combinations: Let you run Searchable PDF only, AI outputs only, or any selected combination; behavior follows the selected outputs and enabled controls above.
""".strip(),
)

ABOUT = HelpSection(
    title="About",
    body="""
Source Document Converter is a local-first desktop tool for converting legal PDFs into:
- Searchable PDF
- Markdown for AI
- Structured JSON

Privacy:
- Documents are processed locally.
- The app does not auto-upload your source files or generated outputs.
""".strip(),
)


def all_sections() -> dict[str, HelpSection]:
    return {
        "getting-started": GETTING_STARTED,
        "settings-guide": SETTINGS_GUIDE,
        "about": ABOUT,
    }
