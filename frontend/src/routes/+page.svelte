<script>
	import rawData from '../lib/challenge_data.json';

	let activeTab = 'entries';
	let searchQuery = '';
	let selectedEntryId = rawData.entries[0]?.entry_id || '';
	let filterStatus = 'all'; // all, compared, excluded, plates

	let detailCache = {};
	let selectedDetail = null;
	let detailLoading = false;
	let detailError = '';

	let latexReport = null;

	$: plateCount = rawData.stats.plates_recovered || rawData.entries.filter(e => e.is_plate).length;

	$: filteredEntries = rawData.entries.filter((entry) => {
		const matchesQuery = entry.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
			entry.entry_id.toLowerCase().includes(searchQuery.toLowerCase());
		if (filterStatus === 'compared') return matchesQuery && entry.compared;
		if (filterStatus === 'excluded') return matchesQuery && !entry.compared;
		if (filterStatus === 'plates') return matchesQuery && entry.is_plate;
		return matchesQuery;
	});

	$: selectedEntry = rawData.entries.find((e) => e.entry_id === selectedEntryId) || rawData.entries[0];
	$: if (selectedEntryId) loadDetail(selectedEntryId);

	async function loadDetail(id) {
		if (detailCache[id]) {
			selectedDetail = detailCache[id];
			detailError = '';
			return;
		}
		detailLoading = true;
		detailError = '';
		try {
			const res = await fetch(`data/entries/${id}.json`);
			if (!res.ok) throw new Error(`HTTP ${res.status}`);
			detailCache[id] = await res.json();
			selectedDetail = detailCache[id];
		} catch (e) {
			selectedDetail = null;
			detailError = `Could not load entry detail (works over HTTP/Pages; file:// may block fetch): ${e.message}`;
		} finally {
			detailLoading = false;
		}
	}

	function selectEntry(id) {
		selectedEntryId = id;
	}

	async function loadLatexReport() {
		if (latexReport) return;
		try {
			const res = await fetch('latex/compile_report.json');
			if (res.ok) latexReport = await res.json();
		} catch { latexReport = { compiled: 0, failed: [], error: 'report unavailable' }; }
	}
	$: if (activeTab === 'latex') loadLatexReport();

	function pdfAvailable(entry) {
		if (!latexReport) return true;
		return !(latexReport.failed || []).some(f => f.file === `${entry.entry_id}.tex`)
			&& (latexReport.compiled > 0 || !latexReport.error);
	}
</script>

<svelte:head>
	<title>Britannica 1771 vs Wikipedia — Toicen's Chosen</title>
</svelte:head>

<div class="app-container">
	<!-- Hero Header -->
	<header class="hero">
		<div class="hero-glow"></div>
		<div class="header-content">
			<div class="title-group">
				<div class="team-chip">Toicen's Chosen</div>
				<h1>Encyclopaedia Britannica <span class="year">1771</span> ⟷ Wikipedia</h1>
				<p class="subtitle">Nemotron Agentic Multimodal Comparison Challenge · Nebius AI Cloud</p>
			</div>
			<div class="badge-group">
				<span class="badge">Nemotron-3.5-Parse</span>
				<span class="badge">Nemotron-Embed/Rerank-VL</span>
				<span class="badge">Nemotron-3.5-Super-VL</span>
				<span class="badge">Hermes Agent</span>
			</div>
		</div>

		<!-- Stat Cards -->
		<div class="stats-grid">
			<div class="stat-card">
				<div class="stat-value">{rawData.stats.entries_total}</div>
				<div class="stat-label">Extracted Entries</div>
			</div>
			<div class="stat-card accent-sky">
				<div class="stat-value">{rawData.stats.compared_count}</div>
				<div class="stat-label">Matched & Compared</div>
			</div>
			<div class="stat-card accent-amber">
				<div class="stat-value">{rawData.stats.excluded_count}</div>
				<div class="stat-label">Excluded (Accounted)</div>
			</div>
			<div class="stat-card accent-green">
				<div class="stat-value">{rawData.topics.length}</div>
				<div class="stat-label">Topic Clusters</div>
			</div>
			<div class="stat-card accent-violet">
				<div class="stat-value">{plateCount}</div>
				<div class="stat-label">Copperplates (Super-VL)</div>
			</div>
			<div class="stat-card accent-rose">
				<div class="stat-value">{rawData.agent_runs.length}</div>
				<div class="stat-label">Hermes Agent Runs</div>
			</div>
		</div>

		<!-- Tab Navigation -->
		<nav class="nav-tabs">
			<button class:active={activeTab === 'entries'} on:click={() => activeTab = 'entries'}>
				Dual-Pane Reader
			</button>
			<button class:active={activeTab === 'plots'} on:click={() => activeTab = 'plots'}>
				Analysis Plots
			</button>
			<button class:active={activeTab === 'exclusions'} on:click={() => activeTab = 'exclusions'}>
				Exclusions <span class="tab-count">{rawData.exclusions.length}</span>
			</button>
			<button class:active={activeTab === 'latex'} on:click={() => activeTab = 'latex'}>
				LaTeX Documents <span class="tab-count">{rawData.entries.length}</span>
			</button>
			<button class:active={activeTab === 'agent'} on:click={() => activeTab = 'agent'}>
				Agent Runs <span class="tab-count">{rawData.agent_runs.length}</span>
			</button>
			<button class:active={activeTab === 'evaluate'} on:click={() => activeTab = 'evaluate'}>
				Case Studies
			</button>
		</nav>
	</header>

	<!-- Main Content Area -->
	<main class="main-content">
		{#if activeTab === 'entries'}
			<div class="dual-pane-layout">
				<!-- Sidebar Entries List -->
				<aside class="sidebar">
					<div class="filter-box">
						<input
							type="text"
							placeholder="Search entries..."
							bind:value={searchQuery}
							class="search-input"
						/>
						<div class="filter-pills">
							<button class:active-pill={filterStatus === 'all'} on:click={() => filterStatus = 'all'}>All</button>
							<button class:active-pill={filterStatus === 'compared'} on:click={() => filterStatus = 'compared'}>Compared</button>
							<button class:active-pill={filterStatus === 'excluded'} on:click={() => filterStatus = 'excluded'}>Excluded</button>
							<button class:active-pill={filterStatus === 'plates'} on:click={() => filterStatus = 'plates'}>Plates</button>
						</div>
					</div>

					<div class="entry-list">
						{#each filteredEntries as item (item.entry_id)}
							<div
								class="entry-item"
								class:selected={item.entry_id === selectedEntryId}
								on:click={() => selectEntry(item.entry_id)}
								on:keydown={(e) => e.key === 'Enter' && selectEntry(item.entry_id)}
								tabindex="0"
								role="button"
							>
								<div class="entry-header">
									<strong class="entry-title">{item.title}</strong>
									{#if item.compared}
										<span class="status-tag compared">Compared</span>
									{:else if item.is_plate}
										<span class="status-tag plate">Plate</span>
									{:else}
										<span class="status-tag excluded">{item.match_status}</span>
									{/if}
								</div>
								<div class="entry-meta">
									{item.character_count.toLocaleString()} chars · Vol {item.volume_id}
								</div>
							</div>
						{/each}
					</div>
				</aside>

				<!-- Entry Detail Viewer -->
				<section class="detail-view">
					{#if selectedEntry}
						<div class="detail-header">
							<div>
								<h2>{selectedEntry.title}</h2>
								<div class="detail-sub">
									<code>{selectedEntry.entry_id}</code> · Vol {selectedEntry.volume_id}
									{#if selectedEntry.wikipedia_title}· matched to <em>{selectedEntry.wikipedia_title}</em>{/if}
								</div>
							</div>
							<div class="detail-tags">
								<a href={selectedEntry.latex_file} class="download-link" download>.tex</a>
								{#if pdfAvailable(selectedEntry)}
									<a href={selectedEntry.pdf_file} class="download-link pdf" target="_blank" rel="noopener noreferrer">.pdf</a>
								{/if}
							</div>
						</div>

						{#if detailLoading}
							<div class="loading-notice"><span class="spinner"></span>Loading entry detail…</div>
						{:else if detailError}
							<p class="error-notice">{detailError}</p>
						{:else if selectedDetail}
							<div class="comparison-grid">
								<!-- Left Pane: Historical Britannica -->
								<div class="pane britannica-pane">
									<div class="pane-header">
										<h3><span class="pane-icon gold">◆</span> Historical Britannica (1771)</h3>
										<span class="char-count">{selectedEntry.character_count.toLocaleString()} chars</span>
									</div>
									<div class="source-info">
										<p><strong>Source Pages:</strong> {selectedDetail.entry.source_pages.join(', ')}</p>
										<p><strong>Rows:</strong> {selectedDetail.entry.source_row_indices.join(', ')}</p>
										{#if selectedDetail.comparison}
											<p><strong>Text SHA256:</strong> <code>{selectedDetail.comparison.britannica_sha256?.slice(0, 20)}…</code></p>
										{/if}
									</div>

									{#each selectedDetail.scans as scan}
										{#if scan.path}
											<figure class="scan-figure">
												<img src={scan.path} alt="Britannica scan {scan.filename}" loading="lazy" />
												<figcaption>{scan.filename} · sha256 {scan.image_sha256.slice(0, 12)}…</figcaption>
											</figure>
										{/if}
									{/each}

									{#if selectedDetail.entry.metadata?.visual_annotation}
										<div class="annotation-box">
											<h4>Super-VL Plate Annotation</h4>
											<p><strong>{selectedDetail.entry.metadata.visual_annotation.plate_title}</strong></p>
											<p>{selectedDetail.entry.metadata.visual_annotation.description}</p>
										</div>
									{/if}

									<div class="text-content historical-text">
										{#if selectedDetail.entry.text.trim()}
											{selectedDetail.entry.text}
										{:else}
											<p class="empty-notice"><em>(No textual body extracted; historical illustration plate or non-text scan.)</em></p>
										{/if}
									</div>
								</div>

								<!-- Right Pane: Matched Wikipedia Article -->
								<div class="pane wikipedia-pane">
									<div class="pane-header">
										<h3><span class="pane-icon sky">◆</span> Wikipedia (Modern Snapshot)</h3>
										{#if selectedDetail.wikipedia.available}
											<a href={selectedDetail.wikipedia.url} target="_blank" rel="noopener noreferrer" class="wiki-link">
												Open Article ↗
											</a>
										{/if}
									</div>

									{#if selectedDetail.wikipedia.available}
										<div class="source-info">
											<p><strong>Title:</strong> {selectedDetail.wikipedia.title}</p>
											<p><strong>Page ID:</strong> {selectedDetail.wikipedia.page_id} · <strong>Revision:</strong> {selectedDetail.wikipedia.revision_id}</p>
											{#if selectedDetail.wikipedia.text_sha256}
												<p><strong>Text SHA256:</strong> <code>{selectedDetail.wikipedia.text_sha256.slice(0, 20)}…</code></p>
											{/if}
											{#if selectedDetail.wikipedia.truncated}
												<p class="truncated-note">Cached article text is truncated.</p>
											{/if}
										</div>
										<div class="text-content modern-text">
											{selectedDetail.wikipedia.text}
										</div>
									{:else}
										<div class="unmatched-box">
											<h4>No Wikipedia Match Accepted</h4>
											<p><strong>Status:</strong> {selectedEntry.match_status}</p>
											{#if selectedDetail.exclusion}
												<p><strong>Exclusion:</strong> {selectedDetail.exclusion.reason}</p>
											{/if}
											<p>This entry was excluded from lexical comparison according to calibrated threshold rules.</p>
										</div>
									{/if}
								</div>
							</div>

							<!-- Comparison Evidence Section -->
							{#if selectedDetail.comparison}
								<div class="evidence-section">
									<h3>Generated Comparison <span class="derived-tag">derived</span></h3>
									<div class="metrics-row">
										<div class="metric">
											<span class="m-val">{selectedDetail.comparison.length_ratio}</span>
											<span class="m-lbl">Length Ratio (Wiki/Brit)</span>
										</div>
										{#if selectedDetail.comparison.metrics?.cosine_embedding != null}
											<div class="metric">
												<span class="m-val">{selectedDetail.comparison.metrics.cosine_embedding}</span>
												<span class="m-lbl">Nemotron Embedding Cosine</span>
											</div>
										{/if}
										{#if selectedDetail.comparison.metrics?.jaccard_normalized != null}
											<div class="metric">
												<span class="m-val">{selectedDetail.comparison.metrics.jaccard_normalized.toFixed(3)}</span>
												<span class="m-lbl">Jaccard (normalized)</span>
											</div>
										{:else if selectedDetail.comparison.metrics?.jaccard_similarity != null}
											<div class="metric">
												<span class="m-val">{selectedDetail.comparison.metrics.jaccard_similarity.toFixed(3)}</span>
												<span class="m-lbl">Jaccard Sim</span>
											</div>
										{/if}
										{#if selectedDetail.comparison.topic_id != null}
											<div class="metric wide">
												<span class="m-val">Topic #{selectedDetail.comparison.topic_id}</span>
												<span class="m-lbl">{(selectedDetail.comparison.topic_terms || []).join(' · ')}</span>
											</div>
										{/if}
									</div>

									{#if selectedDetail.comparison.claims?.length}
										<div class="claims-list">
											<h4>Cited Comparative Claims ({selectedDetail.comparison.claims.length})</h4>
											{#each selectedDetail.comparison.claims as claim}
												<div class="claim-item" class:factual={claim.claim_type === 'factual'}>
													<span class="claim-badge">{claim.claim_type}{claim.label ? ` · ${claim.label}` : ''}</span>
													<p class="claim-text">{claim.claim_text}</p>
													<small class="claim-citation">
														Britannica pages: {(claim.britannica_pages || []).join(', ') || 'n/a'}
														{#if claim.britannica_quote} · “{claim.britannica_quote.slice(0, 120)}{claim.britannica_quote.length > 120 ? '…' : ''}”{/if}
														<br/>Wikipedia: page {claim.wikipedia_page_id} rev {claim.wikipedia_revision_id}
														{#if claim.wikipedia_quote} · “{claim.wikipedia_quote.slice(0, 120)}{claim.wikipedia_quote.length > 120 ? '…' : ''}”{/if}
													</small>
												</div>
											{/each}
										</div>
									{/if}

									{#if selectedDetail.comparison.aligned_chunks?.length}
										<div class="chunks-list">
											<h4>Aligned Passage Pairs ({selectedDetail.comparison.aligned_chunks.length})</h4>
											{#each selectedDetail.comparison.aligned_chunks as chunk}
												<div class="chunk-pair">
													<div class="chunk-side">
														<small>Britannica §{chunk.britannica_chunk_index} · sim {chunk.similarity?.toFixed(3)}</small>
														<p>{chunk.britannica_excerpt}</p>
													</div>
													<div class="chunk-side wiki">
														<small>Wikipedia §{chunk.wikipedia_chunk_index}</small>
														<p>{chunk.wikipedia_excerpt}</p>
													</div>
												</div>
											{/each}
										</div>
									{/if}

									{#if selectedDetail.comparison.text_changes?.length}
										<div class="changes-list">
											<h4>Normalization Audit ({selectedDetail.comparison.text_changes.length} transformations)</h4>
											<table class="audit-table">
												<thead><tr><th>Rule</th><th>Original</th><th>Normalized</th></tr></thead>
												<tbody>
													{#each selectedDetail.comparison.text_changes.slice(0, 50) as change}
														<tr>
															<td><code>{change.rule || change.kind || ''}</code></td>
															<td>{change.original || change.before || ''}</td>
															<td>{change.normalized || change.after || change.replacement || ''}</td>
														</tr>
													{/each}
												</tbody>
											</table>
											{#if selectedDetail.comparison.text_changes.length > 50}
												<small>Showing 50 of {selectedDetail.comparison.text_changes.length}.</small>
											{/if}
										</div>
									{/if}
								</div>
							{/if}
						{/if}
					{/if}
				</section>
			</div>
		{:else if activeTab === 'plots'}
			<div class="section-container">
				<h2>Comparison Analysis Plots</h2>
				<p class="tab-desc">Deterministic SVGs generated by the compare stage; document counts verified in the run record.</p>
				<div class="plots-grid">
					{#each rawData.plots as plot}
						<div class="plot-card">
							<h3>{plot.file.split('/').pop()}</h3>
							{#if plot.plotted != null}<p class="plot-meta">{plot.plotted}/{plot.expected} documents plotted</p>{/if}
							<img src={plot.file} alt={plot.file} />
						</div>
					{:else}
						<p>No plots found. Run the compare stage first.</p>
					{/each}
				</div>
			</div>
		{:else if activeTab === 'exclusions'}
			<div class="section-container">
				<h2>Exclusion Audit <span class="h2-count">{rawData.exclusions.length}</span></h2>
				<p class="tab-desc">Every extracted entry is accounted for: compared, or excluded with a recorded reason.</p>
				<div class="table-box">
					<table class="data-table">
						<thead>
							<tr><th>Entry ID</th><th>Title</th><th>Reason</th><th>Match Status</th><th>Chars</th></tr>
						</thead>
						<tbody>
							{#each rawData.exclusions as ex}
								<tr>
									<td><code>{ex.entry_id}</code></td>
									<td>{ex.britannica_title}</td>
									<td><span class="status-tag excluded">{ex.reason}</span></td>
									<td>{ex.match_status}</td>
									<td>{ex.character_count}</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else if activeTab === 'latex'}
			<div class="section-container">
				<h2>Compiled LaTeX Deliverables <span class="h2-count">{rawData.entries.length}</span></h2>
				<p class="tab-desc">
					Each entry compiles to PDF with the embedded source scan.
					{#if latexReport}
						Compiled: <strong>{latexReport.compiled}</strong>
						{#if latexReport.failed?.length}· Failed: <strong>{latexReport.failed.length}</strong>{/if}
						{#if latexReport.error}· {latexReport.error}{/if}
					{/if}
					· <a href="latex/compile_report.json" target="_blank" rel="noopener noreferrer">compile report</a>
				</p>
				{#if latexReport?.failed?.length}
					<div class="unmatched-box">
						<h4>Compile Failures (recorded honestly)</h4>
						{#each latexReport.failed as f}<p><code>{f.file}</code></p>{/each}
					</div>
				{/if}

				<div class="table-box">
					<table class="data-table">
						<thead>
							<tr><th>Entry ID</th><th>Title</th><th>Volume</th><th>Characters</th><th>Documents</th></tr>
						</thead>
						<tbody>
							{#each rawData.entries as e}
								<tr>
									<td><code>{e.entry_id}</code></td>
									<td><strong>{e.title}</strong></td>
									<td>{e.volume_id}</td>
									<td>{e.character_count}</td>
									<td>
										<a href={e.latex_file} class="action-btn" download>.tex</a>
										{#if pdfAvailable(e)}
											<a href={e.pdf_file} class="action-btn pdf" target="_blank" rel="noopener noreferrer">.pdf</a>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else if activeTab === 'agent'}
			<div class="section-container">
				<h2>Hermes Comparison Agent Runs</h2>
				<p class="tab-desc">Recorded headless runs with Nemotron-3.5-Super-VL; raw transcripts preserved per run.</p>

				<div class="runs-list">
					{#each rawData.agent_runs as run}
						<div class="run-card" class:success={run.status === 'success'}>
							<div class="run-header">
								<span class="run-name">{run.run}</span>
								<span class="run-status-badge {run.status}">{run.status.toUpperCase()}</span>
							</div>
							{#if run.query}<p class="run-query"><strong>Query:</strong> {run.query}</p>{/if}
							{#if run.model}<p class="run-meta"><strong>Model:</strong> {run.model}{#if run.exit_code != null} · exit {run.exit_code}{/if}</p>{/if}
							<div class="tool-tags">
								<strong>Tools:</strong>
								{#each run.tool_calls as tool}
									<span class="tool-tag">{tool}</span>
								{/each}
							</div>
							{#if run.final_text}
								<div class="final-answer">
									<strong>Final answer:</strong>
									<p>{run.final_text}</p>
								</div>
							{/if}
							{#if run.file}
								<a href={run.file} class="action-btn" download>Run record JSON</a>
							{/if}
						</div>
					{/each}
				</div>
			</div>
		{:else if activeTab === 'evaluate'}
			<div class="section-container">
				<h2>Case Studies & Evaluation</h2>
				<p class="tab-desc">Three success cases and three failure cases recorded from real agent runs.</p>
				<div class="case-grid">
					{#each rawData.case_studies as cs}
						<a href={cs.file} class="case-card" target="_blank" rel="noopener noreferrer">
							<strong>{cs.title}</strong>
							<span>{cs.file.split('/').pop()}</span>
						</a>
					{/each}
				</div>
				{#if rawData.submission_doc}
					<p><a href={rawData.submission_doc} class="action-btn" target="_blank" rel="noopener noreferrer">Submission report</a></p>
				{/if}
			</div>
		{/if}
	</main>

	<footer class="footer">
		<span class="footer-team">Toicen's Chosen</span>
		<span class="footer-sep">·</span>
		<span>Nemotron Agentic AI Challenge — Britannica 1771 ⟷ Wikipedia</span>
		<span class="footer-sep">·</span>
		<span>Dataset rev <code>{(rawData.dataset_manifest.revision || '').slice(0, 8)}</code> · {rawData.dataset_manifest.scans_total} scans</span>
	</footer>
</div>

<style>
	:root {
		--bg: #0a0f1e;
		--panel: #121a30;
		--panel-deep: #0c1326;
		--border: #233252;
		--text: #e7edf9;
		--muted: #8ba0c4;
		--gold: #d8ab4e;
		--gold-dim: rgba(216, 171, 78, 0.12);
		--sky: #56b8f5;
		--sky-dim: rgba(86, 184, 245, 0.10);
		--violet: #a78bfa;
		--green: #34d399;
		--amber: #fbbf24;
		--rose: #fb7185;
		--serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
		--mono: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
	}

	:global(body) {
		margin: 0;
		font-family: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
		background: var(--bg);
		color: var(--text);
	}
	:global(*) { scrollbar-width: thin; scrollbar-color: #334468 transparent; }
	:global(*::-webkit-scrollbar) { width: 8px; height: 8px; }
	:global(*::-webkit-scrollbar-thumb) { background: #334468; border-radius: 4px; }

	.app-container { min-height: 100vh; display: flex; flex-direction: column; }

	/* ---------- Hero ---------- */
	.hero {
		position: relative;
		background:
			radial-gradient(1000px 300px at 20% -80px, rgba(216, 171, 78, 0.14), transparent 60%),
			radial-gradient(800px 300px at 85% -60px, rgba(86, 184, 245, 0.12), transparent 60%),
			linear-gradient(180deg, #141d38 0%, #0e1730 100%);
		border-bottom: 1px solid var(--border);
		padding: 2rem 2.5rem 0;
		overflow: hidden;
	}
	.hero::after {
		content: "";
		position: absolute; left: 0; right: 0; bottom: 0;
		height: 2px;
		background: linear-gradient(90deg, transparent, var(--gold) 30%, var(--sky) 70%, transparent);
		opacity: 0.5;
	}

	.header-content {
		display: flex; justify-content: space-between; align-items: flex-start;
		flex-wrap: wrap; gap: 1rem;
	}

	.team-chip {
		display: inline-block;
		font-size: 0.7rem; font-weight: 700; letter-spacing: 0.16em;
		text-transform: uppercase;
		color: var(--gold);
		border: 1px solid rgba(216, 171, 78, 0.45);
		background: var(--gold-dim);
		padding: 0.3rem 0.8rem; border-radius: 9999px;
		margin-bottom: 0.75rem;
	}

	h1 {
		margin: 0;
		font-family: var(--serif);
		font-size: 2.1rem; font-weight: 700; color: #f4f7fd;
		letter-spacing: 0.01em;
	}
	h1 .year { color: var(--gold); }
	.subtitle { margin: 0.4rem 0 0; color: var(--muted); font-size: 0.95rem; }

	.badge-group { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.badge {
		background: rgba(86, 184, 245, 0.12); color: var(--sky);
		border: 1px solid rgba(86, 184, 245, 0.35);
		padding: 0.28rem 0.7rem; border-radius: 9999px;
		font-size: 0.72rem; font-weight: 600; letter-spacing: 0.02em;
	}

	/* ---------- Stats ---------- */
	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
		gap: 1rem; margin: 1.75rem 0;
	}
	.stat-card {
		background: rgba(12, 19, 38, 0.75);
		border: 1px solid var(--border);
		border-top: 3px solid #3a4a72;
		border-radius: 10px; padding: 1rem;
		text-align: center;
		backdrop-filter: blur(4px);
		transition: transform 0.15s ease, border-color 0.15s ease;
	}
	.stat-card:hover { transform: translateY(-2px); }
	.stat-card.accent-sky { border-top-color: var(--sky); }
	.stat-card.accent-amber { border-top-color: var(--amber); }
	.stat-card.accent-green { border-top-color: var(--green); }
	.stat-card.accent-violet { border-top-color: var(--violet); }
	.stat-card.accent-rose { border-top-color: var(--rose); }
	.stat-value {
		font-size: 2.1rem; font-weight: 800; color: #f6f9ff;
		font-variant-numeric: tabular-nums;
	}
	.stat-label { color: var(--muted); font-size: 0.78rem; margin-top: 0.3rem; letter-spacing: 0.02em; }

	/* ---------- Tabs ---------- */
	.nav-tabs { display: flex; gap: 0.4rem; overflow-x: auto; padding-bottom: 0; }
	.nav-tabs button {
		background: transparent; border: 1px solid transparent;
		border-bottom: none;
		border-radius: 8px 8px 0 0;
		color: var(--muted); padding: 0.7rem 1.15rem;
		font-size: 0.9rem; font-weight: 600; cursor: pointer;
		transition: all 0.15s; white-space: nowrap;
	}
	.nav-tabs button:hover { color: var(--text); background: rgba(86, 184, 245, 0.06); }
	.nav-tabs button.active {
		color: var(--sky);
		background: var(--panel);
		border-color: var(--border);
		position: relative;
	}
	.nav-tabs button.active::after {
		content: ""; position: absolute; left: 0; right: 0; bottom: -1px;
		height: 2px; background: var(--panel);
	}
	.tab-count {
		font-size: 0.7rem; background: rgba(86,184,245,0.15); color: var(--sky);
		padding: 0.1rem 0.4rem; border-radius: 9999px; margin-left: 0.25rem;
	}

	.main-content { flex: 1; padding: 1.75rem 2.5rem; }

	/* ---------- Reader layout ---------- */
	.dual-pane-layout {
		display: grid;
		grid-template-columns: 330px 1fr;
		gap: 1.5rem;
		height: calc(100vh - 360px);
		min-height: 560px;
	}

	.sidebar {
		background: var(--panel); border: 1px solid var(--border);
		border-radius: 12px; display: flex; flex-direction: column; overflow: hidden;
	}
	.filter-box { padding: 1rem; border-bottom: 1px solid var(--border); }
	.search-input {
		width: 100%; box-sizing: border-box;
		background: var(--panel-deep); border: 1px solid var(--border); color: var(--text);
		padding: 0.55rem 0.8rem; border-radius: 8px; font-size: 0.9rem;
		transition: border-color 0.15s;
	}
	.search-input:focus { outline: none; border-color: var(--sky); }
	.filter-pills { display: flex; gap: 0.4rem; margin-top: 0.75rem; }
	.filter-pills button {
		flex: 1; background: var(--panel-deep); border: 1px solid var(--border); color: var(--muted);
		font-size: 0.72rem; padding: 0.4rem 0.2rem; border-radius: 6px; cursor: pointer;
		transition: all 0.15s;
	}
	.filter-pills button:hover { color: var(--text); }
	.filter-pills button.active-pill {
		background: rgba(86, 184, 245, 0.15); color: var(--sky);
		font-weight: 700; border-color: rgba(86, 184, 245, 0.4);
	}

	.entry-list { flex: 1; overflow-y: auto; }
	.entry-item {
		padding: 0.8rem 1rem; border-bottom: 1px solid var(--border);
		border-left: 3px solid transparent;
		cursor: pointer; transition: background 0.12s, border-color 0.12s;
	}
	.entry-item:hover { background: rgba(86, 184, 245, 0.05); }
	.entry-item.selected { background: var(--sky-dim); border-left-color: var(--sky); }
	.entry-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.25rem; }
	.entry-title { font-size: 0.92rem; color: #eef3fc; font-family: var(--serif); }
	.entry-meta { font-size: 0.72rem; color: var(--muted); font-variant-numeric: tabular-nums; }

	.status-tag { font-size: 0.66rem; padding: 0.16rem 0.45rem; border-radius: 5px; font-weight: 700; white-space: nowrap; }
	.status-tag.compared { background: rgba(52, 211, 153, 0.15); color: var(--green); border: 1px solid rgba(52,211,153,0.3); }
	.status-tag.excluded { background: rgba(251, 191, 36, 0.12); color: var(--amber); border: 1px solid rgba(251,191,36,0.3); }
	.status-tag.plate { background: rgba(167, 139, 250, 0.15); color: var(--violet); border: 1px solid rgba(167,139,250,0.35); }

	/* ---------- Detail ---------- */
	.detail-view {
		background: var(--panel); border: 1px solid var(--border);
		border-radius: 12px; padding: 1.5rem 1.75rem; overflow-y: auto;
	}
	.detail-header {
		display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;
		border-bottom: 1px solid var(--border); padding-bottom: 1rem; margin-bottom: 1.25rem;
	}
	.detail-header h2 { margin: 0; color: #f4f7fd; font-family: var(--serif); font-size: 1.5rem; }
	.detail-sub { margin-top: 0.35rem; font-size: 0.8rem; color: var(--muted); }
	.detail-sub code { font-family: var(--mono); font-size: 0.72rem; }
	.detail-sub em { color: var(--sky); font-style: normal; }
	.detail-tags { display: flex; gap: 0.6rem; align-items: center; flex-shrink: 0; }

	.download-link {
		background: rgba(86,184,245,0.14); color: var(--sky);
		border: 1px solid rgba(86,184,245,0.4);
		text-decoration: none; padding: 0.4rem 0.85rem; border-radius: 7px;
		font-size: 0.82rem; font-weight: 700; font-family: var(--mono);
		transition: background 0.15s;
	}
	.download-link:hover { background: rgba(86,184,245,0.25); }
	.download-link.pdf { background: rgba(251,113,133,0.12); color: var(--rose); border-color: rgba(251,113,133,0.4); }
	.download-link.pdf:hover { background: rgba(251,113,133,0.22); }

	.loading-notice { color: var(--muted); display: flex; align-items: center; gap: 0.6rem; }
	.spinner {
		width: 14px; height: 14px; border-radius: 50%;
		border: 2px solid var(--border); border-top-color: var(--sky);
		animation: spin 0.8s linear infinite; display: inline-block;
	}
	@keyframes spin { to { transform: rotate(360deg); } }
	.error-notice { color: #fca5a5; }

	.comparison-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
	@media (max-width: 1100px) { .comparison-grid { grid-template-columns: 1fr; } }

	.pane {
		border-radius: 10px; padding: 1.25rem 1.4rem;
		display: flex; flex-direction: column;
	}
	.britannica-pane {
		background: linear-gradient(180deg, rgba(216,171,78,0.06), rgba(216,171,78,0.02)), var(--panel-deep);
		border: 1px solid rgba(216, 171, 78, 0.30);
	}
	.wikipedia-pane {
		background: linear-gradient(180deg, rgba(86,184,245,0.06), rgba(86,184,245,0.02)), var(--panel-deep);
		border: 1px solid rgba(86, 184, 245, 0.30);
	}
	.pane-header {
		display: flex; justify-content: space-between; align-items: center;
		border-bottom: 1px solid var(--border); padding-bottom: 0.7rem; margin-bottom: 0.75rem;
	}
	.pane-header h3 { margin: 0; font-size: 1.05rem; color: #eef3fc; }
	.pane-icon { font-size: 0.7rem; vertical-align: middle; margin-right: 0.3rem; }
	.pane-icon.gold { color: var(--gold); }
	.pane-icon.sky { color: var(--sky); }
	.char-count { font-size: 0.72rem; color: var(--muted); }

	.source-info p { margin: 0.22rem 0; font-size: 0.82rem; color: var(--muted); word-break: break-all; }
	.source-info code { font-size: 0.72rem; font-family: var(--mono); color: var(--gold); }
	.wikipedia-pane .source-info code { color: var(--sky); }
	.truncated-note { color: var(--amber); }

	.scan-figure { margin: 0.85rem 0; }
	.scan-figure img {
		display: block; width: 100%; max-height: 420px; object-fit: contain;
		background: #f4efe4;
		border: 6px solid #f8f4e8; border-radius: 4px;
		box-shadow: 0 6px 24px rgba(0,0,0,0.45);
	}
	.scan-figure figcaption {
		font-size: 0.68rem; color: var(--muted); margin-top: 0.4rem;
		word-break: break-all; font-family: var(--mono);
	}

	.annotation-box {
		background: rgba(167, 139, 250, 0.08);
		border: 1px solid rgba(167, 139, 250, 0.35);
		border-radius: 8px; padding: 0.75rem 1rem; margin: 0.85rem 0; font-size: 0.85rem;
	}
	.annotation-box h4 { margin: 0 0 0.4rem; color: var(--violet); font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.06em; }
	.annotation-box p { margin: 0.25rem 0; color: #d6cee9; }

	.text-content {
		margin-top: 1rem; line-height: 1.65; font-size: 0.92rem;
		max-height: 420px; overflow-y: auto; white-space: pre-wrap;
	}
	.historical-text { font-family: var(--serif); color: #e8dfc8; font-size: 0.95rem; }
	.modern-text { color: #d7e2f2; }
	.empty-notice { color: var(--muted); }

	/* ---------- Evidence section ---------- */
	.evidence-section {
		margin-top: 1.75rem; border-top: 1px dashed var(--border); padding-top: 1.25rem;
	}
	.evidence-section h3 { margin: 0 0 0.9rem; color: #f4f7fd; font-size: 1.1rem; }
	.derived-tag {
		font-size: 0.62rem; background: rgba(251,191,36,0.12); color: var(--amber);
		border: 1px solid rgba(251,191,36,0.35);
		padding: 0.18rem 0.45rem; border-radius: 4px; vertical-align: middle;
		text-transform: uppercase; letter-spacing: 0.08em; font-weight: 700;
	}

	.metrics-row { display: flex; gap: 0.9rem; flex-wrap: wrap; }
	.metric {
		background: var(--panel-deep); border: 1px solid var(--border);
		padding: 0.6rem 0.9rem; border-radius: 8px;
		display: flex; flex-direction: column; gap: 0.2rem;
	}
	.metric.wide { max-width: 340px; }
	.m-val { font-weight: 800; font-size: 1.15rem; color: #f6f9ff; font-variant-numeric: tabular-nums; }
	.m-lbl { font-size: 0.68rem; color: var(--muted); }

	.claims-list h4, .chunks-list h4, .changes-list h4 {
		color: var(--sky); font-size: 0.9rem; margin: 1.25rem 0 0.6rem;
		letter-spacing: 0.02em;
	}
	.claim-item {
		background: var(--panel-deep); border-left: 3px solid #4a5a82;
		padding: 0.6rem 0.9rem; margin-bottom: 0.55rem; border-radius: 0 6px 6px 0;
	}
	.claim-item.factual { border-left-color: var(--green); }
	.claim-badge {
		font-size: 0.62rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.05em;
		background: #2a3a60; color: #c8d4ea; padding: 0.16rem 0.4rem; border-radius: 4px;
	}
	.claim-text { margin: 0.4rem 0; font-size: 0.86rem; color: #e2e9f5; }
	.claim-citation { color: var(--muted); font-size: 0.72rem; line-height: 1.5; }

	.chunk-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; margin-bottom: 0.75rem; }
	@media (max-width: 900px) { .chunk-pair { grid-template-columns: 1fr; } }
	.chunk-side {
		background: var(--panel-deep); border: 1px solid var(--border);
		border-top: 2px solid var(--gold);
		border-radius: 6px; padding: 0.6rem 0.85rem; font-size: 0.8rem;
	}
	.chunk-side.wiki { border-top-color: var(--sky); }
	.chunk-side small { color: var(--gold); font-weight: 600; }
	.chunk-side.wiki small { color: var(--sky); }
	.chunk-side p { margin: 0.3rem 0 0; color: #cdd8ea; max-height: 120px; overflow-y: auto; }

	.audit-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
	.audit-table th, .audit-table td {
		text-align: left; padding: 0.4rem 0.55rem;
		border-bottom: 1px solid var(--border); color: #cdd8ea;
	}
	.audit-table th { color: var(--muted); font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.05em; }
	.audit-table code { font-family: var(--mono); color: var(--gold); }

	.unmatched-box {
		background: rgba(251,191,36,0.05); border: 1px dashed rgba(251,191,36,0.4);
		padding: 1.5rem; border-radius: 10px; text-align: center; margin-top: 1rem;
	}
	.unmatched-box h4 { margin: 0 0 0.5rem; color: var(--amber); }
	.unmatched-box p { margin: 0.3rem 0; color: var(--muted); font-size: 0.85rem; }

	/* ---------- Sections ---------- */
	.section-container h2 { color: #f4f7fd; font-family: var(--serif); font-size: 1.5rem; margin: 0 0 0.4rem; }
	.h2-count {
		font-size: 0.8rem; background: rgba(86,184,245,0.15); color: var(--sky);
		padding: 0.15rem 0.55rem; border-radius: 9999px; vertical-align: middle;
	}
	.tab-desc { color: var(--muted); font-size: 0.9rem; margin-top: 0.4rem; }
	.tab-desc a { color: var(--sky); }

	.plots-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; margin-top: 1.25rem; }
	.plot-card {
		background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 1.25rem;
	}
	.plot-card h3 { margin: 0 0 0.25rem; font-size: 0.95rem; color: #eef3fc; font-family: var(--mono); }
	.plot-meta { margin: 0 0 0.9rem; font-size: 0.78rem; color: var(--muted); }
	.plot-card img { width: 100%; background: #fff; border-radius: 6px; }

	.table-box {
		background: var(--panel); border: 1px solid var(--border);
		border-radius: 12px; overflow: hidden; margin-top: 1.25rem;
	}
	.data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	.data-table th, .data-table td {
		text-align: left; padding: 0.65rem 0.9rem;
		border-bottom: 1px solid var(--border); color: #dfe7f4;
	}
	.data-table tbody tr:hover { background: rgba(86,184,245,0.04); }
	.data-table th {
		background: var(--panel-deep); color: var(--muted);
		font-size: 0.7rem; text-transform: uppercase; letter-spacing: 0.07em;
	}
	.data-table code { font-family: var(--mono); font-size: 0.78rem; color: var(--gold); }

	.action-btn {
		background: rgba(86,184,245,0.14); color: var(--sky);
		border: 1px solid rgba(86,184,245,0.4);
		text-decoration: none; padding: 0.32rem 0.65rem; border-radius: 6px;
		font-size: 0.78rem; font-weight: 700; font-family: var(--mono);
		margin-right: 0.4rem; display: inline-block; transition: background 0.15s;
	}
	.action-btn:hover { background: rgba(86,184,245,0.25); }
	.action-btn.pdf { background: rgba(251,113,133,0.12); color: var(--rose); border-color: rgba(251,113,133,0.4); }
	.action-btn.pdf:hover { background: rgba(251,113,133,0.22); }

	.runs-list { display: flex; flex-direction: column; gap: 1.1rem; margin-top: 1.25rem; }
	.run-card {
		background: var(--panel); border: 1px solid var(--border);
		border-left: 4px solid var(--amber); border-radius: 12px; padding: 1.3rem 1.5rem;
	}
	.run-card.success { border-left-color: var(--green); }
	.run-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
	.run-name { font-family: var(--mono); font-size: 0.8rem; color: #eef3fc; word-break: break-all; }
	.run-status-badge { font-size: 0.68rem; font-weight: 800; padding: 0.22rem 0.6rem; border-radius: 5px; letter-spacing: 0.06em; flex-shrink: 0; }
	.run-status-badge.success { background: rgba(52,211,153,0.15); color: var(--green); border: 1px solid rgba(52,211,153,0.35); }
	.run-status-badge.failure, .run-status-badge.failed { background: rgba(251,113,133,0.12); color: var(--rose); border: 1px solid rgba(251,113,133,0.35); }
	.run-query, .run-meta { font-size: 0.85rem; color: #cdd8ea; margin: 0.6rem 0 0; }
	.run-meta { color: var(--muted); font-size: 0.78rem; }
	.final-answer {
		background: var(--panel-deep); border: 1px solid var(--border);
		border-radius: 8px; padding: 0.85rem 1rem; margin: 0.85rem 0; font-size: 0.85rem;
	}
	.final-answer strong { color: var(--sky); font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; }
	.final-answer p { margin: 0.4rem 0 0; color: #d7e2f2; white-space: pre-wrap; line-height: 1.6; }

	.tool-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin-top: 0.85rem; font-size: 0.78rem; color: var(--muted); }
	.tool-tag {
		background: #2a3a60; color: #d3ddf0;
		padding: 0.22rem 0.55rem; border-radius: 5px;
		font-size: 0.72rem; font-family: var(--mono);
	}

	.case-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.1rem; margin: 1.25rem 0; }
	.case-card {
		background: var(--panel); border: 1px solid var(--border);
		border-left: 3px solid var(--gold);
		border-radius: 10px; padding: 1.1rem 1.25rem;
		text-decoration: none; color: var(--text);
		display: flex; flex-direction: column; gap: 0.45rem;
		transition: border-color 0.15s, transform 0.15s;
	}
	.case-card:hover { border-color: var(--sky); transform: translateY(-2px); }
	.case-card strong { color: #eef3fc; font-size: 0.92rem; }
	.case-card span { color: var(--muted); font-size: 0.72rem; font-family: var(--mono); }

	/* ---------- Footer ---------- */
	.footer {
		border-top: 1px solid var(--border);
		padding: 1.1rem 2.5rem;
		display: flex; gap: 0.7rem; align-items: center; flex-wrap: wrap;
		font-size: 0.78rem; color: var(--muted);
		background: var(--panel-deep);
	}
	.footer-team { color: var(--gold); font-weight: 700; letter-spacing: 0.08em; text-transform: uppercase; font-size: 0.72rem; }
	.footer-sep { color: #3a4a72; }
	.footer code { font-family: var(--mono); font-size: 0.72rem; }

	@media (max-width: 900px) {
		.dual-pane-layout { grid-template-columns: 1fr; height: auto; }
		.sidebar { max-height: 320px; }
		.main-content { padding: 1rem; }
		.hero { padding: 1.25rem 1rem 0; }
	}
</style>
