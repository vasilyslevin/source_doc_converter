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
5. Optionally expand Advanced options to tune OCR and performance.
6. Click Process Documents.
7. Review progress/activity and use Open Output Folder when processing finishes.

Fresh-install behavior:
- Adding a file only queues it.
- No processing starts automatically.
- The source document is never modified in place.
- You must choose an output folder before processing.
- Default processing creates Searchable PDF only.
- Markdown/JSON require selecting those outputs and having local Docling models ready.
""".strip(),
)

SETTINGS_GUIDE = HelpSection(
    title="Settings Guide",
    body="""
What each output creates:
- Searchable PDF uses OCRmyPDF + Tesseract to add searchable/selectable text to a PDF.
- Markdown for AI uses Docling to create markdown for AI workflows.
- Structured JSON uses Docling to create structured extraction data.

Searchable PDF / OCR settings (these affect Searchable PDF output):
- OCR mode: Smart legal document (recommended) checks whether a page already has usable text and handles common legal-document mixes of digital text + scanned pages safely.
- Skip existing text keeps existing embedded text and OCRs only pages that have no text layer.
- Redo OCR replaces existing OCR text when old OCR appears unreliable (for example, bad copy quality or garbled text).
- Force OCR rasterizes and OCRs all pages, which is slower and can reduce existing PDF structure/fidelity; use it only as a repair option.
- Tesseract selection:
  - Automatic chooses the best validated installation available.
  - Bundled uses the app-provided Tesseract package when present.
  - System uses a detected OS installation on your PATH.
  - Manual/Browse lets you select a specific executable path.
  - Reset to Automatic returns selection control to automatic mode.
- OCR languages: choose the languages Tesseract should recognize (eng = English text, osd = orientation/script detection). Selecting only needed languages usually improves speed and can reduce recognition errors.

Markdown and JSON analysis settings (these affect Markdown/JSON outputs):
- AI analysis mode:
  - Auto (recommended) chooses a mode based on document characteristics.
  - Fast Markdown is quickest and favors simpler/plain extraction.
  - Accurate Markdown preserves richer layout/structure but uses more processing.
- Analyze table structure improves extraction of complex tables for accurate Markdown/JSON analysis and adds extra processing time.
- OCR scanned pages in AI output runs Docling OCR for Markdown/JSON generation only. This is separate from OCRmyPDF/Tesseract, which are used for Searchable PDF output.

Performance settings:
- Maximum speed uses more worker/thread capacity to finish sooner.
- Balanced keeps moderate resource use and speed.
- Energy saver reduces concurrency to lower system load.
- CPU only enabled: uses CPU for maximum compatibility and predictable behavior.
- CPU only disabled: allows automatic device selection when supported by your environment; this does not guarantee GPU acceleration.

Component roles and setup:
- OCRmyPDF + Tesseract power Searchable PDF creation.
- Docling powers Markdown for AI and Structured JSON and requires local model setup/download.
- Ghostscript is optional/recommended for PDF/A and advanced PDF post-processing support.

Which controls apply and why some are disabled:
- Searchable PDF / OCR controls are used only when Searchable PDF output is selected.
- Markdown and JSON analysis controls are used only when Markdown for AI and/or Structured JSON is selected.
- Analyze table structure is enabled only when AI analysis mode supports it (Auto or Accurate).
- Controls are intentionally disabled when their output is not selected or when required runtime components are unavailable.
- Valid combinations: you can run Searchable PDF only, AI outputs only, or any combination of selected outputs; behavior follows the selected outputs and enabled controls above.
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
