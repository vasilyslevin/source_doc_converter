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
Output types:
- Searchable PDF: creates OCR text layer using OCRmyPDF + Tesseract.
- Markdown for AI: creates markdown optimized for AI ingestion using Docling.
- Structured JSON: creates structured extraction output using Docling.

Searchable PDF / OCR:
- OCR mode: Smart, Skip, Redo, Force (speed/quality trade-offs).
- Tesseract selection: Automatic/Bundled/System/Manual executable.
- OCR languages: selected Tesseract languages used for Searchable PDF OCR.
- Tesseract recognizes text in scanned pages; OCRmyPDF builds the searchable PDF.

Markdown and JSON analysis:
- AI analysis mode: Auto, Fast Markdown, Accurate Markdown.
- Analyze table structure: improves table extraction for accurate modes, slower.
- OCR scanned pages in AI output: Docling OCR for AI outputs only (distinct from Searchable PDF OCR).

Performance:
- Processing profile: Maximum speed, Balanced, Energy saver.
- CPU only: best compatibility and predictable behavior.
- Disabling CPU only allows automatic device selection where supported; GPU use may vary.

Components:
- Docling handles Markdown/JSON conversion and requires local model files.
- OCRmyPDF and Tesseract are required for Searchable PDF output.
- Ghostscript is optional/recommended for PDF/A and advanced post-processing.
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
