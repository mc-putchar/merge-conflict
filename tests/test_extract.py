"""Tests for extraction parser, entry segmentation, and artifact storage."""
import json
from pathlib import Path
import pytest

from nemotron_challenge.contracts import ArtifactRecord
from nemotron_challenge.extraction import (
    BBox,
    ExtractedBlock,
    ParsedPage,
    clean_markdown_text,
    parse_blocks,
    parse_page,
    record_provenance,
    segment_entries,
)
from nemotron_challenge.storage import LanceArtifactStore


def test_clean_markdown_text():
    raw = "Here is \x00 some   text\n\n\n\nwith extra   spaces."
    cleaned = clean_markdown_text(raw)
    assert "\x00" not in cleaned
    assert "   " not in cleaned
    assert "\n\n\n" not in cleaned
    assert cleaned == "Here is some text\n\nwith extra spaces."


def test_parse_blocks_tokens():
    sample_content = (
        "<x_0.0518><y_0.0281>408<x_0.0957><y_0.0469><class_Page-header>\n\n"
        "<x_0.4111><y_0.0266>**HINDUSTAN.**<x_0.6602><y_0.0477><class_Page-header>\n\n"
        "<x_0.0508><y_0.0516>First column body text.<x_0.4503><y_0.1617><class_Text>\n\n"
        "<x_0.5352><y_0.0523>Second column body text.<x_0.9473><y_0.2602><class_Text>\n\n"
        "<x_0.1172><y_0.8102>1 Mill's History of India.<x_0.9453><y_0.8969><class_Footnote>"
    )
    blocks = parse_blocks(sample_content)
    assert len(blocks) == 5
    assert blocks[0].class_name == "Page-header"
    assert blocks[0].text == "408"
    assert blocks[1].class_name == "Page-header"
    assert blocks[1].text == "**HINDUSTAN.**"
    assert blocks[2].class_name == "Text"
    assert blocks[3].class_name == "Text"
    assert blocks[4].class_name == "Footnote"


def test_parse_page_structure():
    page_meta = {
        "page_id": "britannica:test:train:100",
        "volume_id": "12345",
        "row_index": 100,
        "filename": "page-0100-test.jpg",
        "image_sha256": "a" * 64,
    }
    raw_response = {
        "choices": [
            {
                "message": {
                    "content": (
                        "<x_0.05><y_0.02>408<x_0.09><y_0.04><class_Page-header>\n\n"
                        "<x_0.41><y_0.02>**HINDUSTAN.**<x_0.66><y_0.04><class_Page-header>\n\n"
                        "<x_0.05><y_0.05>Left column.<x_0.45><y_0.50><class_Text>\n\n"
                        "<x_0.55><y_0.05>Right column.<x_0.95><y_0.50><class_Text>\n\n"
                        "<x_0.10><y_0.85>Footnote source.<x_0.90><y_0.90><class_Footnote>"
                    )
                }
            }
        ]
    }
    parsed = parse_page(page_meta, raw_response)
    assert parsed.page_number == 408
    assert parsed.running_title == "HINDUSTAN."
    assert len(parsed.headers) == 2
    assert len(parsed.footnotes) == 1
    assert "Left column." in parsed.body_text
    assert "Right column." in parsed.body_text
    # Left column should appear before right column
    left_pos = parsed.body_text.index("Left column.")
    right_pos = parsed.body_text.index("Right column.")
    assert left_pos < right_pos


def test_segment_entries_continuation():
    p1 = ParsedPage(
        page_id="britannica:test:train:1",
        volume_id="vol-1",
        row_index=1,
        filename="p1.jpg",
        image_sha256="1" * 64,
        running_title="ASTRONOMY",
        page_number=10,
        body_text="Astronomy is the study of stars.",
    )
    p2 = ParsedPage(
        page_id="britannica:test:train:2",
        volume_id="vol-1",
        row_index=2,
        filename="p2.jpg",
        image_sha256="2" * 64,
        running_title="ASTRONOMY",
        page_number=11,
        body_text="It includes planetary orbits and celestial mechanics.",
    )
    p3 = ParsedPage(
        page_id="britannica:test:train:50",
        volume_id="vol-2",
        row_index=50,
        filename="p50.jpg",
        image_sha256="3" * 64,
        running_title="BOTANY",
        page_number=200,
        body_text="Botany is the science of plant life.",
    )

    entries = segment_entries([p1, p2, p3])
    assert len(entries) == 2

    astronomy_entry = entries[0]
    assert astronomy_entry.title == "ASTRONOMY"
    assert astronomy_entry.is_continuation is True
    assert len(astronomy_entry.source_pages) == 2
    assert "Astronomy is the study of stars." in astronomy_entry.text
    assert "planetary orbits" in astronomy_entry.text

    botany_entry = entries[1]
    assert botany_entry.title == "BOTANY"
    assert botany_entry.is_continuation is False
    assert len(botany_entry.source_pages) == 1


def test_record_provenance_store(tmp_path):
    p = ParsedPage(
        page_id="britannica:test:train:10",
        volume_id="vol-1",
        row_index=10,
        filename="p10.jpg",
        image_sha256="f" * 64,
        running_title="CHEMISTRY",
        page_number=50,
        body_text="Chemistry is the science of matter.",
    )
    entries = segment_entries([p])
    pages_by_id = {
        p.page_id: {"image_sha256": p.image_sha256, "row_index": p.row_index}
    }
    manifest = {
        "dataset": "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated",
        "revision": "309f765b1ecc83e0a7f7762e44b4a927a7555443",
        "source_url": "https://example.com/source",
        "license": {"spdx": "CC0-1.0"},
    }

    db_dir = tmp_path / "test.lancedb"
    store = LanceArtifactStore(db_dir)
    saved_count = record_provenance(store, entries, pages_by_id, manifest, tmp_path)
    assert saved_count == 1

    rec = store.get(f"extract:{entries[0].entry_id}")
    assert rec is not None
    assert rec.stage == "extract"
    assert len(rec.sources) == 1
    assert rec.sources[0].source_id == p.page_id
    assert rec.sources[0].content_sha256 == "f" * 64
