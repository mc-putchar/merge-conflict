# Milestones

Choose a method with your team and coding agent before you implement each stage.

## Extract

Entry point: `tasks.extract`.

Choose how to turn Parse output into source entries.
Decide how to join continuations.
Separate headers, footers, and page numbers from entry text.
Keep raw model output and scan coordinates with each derived record.

Check source coverage, missing text, and failed or blank scans.
Compare selected outputs with the source images.

Team method: Parse supplies page layout and raw text. Super VL retranscribes selected crops: the first text region in each column, section headings, and blocks with poor OCR quality. The pipeline preserves raw, corrected, and normalized text in separate fields. It records crop hashes, bounding boxes, model output, uncertainty spans, and failures. A page cache is valid only when it covers every crop selected by the current policy.

## Match

Entry point: `tasks.match`.

Choose how to get candidates from the Wikipedia API.
Decide what to embed, how to use the reranker, and when to reject a weak match.
Keep article IDs, revisions, scores, and the evidence for each decision.

Check matches by reading both source documents.
Report omissions and repeated article selections.

Team method: search-query caches are content-addressed by corrected text, model ID, and prompt version. BM25 supplies candidates. Text and multimodal rerankers supply separate evidence. The next acceptance policy will fuse these scores only after the team labels and reviews a stratified 30-case calibration set. Until then, do not describe the threshold as calibrated.

## Compare

Entry point: `tasks.compare`.

Choose the text units and comparison method.
Decide how to handle OCR errors, document lengths, and historical spelling.
Keep a record of text changes and exclusions.

Check that plots count the intended documents.
Support each comparison with source text.

Team method: pair-level metrics use up to about 4,000 relevant Wikipedia characters selected with embedding similarity or a TF-IDF fallback. Whole-article identifiers, hashes, and lengths remain available as source metadata. Chunk alignment uses maximal marginal relevance with a repeated-evidence penalty and a minimum similarity threshold. Claim caches include both source hashes and the Wikipedia revision.

## Agent

Entry point: `tasks.agent`.

Set up Hermes with the required Super model.
Define tools and decide what evidence the agent needs before it answers.
Choose how it should handle missing or conflicting evidence.

Test tool execution and follow-up model calls.
Review citation support and claims about missing or uncertain evidence in the final answer.
Record successful and failed attempts.

## Site

Entry point: `tasks.site`.

Choose a static website layout.
Link scans, extracted documents, matched articles, and analysis results.
Compile your LaTeX documents and include them in the website.

Check links and inspect the rendered documents.
Keep source text and generated comparisons distinct in the page layout.

## Evaluate

Entry point: `tasks.evaluate`.

Choose three success cases and three failure cases from saved runs.
Explain the evidence for each classification.
Keep a failed initial attempt separate from a later repaired result.

Check that another team can reproduce your setup from the submitted repository.
Record the tested code revision, model IDs, data revisions, and known limits.
