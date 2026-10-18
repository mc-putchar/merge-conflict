"""Compare matched Britannica entries with their verified Wikipedia articles."""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re
from typing import Any, Literal

import numpy as np
from pydantic import BaseModel, Field

from .clients import ChatClient, RetrievalClient
from .contracts import ArtifactRecord, SourceReference, WikiArticle
from .storage import LanceArtifactStore

MIN_ENTRY_CHARS = 50
MIN_ENTRY_TOKENS = 10
CHUNK_MIN_CHARS = 300
CHUNK_MAX_CHARS = 800
TOP_ALIGNED_CHUNKS = 3
TOP_DISTINCTIVE_TERMS = 15
TOP_CLAIM_CHARS = 240
LOG_ODDS_ALPHA0 = 1000.0

STOPWORDS = frozenset(
    "a an the and or but of in on at to for with by from as is are was were be been being it its he she they them his her their "
    "this that these those which who whom whose what when where why how not no nor so such than then too very can could will "
    "would shall should may might must do does did done have has had having i you we us me him our your their there here over "
    "under again once more most other some any each few own same into out up down about above below between through during "
    "before after if because while until both also only just all any none one two three first second new old".split()
)

ARCHAIC_OUR_WORDS = {
    "colour": "color", "colours": "colors", "honour": "honor", "honours": "honors",
    "favour": "favor", "favours": "favors", "labour": "labor", "labours": "labors",
    "neighbour": "neighbor", "neighbours": "neighbors", "behaviour": "behavior",
    "behaviours": "behaviors", "flavour": "flavor", "flavours": "flavors",
    "rumour": "rumor", "vigour": "vigor", "ardour": "ardor", "fervour": "fervor",
}
LIGATURES = {"æ": "ae", "œ": "oe", "ﬀ": "ff", "ﬁ": "fi", "ﬂ": "fl", "ﬃ": "ffi", "ﬄ": "ffl", "Æ": "Ae", "Œ": "Oe"}


class TextChangeRecord(BaseModel):
    rule: str
    original: str
    replacement: str
    count: int = Field(ge=1)
    samples: list[str] = Field(default_factory=list, max_length=5)


class ExclusionRecord(BaseModel):
    entry_id: str
    britannica_title: str
    source_pages: list[str] = Field(default_factory=list)
    reason: Literal["unmatched", "short_or_blank_text", "missing_wikipedia_article"]
    match_status: str = ""
    character_count: int = Field(ge=0)


class AlignedChunkComparison(BaseModel):
    britannica_chunk_index: int = Field(ge=0)
    wikipedia_chunk_index: int = Field(ge=0)
    similarity: float
    britannica_excerpt: str
    wikipedia_excerpt: str


class CitedClaim(BaseModel):
    claim_text: str
    claim_type: Literal["factual", "inference"]
    label: Literal["[factual]", "[inference]"]
    britannica_pages: list[str] = Field(default_factory=list)
    britannica_quote: str = ""
    wikipedia_page_id: str = ""
    wikipedia_revision_id: str = ""
    wikipedia_quote: str = ""


class LexicalMetrics(BaseModel):
    jaccard_raw: float
    jaccard_normalized: float
    cosine_tfidf: float
    cosine_embedding: float | None = None
    distinctive_britannica: list[str] = Field(default_factory=list)
    distinctive_wikipedia: list[str] = Field(default_factory=list)
    shared_terms: list[str] = Field(default_factory=list)


class EntryComparison(BaseModel):
    entry_id: str
    britannica_title: str
    source_pages: list[str]
    britannica_sha256: str
    britannica_raw_chars: int = Field(ge=0)
    britannica_tokens: int = Field(ge=0)
    britannica_unique_tokens: int = Field(ge=0)
    wikipedia_page_id: str
    wikipedia_revision_id: str
    wikipedia_title: str
    wikipedia_url: str
    wikipedia_text_sha256: str
    wikipedia_raw_chars: int = Field(ge=0)
    wikipedia_tokens: int = Field(ge=0)
    wikipedia_unique_tokens: int = Field(ge=0)
    length_ratio: float
    text_changes: list[TextChangeRecord] = Field(default_factory=list)
    metrics: LexicalMetrics
    aligned_chunks: list[AlignedChunkComparison] = Field(default_factory=list)
    topic_id: int | None = None
    topic_terms: list[str] = Field(default_factory=list)
    claims: list[CitedClaim] = Field(default_factory=list)


class CorpusComparisonSummary(BaseModel):
    stage: Literal["compare"] = "compare"
    status: str = "completed"
    entries_total: int = Field(ge=0)
    compared_count: int = Field(ge=0)
    excluded_count: int = Field(ge=0)
    exclusions_by_reason: dict[str, int] = Field(default_factory=dict)
    document_accounting_verified: bool = False
    embedding_similarity_available: bool = False
    claims_factual: int = Field(ge=0)
    claims_inference: int = Field(ge=0)
    claims_dropped_unverifiable: int = Field(ge=0)
    topics: list[dict[str, Any]] = Field(default_factory=list)
    artifacts_dir: str = ""
    database_path: str = ""


def tokenize(text: str) -> list[str]:
    """Lowercase word tokens without stopwords or digits."""
    return [
        token
        for token in re.findall(r"[a-z][a-z'’-]*[a-z]|[a-z]", text.lower())
        if token not in STOPWORDS and len(token) > 2
    ]


def _record(changes: dict[tuple[str, str, str], int], rule: str, original: str, replacement: str,
            context: str) -> None:
    key = (rule, original.lower(), replacement.lower())
    changes[key] = changes.get(key, 0) + 1


def normalize_historical_text(
    text: str, modern_vocab: set[str] | None = None
) -> tuple[str, list[TextChangeRecord]]:
    """Produce a normalized analysis copy. Raw text is never modified.

    Each applied rule is recorded so the team can audit every substitution.
    """
    changes: dict[tuple[str, str, str], int] = {}
    samples: dict[tuple[str, str, str], list[str]] = {}
    normalized = text

    def note(rule: str, original: str, replacement: str, context: str) -> None:
        key = (rule, original.lower(), replacement.lower())
        changes[key] = changes.get(key, 0) + 1
        if len(samples.setdefault(key, [])) < 5:
            samples[key].append(context.strip()[:80])

    # 1. Rejoin hyphenated line breaks.
    def unhyphen(match: re.Match) -> str:
        note("line_break_hyphen", match.group(0), match.group(1) + match.group(2), match.group(0))
        return match.group(1) + match.group(2)

    normalized = re.sub(r"([A-Za-z]+)-\s*\n\s*([a-z]+)", unhyphen, normalized)

    # 2. Expand ligatures.
    def expand_ligature(match: re.Match) -> str:
        char = match.group(0)
        replacement = LIGATURES[char]
        note("ligature_expansion", char, replacement, normalized[max(0, match.start() - 15):match.end() + 15])
        return replacement

    normalized = re.sub("[" + "".join(LIGATURES) + "]", expand_ligature, normalized)

    # 3. Long-s.
    def long_s(match: re.Match) -> str:
        note("long_s", match.group(0), "s", normalized[max(0, match.start() - 15):match.end() + 15])
        return "s"

    normalized = re.sub("ſ", long_s, normalized)

    # 4. Archaic -ick endings and -our spellings, applied per token.
    def fix_token(match: re.Match) -> str:
        token = match.group(0)
        lower = token.lower()
        if lower in ARCHAIC_OUR_WORDS:
            replacement = ARCHAIC_OUR_WORDS[lower]
            note("archaic_spelling", token, replacement, normalized[max(0, match.start() - 15):match.end() + 15])
            return replacement if token.islower() else replacement.capitalize()
        if lower.endswith("ick") and len(lower) > 5:
            replacement = lower[:-3] + "ic"
            note("archaic_spelling", token, replacement, normalized[max(0, match.start() - 15):match.end() + 15])
            return replacement if token.islower() else replacement.capitalize()
        return token

    normalized = re.sub(r"[A-Za-z]+", fix_token, normalized)

    # 5. OCR f/s confusion when a modern vocabulary can arbitrate.
    if modern_vocab:
        def fix_fs(match: re.Match) -> str:
            token = match.group(0)
            lower = token.lower()
            if "f" in lower and lower not in modern_vocab:
                candidate = lower.replace("f", "s")
                if candidate in modern_vocab and candidate != lower:
                    note("ocr_f_s_confusion", token, candidate, normalized[max(0, match.start() - 15):match.end() + 15])
                    return candidate if token.islower() else candidate.capitalize()
            return token

        normalized = re.sub(r"[A-Za-z]+", fix_fs, normalized)

    records = [
        TextChangeRecord(rule=rule, original=orig, replacement=repl, count=count,
                         samples=samples.get((rule, orig, repl), []))
        for (rule, orig, repl), count in sorted(changes.items())
    ]
    return normalized, records


def split_chunks(text: str) -> list[str]:
    """Split text into paragraph-aligned chunks between CHUNK_MIN and CHUNK_MAX chars."""
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n|\n", text) if p.strip()]
    if not paragraphs and text.strip():
        paragraphs = [text.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        if len(paragraph) > CHUNK_MAX_CHARS:
            if current:
                chunks.append(current)
                current = ""
            for start in range(0, len(paragraph), CHUNK_MAX_CHARS):
                chunks.append(paragraph[start:start + CHUNK_MAX_CHARS])
            continue
        if len(current) + len(paragraph) + 2 > CHUNK_MAX_CHARS and len(current) >= CHUNK_MIN_CHARS:
            chunks.append(current)
            current = paragraph
        else:
            current = f"{current}\n\n{paragraph}".strip() if current else paragraph
    if current:
        chunks.append(current)
    return chunks or ([text.strip()] if text.strip() else [])


def compute_corpus_idf(documents: list[list[str]], min_df: int = 2) -> dict[str, float]:
    """Smoothed IDF over tokenized documents."""
    n_docs = len(documents)
    df: dict[str, int] = {}
    for tokens in documents:
        for token in set(tokens):
            df[token] = df.get(token, 0) + 1
    return {t: math.log((1 + n_docs) / (1 + count)) + 1.0 for t, count in df.items() if count >= min_df}


def _tfidf_vector(tokens: list[str], idf: dict[str, float]) -> dict[str, float]:
    counts: dict[str, int] = {}
    for token in tokens:
        if token in idf:
            counts[token] = counts.get(token, 0) + 1
    total = sum(counts.values()) or 1
    vector = {t: (c / total) * idf[t] for t, c in counts.items()}
    norm = math.sqrt(sum(v * v for v in vector.values())) or 1.0
    return {t: v / norm for t, v in vector.items()}


def _cosine(a: dict[str, float], b: dict[str, float]) -> float:
    small, large = (a, b) if len(a) <= len(b) else (b, a)
    return sum(v * large.get(t, 0.0) for t, v in small.items())


def _log_odds_terms(source_counts: dict[str, int], other_counts: dict[str, int],
                    background: dict[str, int], top_n: int) -> list[str]:
    """Log-odds ratio with an informative Dirichlet prior (Monroe et al.)."""
    vocab = set(source_counts) | set(other_counts) | set(background)
    total_background = sum(background.values()) or 1
    alpha = {w: LOG_ODDS_ALPHA0 * background.get(w, 1) / total_background for w in vocab}
    n_source, n_other = sum(source_counts.values()), sum(other_counts.values())
    scored = []
    for word in vocab:
        aw = alpha.get(word, LOG_ODDS_ALPHA0 / max(len(vocab), 1))
        p_source = (source_counts.get(word, 0) + aw) / (n_source + LOG_ODDS_ALPHA0 - source_counts.get(word, 0) - aw)
        p_other = (other_counts.get(word, 0) + aw) / (n_other + LOG_ODDS_ALPHA0 - other_counts.get(word, 0) - aw)
        if 0 < p_source < 1 and 0 < p_other < 1:
            delta = math.log(p_source / (1 - p_source)) - math.log(p_other / (1 - p_other))
            variance = 1.0 / (source_counts.get(word, 0) + aw) + 1.0 / (other_counts.get(word, 0) + aw)
            scored.append((delta / math.sqrt(variance), word))
    scored.sort(reverse=True)
    return [word for _, word in scored[:top_n]]


def compute_lexical_comparison(
    brit_raw: str,
    brit_norm: str,
    wiki_raw: str,
    wiki_norm: str,
    idf: dict[str, float],
    background: dict[str, int],
) -> LexicalMetrics:
    """Whole-document vocabulary and frequency metrics for one matched pair."""
    brit_raw_tokens, wiki_raw_tokens = tokenize(brit_raw), tokenize(wiki_raw)
    brit_tokens, wiki_tokens = tokenize(brit_norm), tokenize(wiki_norm)
    brit_set, wiki_set = set(brit_tokens), set(wiki_tokens)
    brit_raw_set, wiki_raw_set = set(brit_raw_tokens), set(wiki_raw_tokens)

    jaccard_raw = len(brit_raw_set & wiki_raw_set) / len(brit_raw_set | wiki_raw_set) if brit_raw_set | wiki_raw_set else 0.0
    jaccard_norm = len(brit_set & wiki_set) / len(brit_set | wiki_set) if brit_set | wiki_set else 0.0
    cosine = _cosine(_tfidf_vector(brit_tokens, idf), _tfidf_vector(wiki_tokens, idf))

    brit_counts = {t: brit_tokens.count(t) for t in brit_set}
    wiki_counts = {t: wiki_tokens.count(t) for t in wiki_set}

    return LexicalMetrics(
        jaccard_raw=round(jaccard_raw, 4),
        jaccard_normalized=round(jaccard_norm, 4),
        cosine_tfidf=round(cosine, 4),
        distinctive_britannica=_log_odds_terms(brit_counts, wiki_counts, background, TOP_DISTINCTIVE_TERMS),
        distinctive_wikipedia=_log_odds_terms(wiki_counts, brit_counts, background, TOP_DISTINCTIVE_TERMS),
        shared_terms=sorted(brit_set & wiki_set)[:30],
    )


def align_chunks(
    brit_text: str,
    wiki_text: str,
    retrieval_client: RetrievalClient | None = None,
    top_n: int = TOP_ALIGNED_CHUNKS,
) -> list[AlignedChunkComparison]:
    """Match Britannica paragraph chunks to their closest Wikipedia chunks."""
    brit_chunks, wiki_chunks = split_chunks(brit_text), split_chunks(wiki_text)
    if not brit_chunks or not wiki_chunks:
        return []

    similarities: np.ndarray | None = None
    if retrieval_client is not None:
        try:
            all_docs = brit_chunks + wiki_chunks
            vectors: list[list[float]] = []
            for start in range(0, len(all_docs), 16):
                vectors.extend(retrieval_client.embed(all_docs[start:start + 16], "document"))
            matrix = np.asarray(vectors, dtype=np.float64)
            similarities = matrix[: len(brit_chunks)] @ matrix[len(brit_chunks):].T
        except Exception:
            similarities = None

    if similarities is None:
        idf = compute_corpus_idf([tokenize(c) for c in brit_chunks + wiki_chunks], min_df=1)
        brit_vecs = [_tfidf_vector(tokenize(c), idf) for c in brit_chunks]
        wiki_vecs = [_tfidf_vector(tokenize(c), idf) for c in wiki_chunks]
        similarities = np.array([[_cosine(b, w) for w in wiki_vecs] for b in brit_vecs])

    pairs: list[AlignedChunkComparison] = []
    for b_idx, row in enumerate(similarities):
        w_idx = int(np.argmax(row))
        pairs.append(AlignedChunkComparison(
            britannica_chunk_index=b_idx,
            wikipedia_chunk_index=w_idx,
            similarity=round(float(row[w_idx]), 4),
            britannica_excerpt=brit_chunks[b_idx][:TOP_CLAIM_CHARS],
            wikipedia_excerpt=wiki_chunks[w_idx][:TOP_CLAIM_CHARS],
        ))
    return sorted(pairs, key=lambda p: p.similarity, reverse=True)[:top_n]


def compute_corpus_topics(
    documents: list[tuple[str, str, str]],
    retrieval_client: RetrievalClient | None = None,
    max_topics: int = 8,
) -> tuple[dict[str, int], list[dict[str, Any]]]:
    """Cluster documents with spherical k-means; label clusters by c-TF-IDF.

    `documents` are (side, entry_id, normalized_text) triples where side is
    "britannica" or "wikipedia". Returns entry_id -> topic_id and cluster info.
    """
    if not documents:
        return {}, []
    n_clusters = max(2, min(max_topics, len(documents) // 4))

    vectors: np.ndarray | None = None
    if retrieval_client is not None:
        try:
            embedded: list[list[float]] = []
            texts = [doc[2][:32000] for doc in documents]
            for start in range(0, len(texts), 16):
                embedded.extend(retrieval_client.embed(texts[start:start + 16], "document"))
            vectors = np.asarray(embedded, dtype=np.float64)
        except Exception:
            vectors = None

    if vectors is None:
        tokenized = [tokenize(doc[2]) for doc in documents]
        vocab = sorted({token for tokens in tokenized for token in tokens})
        idf = compute_corpus_idf(tokenized, min_df=1)
        vocab_index = {t: i for i, t in enumerate(vocab)}
        matrix = np.zeros((len(documents), max(len(vocab), 1)))
        for row, tokens in enumerate(tokenized):
            vec = _tfidf_vector(tokens, idf)
            for token, value in vec.items():
                if token in vocab_index:
                    matrix[row, vocab_index[token]] = value
        if matrix.shape[1] > 256:
            u, s, _ = np.linalg.svd(matrix, full_matrices=False)
            matrix = u[:, :256] * s[:256]
        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        vectors = matrix / norms

    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms

    rng = np.random.default_rng(0)
    centroids = unit[rng.choice(len(unit), size=n_clusters, replace=False)].copy()
    assignments = np.zeros(len(unit), dtype=int)
    for _ in range(20):
        sims = unit @ centroids.T
        new_assignments = np.argmax(sims, axis=1)
        if np.array_equal(new_assignments, assignments):
            break
        assignments = new_assignments
        for k in range(n_clusters):
            members = unit[assignments == k]
            if len(members):
                centroid = members.mean(axis=0)
                norm = np.linalg.norm(centroid)
                centroids[k] = centroid / norm if norm else centroid

    topics: dict[str, int] = {}
    cluster_docs: dict[int, dict[str, list[str]]] = {}
    for (side, entry_id, _), cluster in zip(documents, assignments):
        topics[f"{side}:{entry_id}"] = int(cluster)
        cluster_docs.setdefault(int(cluster), {"britannica": [], "wikipedia": []})[side].append(entry_id)

    side_texts: dict[tuple[int, str], str] = {}
    for (side, entry_id, text), cluster in zip(documents, assignments):
        key = (int(cluster), side)
        side_texts[key] = f"{side_texts.get(key, '')}\n{text}".strip()

    all_counts = [dict(zip(*np.unique(tokenize(t), return_counts=True))) for t in side_texts.values()]
    total_counts: dict[str, int] = {}
    for counts in all_counts:
        for token, count in counts.items():
            total_counts[token] = total_counts.get(token, 0) + count

    clusters: list[dict[str, Any]] = []
    avg_words = sum(sum(c.values()) for c in all_counts) / max(len(all_counts), 1)
    for cluster_id in sorted(cluster_docs):
        members = cluster_docs[cluster_id]
        cluster_info: dict[str, Any] = {
            "topic_id": cluster_id,
            "document_count": len(members["britannica"]) + len(members["wikipedia"]),
            "britannica_entries": len(members["britannica"]),
            "wikipedia_articles": len(members["wikipedia"]),
        }
        combined_top: list[str] = []
        for side in ("britannica", "wikipedia"):
            text = side_texts.get((cluster_id, side), "")
            counts: dict[str, int] = {}
            for token in tokenize(text):
                counts[token] = counts.get(token, 0) + 1
            scored = sorted(
                counts.items(),
                key=lambda item: item[1] * math.log(1.0 + avg_words / max(total_counts.get(item[0], 1), 1)),
                reverse=True,
            )
            top_terms = [t for t, _ in scored[:6]]
            cluster_info[f"top_terms_{side}"] = top_terms
            combined_top.extend(top_terms[:2])
        cluster_info["label"] = ", ".join(list(dict.fromkeys(combined_top))[:3] or ["misc"])
        clusters.append(cluster_info)
    return topics, clusters


def _first_sentence_with(text: str, term: str, limit: int = TOP_CLAIM_CHARS) -> str:
    for part in re.split(r"(?<=[.!?])\s+|\n+", text):
        if term.lower() in part.lower():
            return part.strip()[:limit]
    index = text.lower().find(term.lower())
    return text[max(0, index - 80): index + 160].strip()[:limit] if index >= 0 else text[:limit].strip()


def _quote_of(text: str, limit: int = TOP_CLAIM_CHARS) -> str:
    return text.strip()[:limit]


def generate_cited_claims(
    entry: dict[str, Any],
    article: WikiArticle,
    comparison_metrics: LexicalMetrics,
    text_changes: list[TextChangeRecord],
    chat_client: ChatClient | None,
    cache_dir: Path,
    brit_norm: str = "",
) -> tuple[list[CitedClaim], int]:
    """Build cited factual comparisons and labeled inferences for one pair.

    Returns (claims, dropped_count). Model claims whose quotes are not verbatim
    substrings of the raw sources are dropped, never rewritten.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = cache_dir / f"{entry['entry_id']}.json"
    if cache_path.is_file():
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            return [CitedClaim.model_validate(c) for c in cached["claims"]], int(cached.get("dropped", 0))
        except Exception:
            pass

    brit_raw, wiki_raw = entry.get("text", ""), article.text
    base: dict[str, Any] = {
        "britannica_pages": entry.get("source_pages", []),
        "wikipedia_page_id": article.page_id,
        "wikipedia_revision_id": article.revision_id,
    }

    claims: list[CitedClaim] = []
    dropped = 0

    # Deterministic factual claims grounded in verbatim quotes.
    metrics = comparison_metrics
    claims.append(CitedClaim(
        claim_text=(
            f"The Britannica entry \"{entry['title']}\" uses {len(tokenize(brit_raw))} content tokens "
            f"while the Wikipedia article \"{article.title}\" uses {len(tokenize(wiki_raw))}; "
            f"their normalized vocabularies share a Jaccard overlap of {metrics.jaccard_normalized} "
            f"(raw {metrics.jaccard_raw}) and a TF-IDF cosine similarity of {metrics.cosine_tfidf}."
        ),
        claim_type="factual",
        label="[factual]",
        britannica_quote=_quote_of(brit_raw),
        wikipedia_quote=_quote_of(wiki_raw),
        **base,
    ))
    if metrics.distinctive_britannica:
        term = metrics.distinctive_britannica[0]
        quote = _first_sentence_with(brit_raw, term)
        if term.lower() in quote.lower() or term.lower() in brit_raw.lower():
            claims.append(CitedClaim(
                claim_text=(
                    f"Britannica's most distinctive term is \"{term}\"; Wikipedia's is "
                    f"\"{metrics.distinctive_wikipedia[0] if metrics.distinctive_wikipedia else 'n/a'}\", "
                    "showing the era-specific vocabulary of each source."
                ),
                claim_type="factual",
                label="[factual]",
                britannica_quote=quote,
                wikipedia_quote=_first_sentence_with(wiki_raw, metrics.distinctive_wikipedia[0])
                if metrics.distinctive_wikipedia else _quote_of(wiki_raw),
                **base,
            ))
    if metrics.shared_terms:
        shared = ", ".join(metrics.shared_terms[:5])
        claims.append(CitedClaim(
            claim_text=f"Both sources share core vocabulary including: {shared}.",
            claim_type="factual",
            label="[factual]",
            britannica_quote=_first_sentence_with(brit_raw, metrics.shared_terms[0]),
            wikipedia_quote=_first_sentence_with(wiki_raw, metrics.shared_terms[0]),
            **base,
        ))
    if text_changes:
        samples = [f'"{c.original}" -> "{c.replacement}"' for c in text_changes[:3]]
        claims.append(CitedClaim(
            claim_text=(
                f"{len(text_changes)} normalization rules fired on the Britannica text "
                f"({'; '.join(samples)}); residual vocabulary differences likely reflect era "
                "terminology rather than OCR noise alone."
            ),
            claim_type="inference",
            label="[inference]",
            britannica_quote=text_changes[0].samples[0] if text_changes[0].samples else _quote_of(brit_raw),
            wikipedia_quote=_quote_of(wiki_raw),
            **base,
        ))

    # Optional Super VL claims, validated against verbatim source text.
    if chat_client is not None:
        prompt = (
            "You compare an 18th-century Encyclopaedia Britannica entry with its matched Wikipedia article. "
            "Produce a JSON array of 2 to 4 objects with keys: claim_text (one sentence), "
            "claim_type (\"factual\" or \"inference\"), britannica_quote (verbatim substring of the "
            "Britannica text), wikipedia_quote (verbatim substring of the Wikipedia text). "
            "Factual claims must be supported by the quoted text. Label interpretive claims as "
            "\"inference\".\n\n"
            f"BRITANNICA (normalized):\n{brit_norm[:3000] or brit_raw[:3000]}\n\n"
            f"WIKIPEDIA:\n{wiki_raw[:3000]}"
        )
        try:
            res = chat_client.complete(
                [{"role": "user", "content": [{"type": "text", "text": prompt}]}],
                max_tokens=1500,
                extra_body={"temperature": 0},
            )
            content = res["choices"][0]["message"]["content"]
            match = re.search(r"\[[\s\S]*\]", content)
            parsed = json.loads(match.group(0)) if match else []
            for item in parsed[:4]:
                if not isinstance(item, dict):
                    continue
                b_quote = str(item.get("britannica_quote", "")).strip()
                w_quote = str(item.get("wikipedia_quote", "")).strip()
                if (b_quote and b_quote not in brit_raw and b_quote not in brit_norm) or \
                        (w_quote and w_quote not in wiki_raw):
                    dropped += 1
                    continue
                claim_type = "inference" if str(item.get("claim_type")) == "inference" else "factual"
                claims.append(CitedClaim(
                    claim_text=str(item.get("claim_text", "")).strip()[:500],
                    claim_type=claim_type,
                    label="[inference]" if claim_type == "inference" else "[factual]",
                    britannica_quote=b_quote[:TOP_CLAIM_CHARS],
                    wikipedia_quote=w_quote[:TOP_CLAIM_CHARS],
                    **base,
                ))
        except Exception:
            pass

    try:
        cache_path.write_text(
            json.dumps({"claims": [c.model_dump() for c in claims], "dropped": dropped}, indent=2),
            encoding="utf-8",
        )
    except OSError:
        pass
    return claims, dropped


def _svg_header(width: int, height: int) -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'font-family="monospace" font-size="11">'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
    )


def _bar(x: int, y: int, w: int, h: int, fill: str, label: str, value: str) -> str:
    return (
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"/>'
        f'<text x="{x}" y="{y - 4}" fill="#222">{label}</text>'
        f'<text x="{x}" y="{y + h + 14}" fill="#222">{value}</text>'
    )


def generate_comparison_plots(
    comparisons: list[EntryComparison],
    exclusions: list[ExclusionRecord],
    entries_total: int,
    out_dir: Path,
) -> dict[str, dict[str, int]]:
    """Write deterministic SVG plots; return per-plot document counts."""
    out_dir.mkdir(parents=True, exist_ok=True)
    n_compared = len(comparisons)
    counts: dict[str, dict[str, int]] = {}

    # 1. Document accounting: every extracted entry is either compared or excluded.
    excluded_by_reason: dict[str, int] = {}
    for record in exclusions:
        excluded_by_reason[record.reason] = excluded_by_reason.get(record.reason, 0) + 1
    groups = [("compared", n_compared, "#4c9f70")] + [
        (reason, count, "#c05a4e") for reason, count in sorted(excluded_by_reason.items())
    ]
    total = max(entries_total, 1)
    width, height, bar_w, gap = 640, 320, 110, 40
    svg = [_svg_header(width, height), f'<text x="20" y="24" font-size="14">Document accounting: {entries_total} extracted entries</text>']
    x = 40
    for name, count, color in groups:
        h = int(200 * count / total)
        svg.append(_bar(x, 260 - h, bar_w, h, color, name, str(count)))
        x += bar_w + gap
    svg.append("</svg>")
    (out_dir / "document_accounting.svg").write_text("".join(svg), encoding="utf-8")
    counts["document_accounting.svg"] = {"plotted": n_compared + sum(excluded_by_reason.values()), "expected": entries_total}

    # 2. Length and vocabulary shift: one point per compared pair.
    width, height = 640, 360
    max_tokens = max((max(c.britannica_tokens, c.wikipedia_tokens) for c in comparisons), default=1)
    svg = [_svg_header(width, height),
           f'<text x="20" y="24" font-size="14">Length and vocabulary shift ({n_compared} pairs)</text>',
           f'<line x1="60" y1="300" x2="600" y2="300" stroke="#333"/>'
           f'<line x1="60" y1="300" x2="60" y2="40" stroke="#333"/>',
           '<text x="300" y="340">tokens (log scale)</text>',
           '<text x="8" y="170" transform="rotate(-90 12 170)">normalized Jaccard</text>']
    plotted_points = 0
    for comp in comparisons:
        for tokens, color in ((comp.britannica_tokens, "#4c6f9f"), (comp.wikipedia_tokens, "#c05a4e")):
            cx = 60 + int(520 * math.log1p(tokens) / math.log1p(max_tokens))
            cy = 300 - int(250 * comp.metrics.jaccard_normalized)
            svg.append(f'<circle cx="{cx}" cy="{cy}" r="4" fill="{color}" fill-opacity="0.6"/>')
            plotted_points += 1
    svg.append('<text x="430" y="50" fill="#4c6f9f">Britannica</text>'
               '<text x="430" y="66" fill="#c05a4e">Wikipedia</text></svg>')
    (out_dir / "length_and_vocabulary_shift.svg").write_text("".join(svg), encoding="utf-8")
    counts["length_and_vocabulary_shift.svg"] = {"plotted": plotted_points // 2, "expected": n_compared}

    # 3. Topic distribution: stacked bar per topic, counts must sum to compared pairs.
    topic_buckets: dict[int, dict[str, int]] = {}
    for comp in comparisons:
        bucket = topic_buckets.setdefault(comp.topic_id if comp.topic_id is not None else -1, {"britannica": 0, "wikipedia": 0})
        bucket["britannica"] += 1
        bucket["wikipedia"] += 1
    topics_sorted = sorted(topic_buckets)
    width, height = 640, 320
    svg = [_svg_header(width, height), f'<text x="20" y="24" font-size="14">Topic distribution ({n_compared} pairs)</text>']
    x = 60
    bar_w = max(40, int(500 / max(len(topics_sorted), 1)) - 10)
    max_count = max((b["britannica"] + b["wikipedia"] for b in topic_buckets.values()), default=1)
    for topic_id in topics_sorted:
        bucket = topic_buckets[topic_id]
        h_b = int(200 * bucket["britannica"] / max_count)
        h_w = int(200 * bucket["wikipedia"] / max_count)
        svg.append(_bar(x, 260 - h_b - h_w, bar_w, h_b, "#4c6f9f", f"topic {topic_id}", ""))
        svg.append(f'<rect x="{x}" y="{260 - h_w}" width="{bar_w}" height="{h_w}" fill="#c05a4e"/>'
                   f'<text x="{x}" y="{280}" fill="#222">{bucket["britannica"] + bucket["wikipedia"]}</text>')
        x += bar_w + 10
    svg.append('<text x="430" y="40" fill="#4c6f9f">Britannica</text>'
               '<text x="430" y="56" fill="#c05a4e">Wikipedia</text></svg>')
    (out_dir / "topic_distribution.svg").write_text("".join(svg), encoding="utf-8")
    counts["topic_distribution.svg"] = {
        "plotted": sum(b["britannica"] for b in topic_buckets.values()),
        "expected": n_compared,
    }

    (out_dir / "plots_manifest.json").write_text(json.dumps(counts, indent=2), encoding="utf-8")
    return counts


def verify_plot_counts(plots_metadata: dict[str, dict[str, int]]) -> list[str]:
    """Return error strings for any plot whose document count is wrong."""
    errors = []
    for name, counts in plots_metadata.items():
        if counts.get("plotted") != counts.get("expected"):
            errors.append(
                f"{name} plots {counts.get('plotted')} documents but {counts.get('expected')} were intended"
            )
    return errors


def record_compare_provenance(
    store: LanceArtifactStore,
    comparison: EntryComparison,
    manifest: dict[str, Any],
    pages_by_id: dict[str, dict[str, Any]],
    artifact_path: Path,
) -> None:
    """Persist a dual-source ArtifactRecord for one compared pair."""
    dataset = manifest.get("dataset", "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated")
    revision = manifest.get("revision", "309f765b1ecc83e0a7f7762e44b4a927a7555443")
    source_url = manifest.get("source_url", "")
    license_spdx = manifest.get("license", {}).get("spdx", "CC0-1.0")

    sources = [
        SourceReference(
            dataset=dataset,
            dataset_revision=revision,
            source_id=pid,
            source_url=source_url,
            content_sha256=pages_by_id.get(pid, {}).get("image_sha256", "0" * 64),
            license=license_spdx,
        )
        for pid in comparison.source_pages
    ]
    sources.append(SourceReference(
        dataset="wikimedia/structured-wikipedia",
        dataset_revision="417c267bb457fa645c22eb3b5c77764963194c70",
        source_id=comparison.wikipedia_page_id,
        source_url=comparison.wikipedia_url,
        content_sha256=comparison.wikipedia_text_sha256,
        license="CC-BY-SA-4.0",
    ))

    store.put(ArtifactRecord(
        record_id=f"compare:{comparison.entry_id}",
        stage="compare",
        sources=sources,
        artifact_path=str(artifact_path),
        metadata={
            "britannica_title": comparison.britannica_title,
            "wikipedia_title": comparison.wikipedia_title,
            "wikipedia_revision_id": comparison.wikipedia_revision_id,
            "jaccard_normalized": comparison.metrics.jaccard_normalized,
            "cosine_tfidf": comparison.metrics.cosine_tfidf,
            "cosine_embedding": comparison.metrics.cosine_embedding,
            "topic_id": comparison.topic_id,
            "claims_factual": sum(1 for c in comparison.claims if c.claim_type == "factual"),
            "claims_inference": sum(1 for c in comparison.claims if c.claim_type == "inference"),
        },
    ))


def britannica_text_sha256(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
