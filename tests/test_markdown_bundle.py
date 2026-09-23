from pathlib import Path
from threading import Event

import pytest

from source_doc_converter.markdown_bundle import create_markdown_bundle
from source_doc_converter.ocr_pipeline import OcrCancelledError, OcrError, OutputCollisionError


def test_bundle_preserves_queue_order_and_headings(tmp_path: Path) -> None:
    first_pdf = tmp_path / "zeta.pdf"
    second_pdf = tmp_path / "alpha.pdf"
    first_md = tmp_path / "out" / "zeta.md"
    second_md = tmp_path / "out" / "alpha.md"
    first_md.parent.mkdir(parents=True)
    first_md.write_text("first content", encoding="utf-8")
    second_md.write_text("second content", encoding="utf-8")

    destination = tmp_path / "out" / "combined_markdown.md"
    create_markdown_bundle(
        ((first_pdf, first_md), (second_pdf, second_md)),
        destination,
    )

    text = destination.read_text(encoding="utf-8")
    assert text.index("# Source: zeta.pdf") < text.index("# Source: alpha.pdf")
    assert "# Source: zeta.pdf\n\nfirst content" in text
    assert "# Source: alpha.pdf\n\nsecond content" in text


def test_bundle_escapes_markdown_specials_and_keeps_unicode(tmp_path: Path) -> None:
    source = tmp_path / "契約#[A]\n.pdf"
    markdown = tmp_path / "out" / "unicode.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("content", encoding="utf-8")
    destination = tmp_path / "out" / "combined_markdown.md"

    create_markdown_bundle(((source, markdown),), destination)

    text = destination.read_text(encoding="utf-8")
    assert "# Source: 契約\\#\\[A\\] .pdf" in text
    assert "content" in text


def test_bundle_normalizes_newlines_and_handles_empty_markdown(tmp_path: Path) -> None:
    first_pdf = tmp_path / "one.pdf"
    second_pdf = tmp_path / "two.pdf"
    first_md = tmp_path / "out" / "one.md"
    second_md = tmp_path / "out" / "two.md"
    first_md.parent.mkdir(parents=True)
    first_md.write_text("line1\r\nline2\rline3\n", encoding="utf-8")
    second_md.write_text("", encoding="utf-8")
    destination = tmp_path / "out" / "combined_markdown.md"

    create_markdown_bundle(((first_pdf, first_md), (second_pdf, second_md)), destination)

    text = destination.read_text(encoding="utf-8")
    assert "\r" not in text
    assert "# Source: one.pdf\n\nline1\nline2\nline3\n\n# Source: two.pdf\n" in text


def test_bundle_uses_only_explicit_current_job_outputs(tmp_path: Path) -> None:
    queued_pdf = tmp_path / "queued.pdf"
    queued_md = tmp_path / "out" / "queued.md"
    unrelated_md = tmp_path / "out" / "old.md"
    queued_md.parent.mkdir(parents=True)
    queued_md.write_text("queued", encoding="utf-8")
    unrelated_md.write_text("should stay out", encoding="utf-8")
    destination = tmp_path / "out" / "combined_markdown.md"

    create_markdown_bundle(((queued_pdf, queued_md),), destination)

    text = destination.read_text(encoding="utf-8")
    assert "queued" in text
    assert "should stay out" not in text


def test_bundle_conflict_policy_matches_other_outputs(tmp_path: Path) -> None:
    source = tmp_path / "file.pdf"
    markdown = tmp_path / "out" / "file.md"
    destination = tmp_path / "out" / "combined_markdown.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("text", encoding="utf-8")
    destination.write_text("existing", encoding="utf-8")

    with pytest.raises(OutputCollisionError, match="will not be overwritten"):
        create_markdown_bundle(((source, markdown),), destination)


def test_bundle_cleans_up_on_cancellation_or_error(tmp_path: Path) -> None:
    source = tmp_path / "file.pdf"
    markdown = tmp_path / "out" / "file.md"
    destination = tmp_path / "out" / "combined_markdown.md"
    markdown.parent.mkdir(parents=True)
    markdown.write_text("text", encoding="utf-8")
    cancel_event = Event()
    cancel_event.set()

    with pytest.raises(OcrCancelledError):
        create_markdown_bundle(((source, markdown),), destination, cancel_event=cancel_event)
    assert not destination.exists()

    with pytest.raises(OcrError, match="Expected Markdown output was not created"):
        create_markdown_bundle(((source, tmp_path / "out" / "missing.md"),), destination)
    assert not destination.exists()


def test_bundle_requires_at_least_one_successful_markdown(tmp_path: Path) -> None:
    destination = tmp_path / "out" / "combined_markdown.md"
    with pytest.raises(OcrError, match="No Markdown outputs were available"):
        create_markdown_bundle((), destination)
