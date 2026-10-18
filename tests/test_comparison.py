"""Unit tests for the comparison pipeline components."""
import json

from nemotron_challenge.comparison import (
    EntryComparison, ExclusionRecord, LexicalMetrics,
    align_chunks, compute_corpus_idf, compute_corpus_topics, compute_lexical_comparison,
    generate_cited_claims, generate_comparison_plots, normalize_historical_text,
    record_compare_provenance, select_relevant_wikipedia_scope, tokenize, verify_plot_counts,
)
from nemotron_challenge.storage import LanceArtifactStore


def _mock_article(text: str):
    class Provenance:
        text_sha256 = "d" * 64

    class Article:
        page_id = "42"
        revision_id = "100"
        title = "Test Article"
        url = "https://en.wikipedia.org/wiki/Test"
        provenance = Provenance()

    article = Article()
    article.text = text
    return article


def test_tokenize_removes_stopwords_and_short_tokens():
    tokens = tokenize("The quick brown fox jumps over the lazy dog in the yard.")
    assert "the" not in tokens
    assert "in" not in tokens
    assert "quick" in tokens
    assert "jumps" in tokens


def test_normalize_historical_text_logs_each_rule():
    raw = "The meafure is of publick ufe in con-\nferration of colour and honour. Aſide."
    normalized, changes = normalize_historical_text(raw, modern_vocab={"measure", "use"})

    rules = {c.rule for c in changes}
    assert "line_break_hyphen" in rules
    assert "archaic_spelling" in rules
    assert "ocr_f_s_confusion" in rules
    assert "long_s" in rules

    hyphen = next(c for c in changes if c.rule == "line_break_hyphen")
    assert hyphen.original == "con-\nferration"
    assert hyphen.replacement == "conferration"
    assert hyphen.count >= 1
    assert hyphen.samples

    fs = next(c for c in changes if c.rule == "ocr_f_s_confusion")
    assert fs.original == "meafure"
    assert fs.replacement == "measure"

    long_s = next(c for c in changes if c.rule == "long_s")
    assert long_s.original == "ſ"
    assert long_s.replacement == "s"

    # Raw text is unchanged; normalization produced a separate view.
    assert "meafure" in raw
    assert "measure" in normalized
    assert "public" in normalized
    assert "color" in normalized and "honor" in normalized


def test_normalize_without_vocab_keeps_f_tokens():
    normalized, changes = normalize_historical_text("The fox ran fast.", modern_vocab=None)
    assert "fox" in normalized and "fast" in normalized
    assert all(c.rule != "ocr_f_s_confusion" for c in changes)


def test_compute_lexical_comparison_metrics():
    brit_raw = "The optic nerve carries visual signals to the brain."
    wiki_raw = "The optic nerve transmits visual information from the retina to the brain."
    idf = compute_corpus_idf([tokenize(brit_raw), tokenize(wiki_raw)], min_df=1)
    background = {}
    for tokens in (tokenize(brit_raw), tokenize(wiki_raw)):
        for token in tokens:
            background[token] = background.get(token, 0) + 1

    metrics = compute_lexical_comparison(brit_raw, brit_raw, wiki_raw, wiki_raw, idf, background)
    assert 0.0 <= metrics.jaccard_normalized <= 1.0
    assert metrics.jaccard_normalized > 0.0
    assert metrics.cosine_tfidf > 0.0
    assert "optic" in metrics.shared_terms
    assert metrics.distinctive_britannica or metrics.distinctive_wikipedia


def test_select_relevant_wikipedia_scope_limits_and_filters():
    brit_text = "Optics studies light, lenses, vision, and refraction. " * 20
    wiki_text = (
        "Medieval taxation concerned charters and feudal rents. " * 15
        + "\n\n"
        + "Optics studies light, lenses, refraction, and visual perception. " * 15
        + "\n\n"
        + "Cooking recipes describe bread and vegetable soups. " * 15
    )
    scope = select_relevant_wikipedia_scope(brit_text, wiki_text, max_chars=1000)
    assert scope.character_count <= 1000
    assert "Optics" in scope.text
    assert scope.chunk_indices
    assert scope.similarities[0] > 0.0


def test_align_chunks_finds_closest_paragraphs():
    brit_text = ("Optics is the science of light and vision. " * 12
                 + "\n\nAstronomy studies celestial bodies and their motions. " * 12)
    wiki_text = ("Astronomy is the study of stars, planets, and other celestial bodies. " * 12
                 + "\n\nOptics concerns the behaviour and properties of light. " * 12)
    aligned = align_chunks(brit_text, wiki_text, retrieval_client=None, top_n=2)
    assert len(aligned) >= 1
    assert all(0.0 <= c.similarity <= 1.0 for c in aligned)
    assert all(c.britannica_excerpt and c.wikipedia_excerpt for c in aligned)
    assert len({c.wikipedia_chunk_index for c in aligned}) == len(aligned)


def test_align_chunks_rejects_unrelated_evidence():
    aligned = align_chunks(
        "optics lenses refraction light " * 30,
        "medieval taxation feudal charter monarchy " * 30,
        retrieval_client=None,
    )
    assert aligned == []


def test_generate_cited_claims_deterministic(tmp_path):
    entry = {
        "entry_id": "e1", "title": "OPTICS",
        "text": "Optics treats of light, vision, and the refraction of rays through lenses. " * 4,
        "source_pages": ["britannica:rev:train:1"],
    }
    article = _mock_article(
        "Optics is the branch of physics that studies the behaviour and properties of light. " * 4)
    metrics = compute_lexical_comparison(
        entry["text"], entry["text"], article.text, article.text,
        compute_corpus_idf([tokenize(entry["text"]), tokenize(article.text)], min_df=1),
        {},
    )
    claims, dropped = generate_cited_claims(
        entry, article, metrics, [], chat_client=None, cache_dir=tmp_path, brit_norm=entry["text"])

    assert dropped == 0
    assert claims, "deterministic claims must be produced"
    assert any(c.claim_type == "factual" for c in claims)
    factual = [c for c in claims if c.claim_type == "factual"]
    for claim in factual:
        assert claim.label == "[factual]"
        assert claim.wikipedia_page_id == "42"
        assert claim.wikipedia_revision_id == "100"
        assert claim.britannica_pages == ["britannica:rev:train:1"]
        assert claim.britannica_quote and claim.wikipedia_quote


def test_generate_cited_claims_drops_unverifiable_model_quotes(tmp_path):
    entry = {
        "entry_id": "e2", "title": "LIGHT",
        "text": "Light is radiant energy visible to the eye. " * 4,
        "source_pages": ["p1"],
    }
    article = _mock_article("Light is electromagnetic radiation visible to humans. " * 4)
    metrics = LexicalMetrics(
        jaccard_raw=0.1, jaccard_normalized=0.2, cosine_tfidf=0.3,
        distinctive_britannica=[], distinctive_wikipedia=[], shared_terms=["light"],
    )

    class FakeChat:
        def complete(self, *args, **kwargs):
            return {"choices": [{"message": {"content": json.dumps([
                {"claim_text": "Invented claim.", "claim_type": "factual",
                 "britannica_quote": "THIS QUOTE DOES NOT EXIST IN SOURCE",
                 "wikipedia_quote": "Light is electromagnetic radiation"},
                {"claim_text": "Interpretive claim.", "claim_type": "inference",
                 "britannica_quote": "Light is radiant energy",
                 "wikipedia_quote": "Light is electromagnetic radiation"},
            ])}}]}

    claims, dropped = generate_cited_claims(
        entry, article, metrics, [], chat_client=FakeChat(), cache_dir=tmp_path, brit_norm=entry["text"])

    assert dropped == 1
    assert all("DOES NOT EXIST" not in c.britannica_quote for c in claims)
    assert any(c.claim_type == "inference" and c.label == "[inference]" for c in claims)


def test_compute_corpus_topics_assigns_clusters():
    docs = [
        ("britannica", "e1", "Optics light vision refraction lenses spectrum colour ray"),
        ("wikipedia", "e1", "Optics physics light electromagnetic radiation photon lens"),
        ("britannica", "e2", "Agriculture plough harvest grain cattle soil farming crops"),
        ("wikipedia", "e2", "Agriculture farming crop cultivation livestock soil harvest"),
        ("britannica", "e3", "Astronomy stars planets comets orbits telescopes heavens"),
        ("wikipedia", "e3", "Astronomy celestial objects planets stars galaxies telescope"),
        ("britannica", "e4", "Law courts justice statute verdict plaintiff crown"),
        ("wikipedia", "e4", "Law legal system court statute justice legislature rights"),
    ]
    topic_map, clusters = compute_corpus_topics(docs, retrieval_client=None)
    assert len(topic_map) == len(docs)
    assert all(key in topic_map for key in ("britannica:e1", "wikipedia:e1"))
    total_docs = sum(c["document_count"] for c in clusters)
    assert total_docs == len(docs)
    assert all(c["label"] for c in clusters)


def _sample_comparison() -> EntryComparison:
    return EntryComparison(
        entry_id="e1", britannica_title="OPTICS", source_pages=["p1"],
        britannica_sha256="a" * 64, britannica_raw_chars=500, britannica_tokens=80,
        britannica_unique_tokens=40,
        wikipedia_page_id="42", wikipedia_revision_id="100",
        wikipedia_title="Optics", wikipedia_url="https://en.wikipedia.org/wiki/Optics",
        wikipedia_text_sha256="d" * 64, wikipedia_raw_chars=2000, wikipedia_tokens=300,
        wikipedia_unique_tokens=150, length_ratio=4.0,
        metrics=LexicalMetrics(
            jaccard_raw=0.1, jaccard_normalized=0.25, cosine_tfidf=0.4,
            distinctive_britannica=["optic"], distinctive_wikipedia=["photon"],
            shared_terms=["light"],
        ),
        topic_id=0,
    )


def test_generate_plots_and_verify_counts(tmp_path):
    comparisons = [_sample_comparison()]
    exclusions = [ExclusionRecord(
        entry_id="e2", britannica_title="BLANK", source_pages=["p2"],
        reason="short_or_blank_text", character_count=0)]
    metadata = generate_comparison_plots(comparisons, exclusions, entries_total=2, out_dir=tmp_path)

    assert (tmp_path / "document_accounting.svg").is_file()
    assert (tmp_path / "length_and_vocabulary_shift.svg").is_file()
    assert (tmp_path / "topic_distribution.svg").is_file()
    assert (tmp_path / "plots_manifest.json").is_file()
    assert verify_plot_counts(metadata) == []

    bad = dict(metadata)
    bad["topic_distribution.svg"] = {"plotted": 0, "expected": 1}
    errors = verify_plot_counts(bad)
    assert errors and "topic_distribution.svg" in errors[0]


def test_record_compare_provenance_store(tmp_path):
    comp = _sample_comparison()
    manifest = {
        "dataset": "NationalLibraryOfScotland/encyclopaedia_britannica_illustrated",
        "revision": "309f765b1ecc83e0a7f7762e44b4a927a7555443",
        "source_url": "https://example.com",
        "license": {"spdx": "CC0-1.0"},
    }
    pages_by_id = {"p1": {"image_sha256": "b" * 64}}

    store = LanceArtifactStore(tmp_path / "test.lancedb")
    record_compare_provenance(store, comp, manifest, pages_by_id, tmp_path / "e1.json")

    rec = store.get("compare:e1")
    assert rec is not None
    assert rec.stage == "compare"
    assert len(rec.sources) == 2
    assert rec.sources[0].source_id == "p1"
    assert rec.sources[0].content_sha256 == "b" * 64
    assert rec.sources[1].dataset == "wikimedia/structured-wikipedia"
    assert rec.sources[1].source_id == "42"
    assert rec.sources[1].content_sha256 == "d" * 64
