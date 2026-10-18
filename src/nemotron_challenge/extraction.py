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
ENTRY_HEADWORD_RE = re.compile(
    r"^(?:_|\*\*)?([A-Z][A-Z0-9\s\'’\-]{1,40}(?:\s*\([^\)]+\))?)(?:_|\*\*)?[\),.:;]+\s+(.*)$",
    re.DOTALL,
)
RANGE_TITLE_RE = re.compile(r"^[A-Z\s]{1,10}\[\s*\d+\s*\]\s*[A-Z\s]{1,10}$")
PAGE_NUM_PATTERN = re.compile(r"^\s*([0-9]{1,4})\s*$")

LIGATURES = {
    "æ": "ae", "œ": "oe", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl",
    "Æ": "Ae", "Œ": "Oe",
}

COMMON_ENGLISH_WORDS = frozenset([
    "the", "of", "and", "a", "to", "in", "is", "you", "that", "it", "he", "was", "for", "on", "are", "as", "with",
    "his", "they", "i", "at", "be", "this", "have", "from", "or", "one", "had", "by", "word", "but", "not", "what",
    "all", "were", "we", "when", "your", "can", "said", "there", "use", "an", "each", "which", "she", "do", "how",
    "their", "if", "will", "up", "other", "about", "out", "many", "then", "them", "these", "so", "some", "her",
    "would", "make", "like", "him", "into", "time", "has", "look", "two", "more", "write", "go", "see", "number",
    "no", "way", "could", "people", "my", "than", "first", "water", "been", "call", "who", "oil", "its", "now",
    "find", "long", "down", "day", "did", "get", "come", "made", "may", "part", "state", "place", "form", "general",
    "system", "order", "body", "great", "name", "species", "power", "small", "hand", "high", "head", "called",
    "case", "book", "large", "air", "light", "side", "plant", "water", "fire", "earth", "acid", "salt", "metal",
    "science", "art", "work", "force", "tree", "animal", "nature", "figure", "iron", "gold", "silver", "lead",
    "line", "point", "surface", "sound", "heat", "cold", "blood", "vessel", "nerve", "motion", "weight", "measure",
    "ship", "king", "country", "city", "town", "sea", "river", "island", "mountain", "church", "law", "right",
    "swiss", "switzerland", "swivels", "sword", "sydenham", "sycophant", "endless", "endorse", "endorsed", "endowment",
    "endymion", "energy", "enemy", "botany", "astronomy", "optics", "mechanics", "chemistry", "bleaching", "horses",
    "sheep", "cattle", "skins", "service", "such", "several", "some", "same", "shall", "should", "spirit", "sumptuary",
    "kind", "ring", "turn", "round", "fluid", "weapon", "worn", "serving", "cut", "appellation", "given", "ancient",
    "athenians", "informants", "sleep", "field", "colour", "color", "cantons", "cause", "sometimes", "simple",
    "degree", "difference", "action", "effect", "manner", "means", "part", "parts", "quality", "quantity", "reason",
    "relation", "respect", "space", "time", "true", "truth", "value", "view", "whole", "wood", "stone", "water",
    "building", "practical", "frame", "timber", "hold", "arch", "beam", "deck", "plank", "trade", "revenue", "militia",
])


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
    corrected_text: str = ""
    uncertain_spans: list[str] = Field(default_factory=list)


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
    corrected_body_text: str = ""
    headers: list[ExtractedBlock] = Field(default_factory=list)
    footnotes: list[ExtractedBlock] = Field(default_factory=list)


class ExtractedEntry(BaseModel):
    entry_id: str
    title: str
    text: str
    raw_text: str = ""
    corrected_text: str = ""
    normalized_text: str = ""
    source_pages: list[str]
    source_row_indices: list[int]
    volume_id: str
    is_continuation: bool = False
    block_count: int = 0
    character_count: int = 0
    validity_score: float = 0.0
    metadata: dict[str, Any] = Field(default_factory=dict)


def compute_vocabulary_validity(
    text: str,
    lexicon: frozenset[str] | set[str] | None = None,
) -> float:
    """Calculate the ratio of recognized dictionary words to measure OCR readability."""
    tokens = re.findall(r"[a-zA-Z]{2,}", text.lower())
    if not tokens:
        return 0.0
    vocab = lexicon if lexicon is not None else COMMON_ENGLISH_WORDS
    valid_count = sum(1 for token in tokens if token in vocab)
    return round(valid_count / len(tokens), 4)


def normalize_entry_text(
    text: str,
    modern_vocab: set[str] | frozenset[str] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    """Normalize historical typography while preserving raw text and auditing changes."""
    changes: list[dict[str, Any]] = []
    normalized = text

    # 1. Line-break hyphen rejoining
    def unhyphen(match: re.Match) -> str:
        orig = match.group(0)
        rejoined = match.group(1) + match.group(2)
        changes.append({"rule": "line_break_hyphen", "original": orig, "replacement": rejoined})
        return rejoined

    normalized = re.sub(r"([A-Za-z]+)-\s*\n\s*([a-z]+)", unhyphen, normalized)

    # 2. Ligatures expansion
    def expand_ligature(match: re.Match) -> str:
        char = match.group(0)
        repl = LIGATURES[char]
        changes.append({"rule": "ligature_expansion", "original": char, "replacement": repl})
        return repl

    normalized = re.sub("[" + "".join(LIGATURES.keys()) + "]", expand_ligature, normalized)

    # 3. Unicode long-s
    if "ſ" in normalized:
        count = normalized.count("ſ")
        normalized = normalized.replace("ſ", "s")
        changes.append({"rule": "long_s", "original": "ſ", "replacement": "s", "count": count})

    # 4. Dictionary-arbitrated OCR f/s confusion
    vocab = modern_vocab or COMMON_ENGLISH_WORDS
    def fix_fs(match: re.Match) -> str:
        token = match.group(0)
        lower = token.lower()
        if "f" in lower and lower not in vocab:
            candidate = lower.replace("f", "s")
            if candidate in vocab and candidate != lower:
                changes.append({"rule": "ocr_f_s_confusion", "original": token, "replacement": candidate})
                return candidate if token.islower() else candidate.capitalize()
        return token

    normalized = re.sub(r"[A-Za-z]+", fix_fs, normalized)
    return normalized, changes


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


def clean_headword_title(hw: str) -> str:
    cleaned = re.sub(r"[\*\_]", "", hw).strip(".,:; )(")
    return cleaned


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
        if ("page-header" in cls_lower or cls_lower == "header") and "section" not in cls_lower:
            headers.append(block)
            num_match = PAGE_NUM_PATTERN.match(block.text)
            if num_match:
                page_number = int(num_match.group(1))
            else:
                title_candidate = re.sub(r"^[0-9\s]+", "", block.text)
                title_candidate = re.sub(r"[\*\_]", "", title_candidate).strip()
                if title_candidate and len(title_candidate) > len(running_title):
                    running_title = title_candidate
        elif "page-footer" in cls_lower or "footer" in cls_lower or "footnote" in cls_lower:
            footnotes.append(block)
        else:
            body_blocks.append(block)

    # Sort body blocks in natural reading order:
    # Top spanning blocks (width > 0.65, y1 < 0.25) -> Column 1 (x_mid < 0.52) -> Column 2 -> Bottom spanning blocks
    def reading_order_key(b: ExtractedBlock) -> tuple[int, float, float]:
        is_spanning = (b.bbox.x2 - b.bbox.x1) > 0.65
        if is_spanning and b.bbox.y1 < 0.25:
            return (0, b.bbox.y1, b.bbox.x1)
        if is_spanning and b.bbox.y2 > 0.85:
            return (3, b.bbox.y1, b.bbox.x1)
        col = 1 if ((b.bbox.x1 + b.bbox.x2) / 2.0) < 0.52 else 2
        return (col, b.bbox.y1, b.bbox.x1)

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

    sorted_pages = sorted(pages, key=lambda p: (p.volume_id, p.row_index))
    raw_entries: list[dict[str, Any]] = []
    current_entry: dict[str, Any] | None = None

    stopwords = {
        "THE", "AND", "FOR", "SEE", "PART", "VOL", "CHAP", "SEC", "SECT",
        "FIG", "PLATE", "AN", "OF", "IN", "ON", "AT", "TO", "BY", "WITH", "FROM",
    }

    for page in sorted_pages:
        page_text = page.corrected_body_text or page.body_text
        page_title = page.running_title or f"Britannica Volume {page.volume_id} Row {page.row_index}"
        clean_title = re.sub(r"[^\w\s-]", "", page_title).strip() or f"Entry_{page.row_index}"
        is_range = bool(RANGE_TITLE_RE.match(page.running_title.strip()))

        paragraphs = [p.strip() for p in page_text.split("\n\n") if p.strip()]
        raw_paragraphs = [p.strip() for p in page.body_text.split("\n\n") if p.strip()]
        detected_hws: list[str] = []
        for p in paragraphs:
            m = ENTRY_HEADWORD_RE.match(p)
            if m:
                cand = m.group(1).strip()
                first_w = cand.split()[0].rstrip(".,:;")
                if first_w not in stopwords and len(cand) > 1:
                    detected_hws.append(cand)

        is_dict_page = is_range or len(detected_hws) >= 2

        if not is_dict_page:
            # Treatise / single-entry page
            is_cont = False
            if current_entry and current_entry["volume_id"] == page.volume_id:
                last_row = current_entry["source_row_indices"][-1]
                row_diff = page.row_index - last_row
                if row_diff == 1:
                    is_cont = True
                elif row_diff <= 3 and page.running_title and current_entry["title"].lower() == clean_title.lower():
                    is_cont = True

            if is_cont and current_entry is not None:
                delim = " " if not current_entry["text"].endswith((".", "!", "?", "\n")) else "\n\n"
                current_entry["text"] = f"{current_entry['text']}{delim}{page_text}".strip()
                raw_delim = " " if not current_entry["raw_text"].endswith((".", "!", "?", "\n")) else "\n\n"
                current_entry["raw_text"] = f"{current_entry['raw_text']}{raw_delim}{page.body_text}".strip()
                current_entry["source_pages"].append(page.page_id)
                current_entry["source_row_indices"].append(page.row_index)
                current_entry["is_continuation"] = True
                current_entry["block_count"] += len(page.blocks)
                current_entry["character_count"] = len(current_entry["text"])
            else:
                if current_entry is not None:
                    raw_entries.append(current_entry)
                entry_id = f"entry-{re.sub(r'[^a-zA-Z0-9]+', '-', clean_title).strip('-').lower()}-{page.row_index}"
                current_entry = {
                    "entry_id": entry_id,
                    "title": clean_title,
                    "text": page_text,
                    "raw_text": page.body_text,
                    "source_pages": [page.page_id],
                    "source_row_indices": [page.row_index],
                    "volume_id": page.volume_id,
                    "is_continuation": False,
                    "block_count": len(page.blocks),
                    "character_count": len(page.body_text),
                    "metadata": {
                        "page_number": page.page_number,
                        "running_title": page.running_title,
                    },
                }
        else:
            # Dictionary page: split paragraphs by headword
            for paragraph_index, p in enumerate(paragraphs):
                raw_paragraph = raw_paragraphs[paragraph_index] if paragraph_index < len(raw_paragraphs) else p
                m = ENTRY_HEADWORD_RE.match(p)
                hw = None
                if m:
                    cand = m.group(1).strip()
                    first_w = cand.split()[0].rstrip(".,:;")
                    if first_w not in stopwords and len(cand) > 1:
                        hw = cand

                if hw:
                    if current_entry is not None:
                        raw_entries.append(current_entry)
                    h_clean = clean_headword_title(hw)
                    entry_id = f"entry-{re.sub(r'[^a-zA-Z0-9]+', '-', h_clean).strip('-').lower()}-{page.row_index}"
                    current_entry = {
                        "entry_id": entry_id,
                        "title": h_clean,
                        "text": p,
                        "raw_text": raw_paragraph,
                        "source_pages": [page.page_id],
                        "source_row_indices": [page.row_index],
                        "volume_id": page.volume_id,
                        "is_continuation": False,
                        "block_count": 1,
                        "character_count": len(p),
                        "metadata": {
                            "page_number": page.page_number,
                            "running_title": page.running_title,
                            "headword": hw,
                        },
                    }
                else:
                    if current_entry is not None and current_entry["volume_id"] == page.volume_id:
                        delim = " " if not current_entry["text"].endswith((".", "!", "?", "\n")) else "\n\n"
                        current_entry["text"] = f"{current_entry['text']}{delim}{p}".strip()
                        raw_delim = " " if not current_entry["raw_text"].endswith((".", "!", "?", "\n")) else "\n\n"
                        current_entry["raw_text"] = f"{current_entry['raw_text']}{raw_delim}{raw_paragraph}".strip()
                        if page.page_id not in current_entry["source_pages"]:
                            current_entry["source_pages"].append(page.page_id)
                        if page.row_index not in current_entry["source_row_indices"]:
                            current_entry["source_row_indices"].append(page.row_index)
                        current_entry["block_count"] += 1
                        current_entry["character_count"] = len(current_entry["text"])
                    else:
                        if current_entry is not None:
                            raw_entries.append(current_entry)
                        c_title = clean_title or f"Entry_{page.row_index}"
                        entry_id = f"entry-{re.sub(r'[^a-zA-Z0-9]+', '-', c_title).strip('-').lower()}-{page.row_index}"
                        current_entry = {
                            "entry_id": entry_id,
                            "title": c_title,
                            "text": p,
                            "raw_text": raw_paragraph,
                            "source_pages": [page.page_id],
                            "source_row_indices": [page.row_index],
                            "volume_id": page.volume_id,
                            "is_continuation": False,
                            "block_count": 1,
                            "character_count": len(p),
                            "metadata": {
                                "page_number": page.page_number,
                                "running_title": page.running_title,
                            },
                        }

    if current_entry is not None:
        raw_entries.append(current_entry)

    entries: list[ExtractedEntry] = []
    for raw in raw_entries:
        raw_text = raw["text"]
        norm_text, text_changes = normalize_entry_text(raw_text)
        validity = compute_vocabulary_validity(norm_text)
        raw_meta = raw.get("metadata", {})
        raw_meta["text_changes_count"] = len(text_changes)
        if text_changes:
            raw_meta["text_changes_sample"] = text_changes[:5]

        entries.append(
            ExtractedEntry(
                entry_id=raw["entry_id"],
                title=raw["title"],
                text=raw_text,
                raw_text=raw.get("raw_text", raw_text),
                corrected_text=raw_text,
                normalized_text=norm_text,
                source_pages=raw["source_pages"],
                source_row_indices=raw["source_row_indices"],
                volume_id=raw["volume_id"],
                is_continuation=raw["is_continuation"],
                block_count=raw["block_count"],
                character_count=raw["character_count"],
                validity_score=validity,
                metadata=raw_meta,
            )
        )

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
