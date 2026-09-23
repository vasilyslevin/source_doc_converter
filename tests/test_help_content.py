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


def test_settings_guide_mentions_key_components_and_settings() -> None:
    body = SETTINGS_GUIDE.body
    for text in (
        "Searchable PDF",
        "Markdown for AI",
        "Structured JSON",
        "OCRmyPDF",
        "Tesseract",
        "OCR mode",
        "AI analysis mode",
        "Analyze table structure",
        "CPU only",
        "Docling",
        "Ghostscript",
    ):
        assert text in body


def test_about_mentions_local_processing_privacy() -> None:
    body = ABOUT.body
    assert "local-first desktop tool" in body
    assert "processed locally" in body
