"""Nemotron challenge plugin: evidence tools over the team's saved artifacts."""
import json
import os
from pathlib import Path
from typing import Any

ANSWER_POLICY = (
    "Answer only from the evidence fields. Cite britannica source_pages and the "
    "wikipedia page_id/revision_id for every factual comparison. If status is not "
    "ok or evidence is missing, say exactly what is missing and do not invent content."
)

EXCERPT_CHARS = 400


def _artifacts_dir() -> Path:
    override = os.environ.get("CHALLENGE_ARTIFACTS_DIR", "").strip()
    return Path(override) if override else Path.cwd() / "artifacts"


def _load_json(path: Path, default: Any) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def _payload(status: str, **fields: Any) -> str:
    return json.dumps({"status": status, "policy": ANSWER_POLICY, **fields})


FIND_SCHEMA = {
    "name": "challenge_find_entry",
    "description": (
        "Find Britannica entries and their matched Wikipedia articles by title or topic word. "
        "Returns entry_ids for use with challenge_compare."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "Title or topic text to search for, e.g. 'optics' or 'agriculture'.",
                "minLength": 1,
                "maxLength": 200,
            },
        },
        "required": ["query"],
        "additionalProperties": False,
    },
}

COMPARE_SCHEMA = {
    "name": "challenge_compare",
    "description": (
        "Return the saved comparison evidence bundle for one entry_id: source citations, "
        "excerpts, vocabulary metrics, and cited factual or inference claims."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "entry_id": {
                "type": "string",
                "description": "Entry identifier returned by challenge_find_entry.",
                "minLength": 1,
                "maxLength": 200,
            },
        },
        "required": ["entry_id"],
        "additionalProperties": False,
    },
}

COVERAGE_SCHEMA = {
    "name": "challenge_check_coverage",
    "description": (
        "Report how many extracted Britannica entries were compared, excluded, or left "
        "unmatched, with the recorded exclusion reasons."
    ),
    "parameters": {"type": "object", "properties": {}, "additionalProperties": False},
}


def handle_find_entry(params: dict[str, Any], **kwargs: Any) -> str:
    """Search extracted entries and match results by title substring."""
    try:
        query = str(params.get("query", "")).strip().lower()
        if not query:
            return _payload("error", error="query is required")

        base = _artifacts_dir()
        entries = _load_json(base / "extract" / "entries.json", [])
        matches = {m.get("entry_id"): m for m in _load_json(base / "match" / "matches.json", [])}
        unmatched = {m.get("entry_id"): m for m in _load_json(base / "match" / "unmatched.json", [])}

        results = []
        for entry in entries:
            title = entry.get("title", "")
            match = matches.get(entry["entry_id"]) or unmatched.get(entry["entry_id"])
            wiki_title = ""
            if match and match.get("selected_candidate"):
                wiki_title = match["selected_candidate"].get("title", "")
            haystack = f"{title} {wiki_title} {entry.get('entry_id', '')}".lower()
            if query in haystack:
                results.append({
                    "entry_id": entry["entry_id"],
                    "britannica_title": title,
                    "matched": bool(match and match.get("matched")),
                    "match_status": match.get("status", "") if match else "no_match_record",
                    "wikipedia_title": wiki_title,
                    "wikipedia_page_id": (match or {}).get("selected_candidate", {}).get("page_id", ""),
                    "source_pages": entry.get("source_pages", []),
                    "character_count": entry.get("character_count", 0),
                })

        if not results:
            return _payload("no_evidence", query=query, results=[],
                            missing=[f"no entry or matched article contains '{query}'"])
        return _payload("ok", query=query, results=results[:15])
    except Exception as exc:  # noqa: BLE001 — handlers must return JSON, never raise
        return _payload("error", error=f"{type(exc).__name__}: {exc}")


def handle_compare(params: dict[str, Any], **kwargs: Any) -> str:
    """Return the saved comparison evidence bundle for one entry."""
    try:
        entry_id = str(params.get("entry_id", "")).strip()
        if not entry_id:
            return _payload("error", error="entry_id is required")

        base = _artifacts_dir()
        compare_file = base / "compare" / f"{entry_id}.json"
        if compare_file.is_file():
            comp = _load_json(compare_file, {})
            claims = [
                {
                    "claim_text": c.get("claim_text", ""),
                    "claim_type": c.get("claim_type", ""),
                    "label": c.get("label", ""),
                    "britannica_pages": c.get("britannica_pages", []),
                    "britannica_quote": c.get("britannica_quote", ""),
                    "wikipedia_page_id": c.get("wikipedia_page_id", ""),
                    "wikipedia_revision_id": c.get("wikipedia_revision_id", ""),
                    "wikipedia_quote": c.get("wikipedia_quote", ""),
                }
                for c in comp.get("claims", [])
            ]
            return _payload(
                "ok",
                entry_id=entry_id,
                britannica={
                    "title": comp.get("britannica_title", ""),
                    "source_pages": comp.get("source_pages", []),
                    "text_sha256": comp.get("britannica_sha256", ""),
                    "excerpt": _load_json(base / "extract" / f"{entry_id}.json", {}).get("text", "")[:EXCERPT_CHARS],
                    "distinctive_terms": comp.get("metrics", {}).get("distinctive_britannica", []),
                },
                wikipedia={
                    "title": comp.get("wikipedia_title", ""),
                    "page_id": comp.get("wikipedia_page_id", ""),
                    "revision_id": comp.get("wikipedia_revision_id", ""),
                    "url": comp.get("wikipedia_url", ""),
                    "text_sha256": comp.get("wikipedia_text_sha256", ""),
                    "distinctive_terms": comp.get("metrics", {}).get("distinctive_wikipedia", []),
                },
                metrics=comp.get("metrics", {}),
                length_ratio=comp.get("length_ratio"),
                topic_terms=comp.get("topic_terms", []),
                claims=claims,
            )

        # No comparison artifact: explain why through the exclusion log.
        exclusions = _load_json(base / "compare" / "exclusions.json", [])
        exclusion = next((e for e in exclusions if e.get("entry_id") == entry_id), None)
        missing = [f"no comparison artifact for entry_id '{entry_id}'"]
        if exclusion:
            missing.append(f"entry excluded: {exclusion.get('reason')}")
        return _payload("no_evidence", entry_id=entry_id, missing=missing,
                        exclusion=exclusion)
    except Exception as exc:  # noqa: BLE001
        return _payload("error", error=f"{type(exc).__name__}: {exc}")


def handle_check_coverage(params: dict[str, Any], **kwargs: Any) -> str:
    """Report document accounting across the compare stage."""
    try:
        base = _artifacts_dir()
        summary = _load_json(base / "compare" / "summary.json", None)
        if summary is None:
            return _payload("no_evidence",
                            missing=["compare stage has not run; artifacts/compare/summary.json absent"])
        exclusions = _load_json(base / "compare" / "exclusions.json", [])
        return _payload(
            "ok",
            entries_total=summary.get("entries_total", 0),
            compared_count=summary.get("compared_count", 0),
            excluded_count=summary.get("excluded_count", 0),
            exclusions_by_reason=summary.get("exclusions_by_reason", {}),
            document_accounting_verified=summary.get("document_accounting_verified", False),
            sample_excluded=[
                {
                    "entry_id": e.get("entry_id"),
                    "britannica_title": e.get("britannica_title"),
                    "reason": e.get("reason"),
                    "match_status": e.get("match_status"),
                }
                for e in exclusions[:10]
            ],
        )
    except Exception as exc:  # noqa: BLE001
        return _payload("error", error=f"{type(exc).__name__}: {exc}")


def register(ctx: Any) -> None:
    """Register the challenge evidence tools through the native Hermes interface."""
    ctx.register_tool(
        name="challenge_find_entry",
        toolset="nemotron_challenge",
        schema=FIND_SCHEMA,
        handler=handle_find_entry,
    )
    ctx.register_tool(
        name="challenge_compare",
        toolset="nemotron_challenge",
        schema=COMPARE_SCHEMA,
        handler=handle_compare,
    )
    ctx.register_tool(
        name="challenge_check_coverage",
        toolset="nemotron_challenge",
        schema=COVERAGE_SCHEMA,
        handler=handle_check_coverage,
    )
