"""Extraction, block parsing, and entry segmentation for historical Britannica scans."""
from __future__ import annotations

import base64
from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
import re
from typing import Any

from pydantic import BaseModel, Field

from .contracts import ArtifactRecord, SourceReference
from .storage import LanceArtifactStore

BLOCK_PATTERN = re.compile(
    r"<x_([0-9.]+)> *<y_([0-9.]+)>([\s\S]*?)<x_([0-9.]+)> *<y_([0-9.]+)> *<class_([^>]+)>"
)
HEADWORD_PATTERN = re.compile(
    r"(?:^|\n)\*{2}([A-Z][A-Z0-9\s,.'-]{1,50}\.?)\*{2}\s*"
)
PAGE_NUM_PATTERN = re.compile(r"^\s*([0-9]{1,4})\s*$")


class BBox(BaseModel):
    x1: float = Field(ge=0.0, le=1.0)
    y1: float = Field(ge=0.0, le=1.0)
    x2: float = Field(ge=0.0, le=1.0)
    y2: float = Field(ge=0.0, le=1.0)


class ExtractedBlock(BaseModel):
    class_name: str
    bbox: BBox
    text: str
    raw_text: str


class ParsedPage(BaseModel):
    page_id: str
    volume_id: str
    row_index: int
    filename: str
    image_sha256: str
    running_title: str = ""
    page_number: int | None = None
    blocks: list[ExtractedBlock] = Field(default_factory=list)
    body_text: str = ""
    headers: list[ExtractedBlock] = Field(default_factory=list)
    footnotes: list[ExtractedBlock] = Field(default_factory=list)


class ExtractedEntry(BaseModel):
    entry_id: str
    title: str
    text: str
    source_pages: list[str]
    source_row_indices: list[int]
    volume_id: str
    is_continuation: bool = False
    block_count: int = 0
    character_count: int = 0
    metadata: dict[str, Any] = Field(default_factory=dict)


def clean_markdown_text(text: str) -> str:
    """Normalize extracted OCR text while preserving markdown emphasis and words."""
    cleaned = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    cleaned = re.sub(r"[ \t]+", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


def parse_blocks(content: str) -> list[ExtractedBlock]:
    """Extract classified bounding boxes and text from Nemotron Parse 3.5 output."""
    blocks: list[ExtractedBlock] = []
    for match in BLOCK_PATTERN.finditer(content):
        x1_str, y1_str, raw_text, x2_str, y2_str, class_name = match.groups()
        try:
            x1, y1 = float(x1_str), float(y1_str)
            x2, y2 = float(x2_str), float(y2_str)
            bbox = BBox(x1=min(x1, x2), y1=min(y1, y2), x2=max(x1, x2), y2=max(y1, y2))
        except ValueError:
            continue
        cleaned_text = clean_markdown_text(raw_text)
        blocks.append(
            ExtractedBlock(
                class_name=class_name.strip(),
                bbox=bbox,
                text=cleaned_text,
                raw_text=raw_text,
            )
        )
    return blocks


def parse_page(
    page_meta: dict[str, Any],
    raw_response: dict[str, Any],
) -> ParsedPage:
    """Parse one scan page from raw Parse 3.5 model response."""
    choices = raw_response.get("choices", [])
    content = ""
    if choices and isinstance(choices, list) and isinstance(choices[0], dict):
        message = choices[0].get("message", {})
        content = message.get("content", "") if isinstance(message, dict) else ""

    blocks = parse_blocks(content)

    headers: list[ExtractedBlock] = []
    footnotes: list[ExtractedBlock] = []
    body_blocks: list[ExtractedBlock] = []

    running_title = ""
    page_number: int | None = None

    for block in blocks:
        cls_lower = block.class_name.lower()
        if "header" in cls_lower:
            headers.append(block)
            num_match = PAGE_NUM_PATTERN.match(block.text)
            if num_match:
                page_number = int(num_match.group(1))
            else:
                title_candidate = re.sub(r"^[0-9\s]+", "", block.text)
                title_candidate = re.sub(r"[\*\_]", "", title_candidate).strip()
                if title_candidate and len(title_candidate) > len(running_title):
                    running_title = title_candidate
        elif "footer" in cls_lower or "footnote" in cls_lower:
            footnotes.append(block)
        else:
            body_blocks.append(block)

    # Sort body blocks in natural 2-column reading order:
    # First sort by horizontal column (x midpoint < 0.5 vs >= 0.5), then by y position.
    def reading_order_key(b: ExtractedBlock) -> tuple[int, float]:
        col = 0 if ((b.bbox.x1 + b.bbox.x2) / 2.0) < 0.52 else 1
        return (col, b.bbox.y1)

    body_blocks_sorted = sorted(body_blocks, key=reading_order_key)
    body_text_parts = [b.text for b in body_blocks_sorted if b.text]
    body_text = "\n\n".join(body_text_parts)

    return ParsedPage(
        page_id=page_meta["page_id"],
        volume_id=str(page_meta.get("volume_id", "")),
        row_index=int(page_meta.get("row_index", 0)),
        filename=page_meta.get("filename", ""),
        image_sha256=page_meta.get("image_sha256", ""),
        running_title=running_title,
        page_number=page_number,
        blocks=blocks,
        body_text=body_text,
        headers=headers,
        footnotes=footnotes,
    )


def segment_entries(pages: list[ParsedPage]) -> list[ExtractedEntry]:
    """Segment encyclopedia entries and join continuations across sequential pages."""
    if not pages:
        return []

    # Sort pages by volume_id then row_index
    sorted_pages = sorted(pages, key=lambda p: (p.volume_id, p.row_index))
    entries: list[ExtractedEntry] = []

    current_entry: ExtractedEntry | None = None

    for page in sorted_pages:
        page_title = page.running_title or f"Britannica Volume {page.volume_id} Row {page.row_index}"
        clean_title = re.sub(r"[^\w\s-]", "", page_title).strip()
        if not clean_title:
            clean_title = f"Entry_{page.row_index}"

        # Check if page continues previous entry:
        # Condition 1: Same volume and consecutive row_index (diff == 1)
        # Condition 2: Same volume, same running_title, and small gap (diff <= 3)
        is_continuation = False
        if current_entry and current_entry.volume_id == page.volume_id:
            last_row = current_entry.source_row_indices[-1]
            row_diff = page.row_index - last_row
            if row_diff == 1:
                is_continuation = True
            elif row_diff <= 3 and page.running_title and current_entry.title.lower() == clean_title.lower():
                is_continuation = True

        if is_continuation and current_entry is not None:
            # Join text to current entry
            join_delimiter = " " if not current_entry.text.endswith((".", "!", "?", "\n")) else "\n\n"
            current_entry.text = f"{current_entry.text}{join_delimiter}{page.body_text}".strip()
            current_entry.source_pages.append(page.page_id)
            current_entry.source_row_indices.append(page.row_index)
            current_entry.is_continuation = True
            current_entry.block_count += len(page.blocks)
            current_entry.character_count = len(current_entry.text)
        else:
            if current_entry is not None:
                entries.append(current_entry)

            entry_id = f"entry-{re.sub(r'[^a-zA-Z0-9]+', '-', clean_title).strip('-').lower()}-{page.row_index}"
            current_entry = ExtractedEntry(
                entry_id=entry_id,
                title=clean_title,
                text=page.body_text,
                source_pages=[page.page_id],
                source_row_indices=[page.row_index],
                volume_id=page.volume_id,
                is_continuation=False,
                block_count=len(page.blocks),
                character_count=len(page.body_text),
                metadata={
                    "page_number": page.page_number,
                    "running_title": page.running_title,
                },
            )

    if current_entry is not None:
        entries.append(current_entry)

    return entries


def record_provenance(
    store: LanceArtifactStore,
    entries: list[ExtractedEntry],
    pages_by_id: dict[str, dict[str, Any]],
    manifest: dict[str, Any],
    artifacts_dir: Path,
) -> int:
    """Save an ArtifactRecord for each extracted entry into LanceArtifactStore."""
    records_saved = 0
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")
    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    source_url = manifest.get("source_url", "")
    license_spdx = manifest.get("license", {}).get("spdx", "CC0-1.0")

    for entry in entries:
        sources: list[SourceReference] = []
        for pid in entry.source_pages:
            pmeta = pages_by_id.get(pid, {})
            sources.append(
                SourceReference(
                    dataset=dataset,
                    dataset_revision=revision,
                    source_id=pid,
                    source_url=source_url,
                    content_sha256=pmeta.get("image_sha256", "0" * 64),
                    license=license_spdx,
                )
            )

        artifact_file = artifacts_dir / f"{entry.entry_id}.json"
        artifact_record = ArtifactRecord(
            record_id=f"extract:{entry.entry_id}",
            stage="extract",
            sources=sources,
            artifact_path=str(artifact_file),
            metadata={
                "title": entry.title,
                "volume_id": entry.volume_id,
                "source_pages": entry.source_pages,
                "source_row_indices": entry.source_row_indices,
                "character_count": entry.character_count,
                "block_count": entry.block_count,
                "is_continuation": entry.is_continuation,
            },
        )
        store.put(artifact_record)
        records_saved += 1

    return records_saved
