from source_doc_converter.help_content import ABOUT, GETTING_STARTED, SETTINGS_GUIDE


def test_getting_started_covers_basic_workflow_and_defaults() -> None:
    body = GETTING_STARTED.body
    assert "1. Add PDFs or Add Folder" in body
    assert "2. Review the queue" in body
    assert "3. Choose an output folder" in body
    assert "4. Select output types" in body
    assert "5. Optionally expand Advanced options" in body
    assert "6. Click Process Documents" in body
    assert "7. Review progress/activity" in body
    assert "Adding a file only queues it" in body
    assert "No processing starts automatically" in body


def test_settings_guide_explains_each_visible_option_and_scope() -> None:
    body = SETTINGS_GUIDE.body
    for text in (
        "Smart legal document (recommended)",
        "Skip existing text keeps existing embedded text",
        "Redo OCR replaces existing OCR text",
        "Force OCR rasterizes and OCRs all pages",
        "Automatic chooses the best validated installation available",
        "Bundled uses the app-provided Tesseract package",
        "System uses a detected OS installation on your PATH",
        "Manual/Browse lets you select a specific executable path",
        "Reset to Automatic returns selection control to automatic mode",
        "eng = English text",
        "osd = orientation/script detection",
        "Auto (recommended) chooses a mode",
        "Fast Markdown is quickest",
        "Accurate Markdown preserves richer layout/structure",
        "Analyze table structure improves extraction of complex tables",
        "OCR scanned pages in AI output runs Docling OCR for Markdown/JSON generation only",
        "Maximum speed uses more worker/thread capacity",
        "Balanced keeps moderate resource use and speed",
        "Energy saver reduces concurrency",
        "CPU only enabled: uses CPU for maximum compatibility",
        "CPU only disabled: allows automatic device selection",
        "Docling powers Markdown for AI and Structured JSON and requires local model setup/download",
        "Ghostscript is optional/recommended for PDF/A",
        "Searchable PDF / OCR controls are used only when Searchable PDF output is selected",
        "Markdown and JSON analysis controls are used only when Markdown for AI and/or Structured JSON is selected",
        "Controls are intentionally disabled when their output is not selected",
        "Valid combinations: you can run Searchable PDF only, AI outputs only, or any combination",
    ):
        assert text in body


def test_about_mentions_local_processing_privacy() -> None:
    body = ABOUT.body
    assert "local-first desktop tool" in body
    assert "processed locally" in body
