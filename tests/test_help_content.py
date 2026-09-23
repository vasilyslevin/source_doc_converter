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
    assert "Combined Markdown bundle stays off unless you explicitly enable it" in body


def test_settings_guide_explains_each_visible_option_and_scope() -> None:
    body = SETTINGS_GUIDE.body
    for text in (
        "Smart legal document (recommended)",
        "Skip existing text: Keeps existing embedded text",
        "Redo OCR: Replaces existing OCR text",
        "Force OCR: Rasterizes and OCRs all pages",
        "Automatic: Chooses the best validated installation available",
        "Bundled: Uses the app-provided Tesseract package",
        "System: Uses a detected OS installation on your PATH",
        "Manual/Browse: Lets you select a specific executable path",
        "Reset to Automatic: Returns selection control to automatic mode",
        "eng: English text.",
        "osd: Orientation/script detection.",
        "Auto (recommended): Chooses a mode",
        "Fast Markdown: Is quickest",
        "Accurate Markdown: Preserves richer layout/structure",
        "Analyze table structure: Improves extraction of complex tables",
        "OCR scanned pages in AI output: Runs Docling OCR for Markdown/JSON generation only",
        "Create combined Markdown bundle: Is available only when Markdown for AI is selected",
        "Maximum speed: Uses more worker/thread capacity",
        "Balanced: Keeps moderate resource use and speed",
        "Energy saver: Reduces concurrency",
        "CPU only enabled: Uses CPU for maximum compatibility",
        "CPU only disabled: Allows automatic device selection",
        "Docling: Powers Markdown for AI and Structured JSON and requires local model setup/download",
        "Ghostscript: Is optional/recommended for PDF/A",
        "Searchable PDF / OCR controls: Are used only when Searchable PDF output is selected",
        "Markdown and JSON analysis controls: Are used only when Markdown for AI and/or Structured JSON is selected",
        "Create combined Markdown bundle: Is disabled unless Markdown for AI is selected",
        "Controls disabled state: Is intentional",
        "Valid combinations: Let you run Searchable PDF only, AI outputs only, or any selected combination",
    ):
        assert text in body


def test_about_mentions_local_processing_privacy() -> None:
    body = ABOUT.body
    assert "local-first desktop tool" in body
    assert "processed locally" in body
