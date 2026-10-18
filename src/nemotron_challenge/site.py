"""Static website generation and LaTeX document compilation for challenge deliverables."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from typing import Any

from .config import Settings
from .contracts import ArtifactRecord, SourceReference
from .data import load_manifest
from .storage import LanceArtifactStore


def escape_latex(text: str) -> str:
    """Escape special LaTeX characters in historical and extracted text."""
    if not text:
        return ""
    # Replace backslash first to avoid double-escaping
    text = text.replace("\\", "\\textbackslash{}")
    replacements = [
        ("&", "\\&"),
        ("%", "\\%"),
        ("$", "\\$"),
        ("#", "\\#"),
        ("_", "\\_"),
        ("{", "\\{"),
        ("}", "\\}"),
        ("~", "\\textasciitilde{}"),
        ("^", "\\textasciicircum{}"),
    ]
    for char, escaped in replacements:
        text = text.replace(char, escaped)
    return text


def generate_latex_document(
    entry: dict[str, Any],
    manifest: dict[str, Any],
    pages_by_id: dict[str, dict[str, Any]],
    match_record: dict[str, Any] | None = None,
) -> str:
    """Generate a valid standalone LaTeX document conforming to templates/page.tex."""
    title = entry.get("title", "Untitled Entry")
    escaped_title = escape_latex(title)
    text = entry.get("text", "")
    escaped_text = escape_latex(text) if text.strip() else "\\textit{(No textual content; illustration plate or empty scan.)}"

    source_pages = entry.get("source_pages", [])
    page_items = []
    for pid in source_pages:
        pmeta = pages_by_id.get(pid, {})
        fn = pmeta.get("filename", "unknown")
        sha = pmeta.get("image_sha256", "unknown")
        row = pmeta.get("row_index", "unknown")
        page_items.append(
            f"\\item \\textbf{{Page ID:}} \\texttt{{{escape_latex(pid)}}} \\\\\n"
            f"  \\textbf{{Filename:}} \\texttt{{{escape_latex(fn)}}} \\\\\n"
            f"  \\textbf{{Row Index:}} {row} \\\\\n"
            f"  \\textbf{{SHA256:}} \\texttt{{{sha[:16]}...}}"
        )
    source_pages_tex = "\n".join(page_items) if page_items else "\\item None recorded"

    match_info_tex = ""
    if match_record and match_record.get("selected_candidate"):
        cand = match_record["selected_candidate"]
        wiki_title = escape_latex(cand.get("title", ""))
        wiki_pid = cand.get("page_id", "")
        wiki_rev = cand.get("revision_id", "")
        wiki_url = escape_latex(cand.get("url", ""))
        match_info_tex = (
            f"\\subsection*{{Matched Wikipedia Article}}\n"
            f"\\textbf{{Title:}} {wiki_title} \\\\\n"
            f"\\textbf{{Page ID:}} {wiki_pid} \\\\\n"
            f"\\textbf{{Revision ID:}} {wiki_rev} \\\\\n"
            f"\\textbf{{URL:}} \\url{{{wiki_url}}}\n"
        )

    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")

    return f"""\\documentclass{{article}}
\\usepackage[utf8]{{inputenc}}
\\usepackage[T1]{{fontenc}}
\\usepackage{{hyperref}}
\\usepackage{{geometry}}
\\geometry{{margin=1in}}

\\title{{{escaped_title}}}
\\date{{Encyclopaedia Britannica (1771)}}

\\begin{{document}}
\\maketitle

\\section*{{Historical source}}
\\textbf{{Entry ID:}} \\texttt{{{escape_latex(entry.get("entry_id", ""))}}} \\\\
\\textbf{{Volume ID:}} {entry.get("volume_id", "N/A")} \\\\
\\textbf{{Character Count:}} {entry.get("character_count", len(text))}

\\subsection*{{Extracted Text}}
{escaped_text}

{match_info_tex}

\\section*{{Source record}}
\\begin{{itemize}}
\\item \\textbf{{Dataset:}} \\texttt{{{escape_latex(dataset)}}}
\\item \\textbf{{Dataset Revision:}} \\texttt{{{escape_latex(revision)}}}
{source_pages_tex}
\\end{{itemize}}

\\end{{document}}
"""


def bundle_site_data(work_dir: Path, artifacts_dir: Path) -> dict[str, Any]:
    """Gather all stage outputs into a single JSON payload for SvelteKit."""
    manifest = load_manifest()
    pages_by_id = {page["page_id"]: page for page in manifest.get("pages", [])}

    extract_file = artifacts_dir / "extract" / "entries.json"
    entries = json.loads(extract_file.read_text(encoding="utf-8")) if extract_file.is_file() else []

    matches_file = artifacts_dir / "match" / "matches.json"
    matches = {m["entry_id"]: m for m in json.loads(matches_file.read_text(encoding="utf-8"))} if matches_file.is_file() else {}

    unmatched_file = artifacts_dir / "match" / "unmatched.json"
    unmatched = {u["entry_id"]: u for u in json.loads(unmatched_file.read_text(encoding="utf-8"))} if unmatched_file.is_file() else {}

    compare_summary_file = artifacts_dir / "compare" / "summary.json"
    compare_summary = json.loads(compare_summary_file.read_text(encoding="utf-8")) if compare_summary_file.is_file() else {}

    comparisons_file = artifacts_dir / "compare" / "comparisons.json"
    comparisons = {c["entry_id"]: c for c in json.loads(comparisons_file.read_text(encoding="utf-8"))} if comparisons_file.is_file() else {}

    exclusions_file = artifacts_dir / "compare" / "exclusions.json"
    exclusions = json.loads(exclusions_file.read_text(encoding="utf-8")) if exclusions_file.is_file() else []

    topics_file = artifacts_dir / "compare" / "topics.json"
    topics = json.loads(topics_file.read_text(encoding="utf-8")) if topics_file.is_file() else []

    agent_records_file = artifacts_dir / "agent" / "records.json"
    agent_records = json.loads(agent_records_file.read_text(encoding="utf-8")) if agent_records_file.is_file() else []

    # Assemble comprehensive entry cards
    entry_cards = []
    for entry in entries:
        eid = entry["entry_id"]
        match_info = matches.get(eid)
        comp_info = comparisons.get(eid)
        unmatch_info = unmatched.get(eid)

        entry_cards.append({
            "entry_id": eid,
            "title": entry["title"],
            "text": entry.get("text", ""),
            "character_count": entry.get("character_count", 0),
            "source_pages": entry.get("source_pages", []),
            "source_row_indices": entry.get("source_row_indices", []),
            "volume_id": entry.get("volume_id", ""),
            "is_continuation": entry.get("is_continuation", False),
            "matched": match_info is not None,
            "match_status": (match_info or unmatch_info or {}).get("status", "unmatched"),
            "wikipedia_article": match_info.get("selected_candidate") if match_info else None,
            "comparison": {
                "length_ratio": comp_info.get("length_ratio") if comp_info else None,
                "metrics": comp_info.get("metrics") if comp_info else None,
                "claims": comp_info.get("claims", []) if comp_info else [],
                "topic_id": comp_info.get("topic_id") if comp_info else None,
                "topic_terms": comp_info.get("topic_terms", []) if comp_info else [],
            } if comp_info else None,
            "latex_file": f"latex/{eid}.tex",
        })

    return {
        "dataset_manifest": {
            "dataset": manifest.get("dataset"),
            "revision": manifest.get("revision"),
            "scans_total": len(manifest.get("pages", [])),
        },
        "stats": {
            "entries_total": len(entries),
            "matches_accepted": len(matches),
            "matches_rejected": len(unmatched),
            "compared_count": len(comparisons),
            "excluded_count": len(exclusions),
        },
        "compare_summary": compare_summary,
        "topics": topics,
        "exclusions": exclusions,
        "entries": entry_cards,
        "agent_runs": agent_records,
    }


def build_site(settings: Settings, work_dir: Path) -> dict[str, Any]:
    """Compile LaTeX documents and build the SvelteKit static website."""
    work_dir = Path(work_dir)
    site_dir = work_dir / "site"
    site_dir.mkdir(parents=True, exist_ok=True)
    latex_dir = site_dir / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)

    artifacts_dir = work_dir if (work_dir / "extract").is_dir() else Path("artifacts")
    manifest = load_manifest()
    pages_by_id = {page["page_id"]: page for page in manifest.get("pages", [])}

    extract_file = artifacts_dir / "extract" / "entries.json"
    if not extract_file.is_file():
        raise FileNotFoundError(f"Extract entries not found at {extract_file}. Run extract stage first.")
    entries = json.loads(extract_file.read_text(encoding="utf-8"))

    matches_file = artifacts_dir / "match" / "matches.json"
    matches = {m["entry_id"]: m for m in json.loads(matches_file.read_text(encoding="utf-8"))} if matches_file.is_file() else {}

    # 1. Bundle data for frontend
    data_payload = bundle_site_data(work_dir, artifacts_dir)

    # 2. Write data to frontend static directory and lib directory
    frontend_dir = Path("frontend")
    static_data_dir = frontend_dir / "static" / "data"
    static_data_dir.mkdir(parents=True, exist_ok=True)
    (static_data_dir / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )

    src_lib_dir = frontend_dir / "src" / "lib"
    src_lib_dir.mkdir(parents=True, exist_ok=True)
    (src_lib_dir / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )

    # 3. Run SvelteKit build if frontend directory exists and node/pnpm is available
    svelte_built = False
    build_error = ""
    pnpm_path = shutil.which("pnpm") or shutil.which("npm")
    if frontend_dir.is_dir() and pnpm_path:
        env = {
            **os.environ,
            "BUILD_OUT_DIR": str(site_dir.resolve()),
        }
        cmd = [pnpm_path, "run", "build"]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(frontend_dir),
                capture_output=True,
                text=True,
                timeout=120,
                env=env,
            )
            if proc.returncode == 0:
                svelte_built = True
            else:
                build_error = f"pnpm build exited {proc.returncode}: {proc.stderr[:1000]}"
        except Exception as exc:
            build_error = f"pnpm build failed: {exc}"

    # 4. Generate LaTeX documents for every extracted entry (after Svelte build)
    latex_dir = site_dir / "latex"
    latex_dir.mkdir(parents=True, exist_ok=True)
    latex_count = 0
    for entry in entries:
        eid = entry["entry_id"]
        tex_content = generate_latex_document(entry, manifest, pages_by_id, matches.get(eid))
        (latex_dir / f"{eid}.tex").write_text(tex_content, encoding="utf-8")
        latex_count += 1

    # Also persist site data payload in site_dir/data
    (site_dir / "data").mkdir(parents=True, exist_ok=True)
    (site_dir / "data" / "challenge_data.json").write_text(
        json.dumps(data_payload, indent=2), encoding="utf-8"
    )

    # Ensure index.html exists even if SvelteKit build fails or node isn't available
    index_file = site_dir / "index.html"
    if not index_file.is_file():
        # Fallback clean self-contained HTML
        index_file.write_text(
            f"""<!DOCTYPE html>
<html>
<head><meta charset="utf-8"><title>Britannica vs Wikipedia</title></head>
<body>
<h1>Nemotron Agentic AI Challenge — Deliverables</h1>
<p>Entries: {len(entries)}, Compared: {data_payload['stats']['compared_count']}</p>
<p>LaTeX documents generated: {latex_count}</p>
</body>
</html>""",
            encoding="utf-8",
        )

    # 5. Record artifact provenance to LanceDB
    store = LanceArtifactStore(settings.db_path)
    store.put(ArtifactRecord(
        record_id="site:static",
        stage="site",
        sources=[
            SourceReference(
                dataset=manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated"),
                dataset_revision=manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443"),
                source_id="entries.json",
                source_url="",
                content_sha256="0" * 64,
                license="CC0-1.0",
            )
        ],
        artifact_path=str(site_dir),
        metadata={
            "latex_count": latex_count,
            "svelte_built": svelte_built,
            "entries_total": len(entries),
            "compared_count": data_payload["stats"]["compared_count"],
        },
    ))

    return {
        "stage": "site",
        "status": "completed",
        "latex_documents_generated": latex_count,
        "svelte_built": svelte_built,
        "build_error": build_error,
        "site_dir": str(site_dir),
        "latex_dir": str(latex_dir),
        "database_path": str(settings.db_path),
    }
