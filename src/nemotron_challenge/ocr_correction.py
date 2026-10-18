"""Image-grounded transcription correction for parsed historical text blocks."""
from __future__ import annotations

import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO
import json
from pathlib import Path
import re
from typing import Any

from PIL import Image
from pydantic import BaseModel, Field

from .clients import ChatClient, ServiceError
from .extraction import ExtractedBlock, ParsedPage, clean_markdown_text, compute_vocabulary_validity


TEXT_CLASSES = ("text", "section-header", "list", "table")
UNCERTAIN_PATTERN = re.compile(r"\[unclear(?::[^\]]*)?\]", re.IGNORECASE)


class CropCorrection(BaseModel):
    block_index: int
    bbox: dict[str, float]
    raw_text: str
    corrected_text: str
    uncertain_spans: list[str] = Field(default_factory=list)
    status: str
    model_id: str
    crop_sha256: str
    raw_model_output: str = ""
    error: str = ""


def _response_text(response: dict[str, Any]) -> str:
    choices = response.get("choices", [])
    if not choices or not isinstance(choices[0], dict):
        return ""
    message = choices[0].get("message", {})
    return str(message.get("content", "")).strip() if isinstance(message, dict) else ""


def _parse_correction(content: str) -> tuple[str, list[str]]:
    match = re.search(r"\{[\s\S]*\}", content)
    if not match:
        raise ValueError("correction response does not contain a JSON object")
    data = json.loads(match.group(0))
    transcription = clean_markdown_text(data.get("transcription", ""))
    uncertain = data.get("uncertain_spans", [])
    if not transcription or not isinstance(uncertain, list) or not all(isinstance(item, str) for item in uncertain):
        raise ValueError("correction response has an invalid transcription contract")
    markers = UNCERTAIN_PATTERN.findall(transcription)
    return transcription, list(dict.fromkeys([*uncertain, *markers]))


def _crop_data_url(image: Image.Image, block: ExtractedBlock, padding: int = 12) -> tuple[str, str]:
    width, height = image.size
    box = (
        max(0, round(block.bbox.x1 * width) - padding),
        max(0, round(block.bbox.y1 * height) - padding),
        min(width, round(block.bbox.x2 * width) + padding),
        min(height, round(block.bbox.y2 * height) + padding),
    )
    crop = image.crop(box)
    if crop.width < 2 or crop.height < 2:
        raise ValueError("text crop is empty")
    scale = max(1, min(3, round(1800 / crop.width)))
    if scale > 1:
        crop = crop.resize((crop.width * scale, crop.height * scale), Image.Resampling.LANCZOS)
    output = BytesIO()
    crop.convert("RGB").save(output, format="JPEG", quality=95)
    payload = output.getvalue()
    import hashlib
    return f"data:image/jpeg;base64,{base64.b64encode(payload).decode('ascii')}", hashlib.sha256(payload).hexdigest()


def _is_text_block(block: ExtractedBlock) -> bool:
    cls = block.class_name.lower()
    return any(name in cls for name in TEXT_CLASSES) and bool(block.text.strip())


def _reading_order(block: ExtractedBlock) -> tuple[int, float, float]:
    spanning = (block.bbox.x2 - block.bbox.x1) > 0.65
    if spanning and block.bbox.y1 < 0.25:
        return (0, block.bbox.y1, block.bbox.x1)
    if spanning and block.bbox.y2 > 0.85:
        return (3, block.bbox.y1, block.bbox.x1)
    return (1 if (block.bbox.x1 + block.bbox.x2) / 2 < 0.52 else 2, block.bbox.y1, block.bbox.x1)


def _trim_repeated_prefix(previous: str, current: str) -> str:
    previous_words = [match.group(0).lower() for match in re.finditer(r"[\w’'-]+", previous)]
    current_matches = list(re.finditer(r"[\w’'-]+", current))
    current_words = [match.group(0).lower() for match in current_matches]
    for size in range(min(100, len(previous_words), len(current_words)), 4, -1):
        if previous_words[-size:] == current_words[:size]:
            return current[current_matches[size - 1].end():].lstrip(" \n.,;:")
    return current


def apply_corrections(page: ParsedPage, reports: list[CropCorrection]) -> ParsedPage:
    for report in reports:
        if report.status == "corrected" and 0 <= report.block_index < len(page.blocks):
            page.blocks[report.block_index].corrected_text = report.corrected_text
            page.blocks[report.block_index].uncertain_spans = report.uncertain_spans
    corrected_blocks = sorted((block for block in page.blocks if _is_text_block(block)), key=_reading_order)
    parts: list[str] = []
    for block in corrected_blocks:
        text = block.corrected_text or block.text
        trimmed = _trim_repeated_prefix(parts[-1], text) if parts else text
        if trimmed:
            parts.append(trimmed)
    page.corrected_body_text = "\n\n".join(parts)
    return page


def select_correction_blocks(page: ParsedPage) -> set[int]:
    selected: set[int] = set()
    columns: dict[int, list[tuple[float, int]]] = {0: [], 1: []}
    for index, block in enumerate(page.blocks):
        if not _is_text_block(block):
            continue
        column = 0 if (block.bbox.x1 + block.bbox.x2) / 2 < 0.52 else 1
        columns[column].append((block.bbox.y1, index))
        tokens = re.findall(r"[A-Za-z]{2,}", block.text)
        odd = sum(not re.search(r"[aeiouyAEIOUY]", token) or len(token) > 24 for token in tokens)
        if compute_vocabulary_validity(block.text) < 0.35 or (tokens and odd / len(tokens) > 0.12):
            selected.add(index)
        if "section-header" in block.class_name.lower():
            selected.add(index)
    for rows in columns.values():
        if rows:
            selected.add(min(rows)[1])
    return selected


def correct_page_crops(
    page: ParsedPage,
    image_path: Path,
    client: ChatClient,
    model_id: str,
    block_indices: set[int] | None = None,
) -> tuple[ParsedPage, list[CropCorrection]]:
    """Correct selected text crops while retaining their raw Parse transcription."""
    image = Image.open(image_path)
    selected_indices = block_indices if block_indices is not None else {
        index for index, block in enumerate(page.blocks) if _is_text_block(block)
    }
    prompt = (
        "Transcribe only the visible historical printed text in this crop. Use the supplied OCR as a hint, not as authority. "
        "Preserve spelling, capitalization, punctuation, numbers, and line-break hyphens exactly when visible. Do not modernize, "
        "summarize, complete, or explain the text. Write [unclear] or [unclear:best reading] for unreadable spans. Return only "
        "JSON with keys transcription (string) and uncertain_spans (array of strings). OCR hint:\n"
    )
    jobs = []
    for index, block in enumerate(page.blocks):
        if index in selected_indices and _is_text_block(block):
            data_url, crop_hash = _crop_data_url(image, block)
            jobs.append((index, block, data_url, crop_hash))

    def correct_one(index: int, block: ExtractedBlock, data_url: str, crop_hash: str) -> CropCorrection:
        raw_output = ""
        try:
            messages = [{"role": "user", "content": [
                {"type": "text", "text": prompt + block.text},
                {"type": "image_url", "image_url": {"url": data_url}},
            ]}]
            try:
                response = client.complete(messages, max_tokens=8192, extra_body={"temperature": 0})
            except ServiceError as exc:
                if "incomplete" not in str(exc).lower():
                    raise
                response = client.complete(messages, max_tokens=16384, extra_body={"temperature": 0})
            raw_output = _response_text(response)
            corrected, uncertain = _parse_correction(raw_output)
            return CropCorrection(
                block_index=index, bbox=block.bbox.model_dump(), raw_text=block.text,
                corrected_text=corrected, uncertain_spans=uncertain, status="corrected",
                model_id=model_id, crop_sha256=crop_hash, raw_model_output=raw_output,
            )
        except Exception as exc:
            return CropCorrection(
                block_index=index, bbox=block.bbox.model_dump(), raw_text=block.text,
                corrected_text="", status="failed", model_id=model_id,
                crop_sha256=crop_hash, raw_model_output=raw_output, error=str(exc),
            )

    reports: list[CropCorrection] = []
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = {executor.submit(correct_one, *job): job[0] for job in jobs}
        for future in as_completed(futures):
            reports.append(future.result())
    reports.sort(key=lambda report: report.block_index)
    return apply_corrections(page, reports), reports
