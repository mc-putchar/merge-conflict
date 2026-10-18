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
	<!-- Masthead -->
	<header class="masthead">
		<div class="masthead-inner">
			<div class="team-line">Toicen's Chosen</div>
			<div class="rule-ornament">❦</div>
			<h1>Encyclopaedia Britannica <span class="year">1771</span><br/>
				<span class="versus">and</span> Wikipedia</h1>
			<p class="subtitle">A comparative study of historical and modern reference works<br/>
				<span class="subtitle-models">Nemotron Agentic Multimodal Challenge · Nebius AI Cloud</span></p>
			<div class="model-line">
				Nemotron-3.5-Parse · Nemotron-Embed/Rerank-VL · Nemotron-3.5-Super-VL · Hermes Agent
			</div>

			<!-- Index strip -->
			<div class="stats-strip">
				<div class="stat">
					<div class="stat-value">{rawData.stats.entries_total}</div>
					<div class="stat-label">Extracted Entries</div>
				</div>
				<div class="stat">
					<div class="stat-value">{rawData.stats.compared_count}</div>
					<div class="stat-label">Matched & Compared</div>
				</div>
				<div class="stat">
					<div class="stat-value">{rawData.stats.excluded_count}</div>
					<div class="stat-label">Excluded, Accounted</div>
				</div>
				<div class="stat">
					<div class="stat-value">{rawData.topics.length}</div>
					<div class="stat-label">Topic Clusters</div>
				</div>
				<div class="stat">
					<div class="stat-value">{plateCount}</div>
					<div class="stat-label">Copperplates · Super-VL</div>
				</div>
				<div class="stat">
					<div class="stat-value">{rawData.agent_runs.length}</div>
					<div class="stat-label">Hermes Agent Runs</div>
				</div>
			</div>

			<!-- Tab Navigation -->
			<nav class="nav-tabs">
				<button class:active={activeTab === 'entries'} on:click={() => activeTab = 'entries'}>Reader</button>
				<button class:active={activeTab === 'plots'} on:click={() => activeTab = 'plots'}>Plates & Analysis</button>
				<button class:active={activeTab === 'exclusions'} on:click={() => activeTab = 'exclusions'}>Exclusions</button>
				<button class:active={activeTab === 'latex'} on:click={() => activeTab = 'latex'}>Documents</button>
				<button class:active={activeTab === 'agent'} on:click={() => activeTab = 'agent'}>Agent Runs</button>
				<button class:active={activeTab === 'evaluate'} on:click={() => activeTab = 'evaluate'}>Case Studies</button>
			</nav>
		</div>
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
							placeholder="Search entries…"
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
									<code>{selectedEntry.entry_id}</code> · Vol. {selectedEntry.volume_id}
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
										<h3>Historical Britannica · 1771</h3>
										<span class="char-count">{selectedEntry.character_count.toLocaleString()} chars</span>
									</div>
									<div class="source-info">
										<p><strong>Source Pages:</strong> {selectedDetail.entry.source_pages.join(', ')}</p>
										<p><strong>Rows:</strong> {selectedDetail.entry.source_row_indices.join(', ')}</p>
										{#if selectedDetail.comparison}
											<p><strong>Text SHA-256:</strong> <code>{selectedDetail.comparison.britannica_sha256?.slice(0, 20)}…</code></p>
										{/if}
									</div>

									{#each selectedDetail.scans as scan}
										{#if scan.path}
											<figure class="scan-figure">
												<img src={scan.path} alt="Britannica scan {scan.filename}" loading="lazy" />
												<figcaption>Plate: {scan.filename} · sha-256 {scan.image_sha256.slice(0, 12)}…</figcaption>
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
										<h3>Wikipedia · Modern Snapshot</h3>
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
												<p><strong>Text SHA-256:</strong> <code>{selectedDetail.wikipedia.text_sha256.slice(0, 20)}…</code></p>
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
												<span class="m-lbl">Jaccard Similarity</span>
											</div>
										{/if}
										{#if selectedDetail.comparison.topic_id != null}
											<div class="metric wide">
												<span class="m-val">Topic {selectedDetail.comparison.topic_id}</span>
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
														<br/>Wikipedia: page {claim.wikipedia_page_id} rev. {claim.wikipedia_revision_id}
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
														<small>Britannica §{chunk.britannica_chunk_index} · sim. {chunk.similarity?.toFixed(3)}</small>
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
				<h2>Comparison Analysis</h2>
				<p class="tab-desc">Deterministic figures generated by the compare stage; document counts verified in the run record.</p>
				<div class="plots-grid">
					{#each rawData.plots as plot}
						<div class="plot-card">
							<h3>{plot.file.split('/').pop()}</h3>
							{#if plot.plotted != null}<p class="plot-meta">{plot.plotted} of {plot.expected} documents plotted</p>{/if}
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
				<h2>Compiled Documents <span class="h2-count">{rawData.entries.length}</span></h2>
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
		<span>Nemotron Agentic AI Challenge</span>
		<span class="footer-sep">·</span>
		<span>Dataset rev. <code>{(rawData.dataset_manifest.revision || '').slice(0, 8)}</code> · {rawData.dataset_manifest.scans_total} scans</span>
	</footer>
</div>

<style>
	:root {
		/* Royal encyclopaedia palette: ivory paper, ink, antique gold, oxblood, royal navy */
		--paper: #f4efe3;
		--paper-deep: #ece5d3;
		--panel: #faf7ee;
		--panel-cool: #f2f4f6;
		--ink: #252536;
		--ink-soft: #43435a;
		--muted: #77705d;
		--gold: #96762b;
		--gold-soft: #b39345;
		--oxblood: #6e2c33;
		--navy: #263b5e;
		--border: #d5cbb2;
		--border-dark: #bfb394;
		--sage: #4c7257;
		--display: Didot, "Bodoni MT", "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
		--serif: "Iowan Old Style", "Palatino Linotype", Palatino, Georgia, serif;
		--sans: system-ui, -apple-system, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
		--mono: "SF Mono", ui-monospace, Menlo, Consolas, monospace;
	}

	:global(body) {
		margin: 0;
		font-family: var(--sans);
		background: var(--paper);
		color: var(--ink);
	}
	:global(*) { scrollbar-width: thin; scrollbar-color: var(--border-dark) transparent; }
	:global(*::-webkit-scrollbar) { width: 8px; height: 8px; }
	:global(*::-webkit-scrollbar-thumb) { background: var(--border-dark); border-radius: 4px; }

	.app-container { min-height: 100vh; display: flex; flex-direction: column; }

	/* ---------- Masthead ---------- */
	.masthead {
		background: var(--panel);
		border-bottom: 1px solid var(--border-dark);
		padding: 2.75rem 2rem 0;
		text-align: center;
	}
	.masthead-inner { max-width: 1080px; margin: 0 auto; }

	.team-line {
		font-size: 0.72rem; font-weight: 700;
		letter-spacing: 0.34em; text-transform: uppercase;
		color: var(--oxblood);
	}
	.rule-ornament {
		color: var(--gold); font-size: 1.05rem; margin: 0.5rem 0 0.25rem;
	}
	.rule-ornament::before, .rule-ornament::after {
		content: ""; display: inline-block; vertical-align: middle;
		width: 90px; height: 0; margin: 0 0.9rem;
		border-top: 1px solid var(--gold-soft);
	}

	h1 {
		margin: 0.6rem 0 0;
		font-family: var(--display);
		font-size: 2.9rem; font-weight: 500;
		color: var(--ink); letter-spacing: 0.015em; line-height: 1.12;
	}
	h1 .year { color: var(--gold); font-style: italic; }
	h1 .versus {
		font-size: 1.15rem; font-style: italic; color: var(--muted);
		letter-spacing: 0.06em; font-weight: 400;
	}
	.subtitle {
		margin: 0.9rem 0 0; color: var(--ink-soft);
		font-family: var(--serif); font-style: italic; font-size: 1rem; line-height: 1.5;
	}
	.subtitle-models {
		font-style: normal; font-family: var(--sans);
		font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase;
		color: var(--muted);
	}
	.model-line {
		margin-top: 0.85rem;
		font-size: 0.7rem; letter-spacing: 0.1em;
		color: var(--gold); font-family: var(--serif); font-variant: small-caps;
	}

	/* ---------- Index strip ---------- */
	.stats-strip {
		display: flex; justify-content: center; flex-wrap: wrap;
		margin: 1.9rem auto 0;
		border-top: 1px solid var(--border-dark);
		border-bottom: 1px solid var(--border-dark);
	}
	.stat {
		padding: 0.95rem 1.9rem;
		border-right: 1px solid var(--border);
		min-width: 120px;
	}
	.stat:last-child { border-right: none; }
	.stat-value {
		font-family: var(--display);
		font-size: 1.9rem; font-weight: 500; color: var(--navy);
		font-variant-numeric: tabular-nums; line-height: 1.1;
	}
	.stat-label {
		color: var(--muted); font-size: 0.64rem; margin-top: 0.3rem;
		letter-spacing: 0.14em; text-transform: uppercase;
	}

	/* ---------- Tabs (small-caps contents list) ---------- */
	.nav-tabs {
		display: flex; justify-content: center; gap: 0;
		overflow-x: auto; margin-top: 0;
	}
	.nav-tabs button {
		background: transparent; border: none;
		border-bottom: 2px solid transparent;
		color: var(--muted); padding: 0.85rem 1.3rem;
		font-size: 0.74rem; font-weight: 700;
		letter-spacing: 0.16em; text-transform: uppercase;
		cursor: pointer; transition: color 0.15s, border-color 0.15s;
		white-space: nowrap; font-family: var(--sans);
	}
	.nav-tabs button:hover { color: var(--ink); }
	.nav-tabs button.active {
		color: var(--oxblood);
		border-bottom-color: var(--oxblood);
	}

	.main-content { flex: 1; padding: 1.9rem 2.2rem; max-width: 1560px; margin: 0 auto; width: 100%; box-sizing: border-box; }

	/* ---------- Reader layout ---------- */
	.dual-pane-layout {
		display: grid;
		grid-template-columns: 330px 1fr;
		gap: 1.6rem;
		height: calc(100vh - 400px);
		min-height: 560px;
	}

	.sidebar {
		background: var(--panel); border: 1px solid var(--border);
		display: flex; flex-direction: column; overflow: hidden;
	}
	.filter-box { padding: 0.9rem; border-bottom: 1px solid var(--border); }
	.search-input {
		width: 100%; box-sizing: border-box;
		background: #fffdf7; border: 1px solid var(--border); color: var(--ink);
		padding: 0.5rem 0.7rem; font-size: 0.88rem; border-radius: 2px;
		font-family: var(--serif);
	}
	.search-input:focus { outline: none; border-color: var(--gold-soft); }
	.filter-pills { display: flex; gap: 0; margin-top: 0.7rem; border: 1px solid var(--border); }
	.filter-pills button {
		flex: 1; background: transparent; border: none;
		border-right: 1px solid var(--border);
		color: var(--muted); font-size: 0.66rem; padding: 0.42rem 0.2rem;
		cursor: pointer; letter-spacing: 0.08em; text-transform: uppercase; font-weight: 700;
	}
	.filter-pills button:last-child { border-right: none; }
	.filter-pills button:hover { color: var(--ink); }
	.filter-pills button.active-pill { background: var(--ink); color: var(--panel); }

	.entry-list { flex: 1; overflow-y: auto; }
	.entry-item {
		padding: 0.75rem 1rem; border-bottom: 1px solid var(--border);
		border-left: 3px solid transparent;
		cursor: pointer; transition: background 0.12s, border-color 0.12s;
	}
	.entry-item:hover { background: rgba(150, 118, 43, 0.06); }
	.entry-item.selected { background: rgba(150, 118, 43, 0.11); border-left-color: var(--gold); }
	.entry-header { display: flex; justify-content: space-between; align-items: flex-start; gap: 0.5rem; margin-bottom: 0.2rem; }
	.entry-title { font-size: 0.92rem; color: var(--ink); font-family: var(--serif); font-weight: 600; }
	.entry-meta { font-size: 0.7rem; color: var(--muted); font-variant-numeric: tabular-nums; }

	.status-tag {
		font-size: 0.6rem; padding: 0.16rem 0.42rem; font-weight: 700;
		white-space: nowrap; letter-spacing: 0.08em; text-transform: uppercase;
		border: 1px solid;
	}
	.status-tag.compared { color: var(--sage); border-color: rgba(76,114,87,0.5); background: rgba(76,114,87,0.07); }
	.status-tag.excluded { color: #8a6516; border-color: rgba(138,101,22,0.45); background: rgba(138,101,22,0.06); }
	.status-tag.plate { color: #5e5480; border-color: rgba(94,84,128,0.45); background: rgba(94,84,128,0.07); }

	/* ---------- Detail ---------- */
	.detail-view {
		background: var(--panel); border: 1px solid var(--border);
		padding: 1.5rem 1.75rem; overflow-y: auto;
	}
	.detail-header {
		display: flex; justify-content: space-between; align-items: flex-start; gap: 1rem;
		border-bottom: 2px solid var(--ink); padding-bottom: 0.9rem; margin-bottom: 1.25rem;
	}
	.detail-header h2 {
		margin: 0; color: var(--ink);
		font-family: var(--display); font-size: 1.7rem; font-weight: 500;
	}
	.detail-sub { margin-top: 0.35rem; font-size: 0.8rem; color: var(--muted); font-family: var(--serif); }
	.detail-sub code { font-family: var(--mono); font-size: 0.7rem; }
	.detail-sub em { color: var(--navy); }
	.detail-tags { display: flex; gap: 0.55rem; align-items: center; flex-shrink: 0; }

	.download-link {
		color: var(--navy); border: 1px solid var(--navy);
		text-decoration: none; padding: 0.36rem 0.8rem;
		font-size: 0.78rem; font-weight: 600; font-family: var(--mono);
		transition: all 0.15s; border-radius: 2px;
	}
	.download-link:hover { background: var(--navy); color: var(--panel); }
	.download-link.pdf { color: var(--oxblood); border-color: var(--oxblood); }
	.download-link.pdf:hover { background: var(--oxblood); color: var(--panel); }

	.loading-notice { color: var(--muted); display: flex; align-items: center; gap: 0.6rem; font-family: var(--serif); font-style: italic; }
	.spinner {
		width: 13px; height: 13px; border-radius: 50%;
		border: 2px solid var(--border); border-top-color: var(--gold);
		animation: spin 0.8s linear infinite; display: inline-block;
	}
	@keyframes spin { to { transform: rotate(360deg); } }
	.error-notice { color: var(--oxblood); }

	.comparison-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.6rem; }
	@media (max-width: 1100px) { .comparison-grid { grid-template-columns: 1fr; } }

	.pane { padding: 1.25rem 1.4rem; display: flex; flex-direction: column; }
	.britannica-pane {
		background: #f2ecdc;
		border: 1px solid var(--border-dark);
		border-top: 3px double var(--gold);
	}
	.wikipedia-pane {
		background: var(--panel-cool);
		border: 1px solid #c3ccd8;
		border-top: 3px double var(--navy);
	}
	.pane-header {
		display: flex; justify-content: space-between; align-items: baseline;
		border-bottom: 1px solid var(--border); padding-bottom: 0.65rem; margin-bottom: 0.75rem;
	}
	.britannica-pane .pane-header { border-bottom-color: #cfc2a0; }
	.wikipedia-pane .pane-header { border-bottom-color: #bfc9d6; }
	.pane-header h3 {
		margin: 0; font-size: 0.82rem; color: var(--ink);
		letter-spacing: 0.14em; text-transform: uppercase; font-weight: 700;
	}
	.britannica-pane .pane-header h3 { color: var(--gold); }
	.wikipedia-pane .pane-header h3 { color: var(--navy); }
	.char-count { font-size: 0.7rem; color: var(--muted); }

	.source-info p { margin: 0.22rem 0; font-size: 0.78rem; color: var(--muted); word-break: break-all; }
	.source-info strong { color: var(--ink-soft); font-weight: 600; }
	.source-info code { font-size: 0.68rem; font-family: var(--mono); color: var(--gold); }
	.wikipedia-pane .source-info code { color: var(--navy); }
	.truncated-note { color: #8a6516; }
	.wiki-link {
		color: var(--navy); font-size: 0.78rem; text-decoration: none;
		border-bottom: 1px solid var(--navy);
	}
	.wiki-link:hover { background: rgba(38,59,94,0.08); }

	.scan-figure { margin: 0.9rem 0; text-align: center; }
	.scan-figure img {
		display: inline-block; max-width: 100%; max-height: 420px; object-fit: contain;
		background: #fbf7ea;
		border: 1px solid #fff; outline: 1px solid var(--border-dark);
		padding: 5px;
		box-shadow: 0 3px 14px rgba(60, 50, 25, 0.25);
	}
	.scan-figure figcaption {
		font-size: 0.66rem; color: var(--muted); margin-top: 0.45rem;
		word-break: break-all; font-family: var(--mono);
	}

	.annotation-box {
		background: rgba(94, 84, 128, 0.06);
		border: 1px solid rgba(94, 84, 128, 0.35);
		border-left: 3px solid #5e5480;
		padding: 0.75rem 1rem; margin: 0.85rem 0; font-size: 0.85rem;
	}
	.annotation-box h4 {
		margin: 0 0 0.4rem; color: #5e5480; font-size: 0.7rem;
		text-transform: uppercase; letter-spacing: 0.12em;
	}
	.annotation-box p { margin: 0.25rem 0; color: var(--ink-soft); font-family: var(--serif); }

	.text-content {
		margin-top: 1rem; line-height: 1.7; font-size: 0.92rem;
		max-height: 420px; overflow-y: auto; white-space: pre-wrap;
	}
	.historical-text {
		font-family: var(--serif); color: #3a3524; font-size: 0.96rem;
	}
	.historical-text::first-letter {
		font-family: var(--display); font-size: 2.6em;
		float: left; line-height: 0.85; padding: 0.04em 0.1em 0 0;
		color: var(--oxblood);
	}
	.modern-text { color: #333d4d; font-family: var(--sans); }
	.empty-notice { color: var(--muted); }

	/* ---------- Evidence section ---------- */
	.evidence-section {
		margin-top: 1.75rem; border-top: 1px dashed var(--border-dark); padding-top: 1.25rem;
	}
	.evidence-section h3 {
		margin: 0 0 0.9rem; color: var(--ink);
		font-family: var(--display); font-size: 1.3rem; font-weight: 500;
	}
	.derived-tag {
		font-size: 0.6rem; background: rgba(138,101,22,0.08); color: #8a6516;
		border: 1px solid rgba(138,101,22,0.4);
		padding: 0.18rem 0.45rem; vertical-align: middle;
		text-transform: uppercase; letter-spacing: 0.1em; font-weight: 700;
		font-family: var(--sans); border-radius: 2px;
	}

	.metrics-row { display: flex; gap: 0; flex-wrap: wrap; border: 1px solid var(--border); }
	.metric {
		background: #fffdf7;
		padding: 0.7rem 1.1rem;
		border-right: 1px solid var(--border);
		display: flex; flex-direction: column; gap: 0.2rem;
	}
	.metric:last-child { border-right: none; }
	.metric.wide { max-width: 340px; }
	.m-val {
		font-weight: 500; font-size: 1.3rem; color: var(--navy);
		font-family: var(--display); font-variant-numeric: tabular-nums;
	}
	.m-lbl { font-size: 0.62rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.1em; }

	.claims-list h4, .chunks-list h4, .changes-list h4 {
		color: var(--oxblood); font-size: 0.78rem; margin: 1.4rem 0 0.6rem;
		letter-spacing: 0.12em; text-transform: uppercase;
	}
	.claim-item {
		background: #fffdf7; border: 1px solid var(--border);
		border-left: 3px solid #a89a78;
		padding: 0.6rem 0.9rem; margin-bottom: 0.55rem;
	}
	.claim-item.factual { border-left-color: var(--sage); }
	.claim-badge {
		font-size: 0.58rem; font-weight: 700; text-transform: uppercase; letter-spacing: 0.1em;
		background: var(--ink); color: var(--panel); padding: 0.18rem 0.42rem;
	}
	.claim-text { margin: 0.4rem 0; font-size: 0.87rem; color: var(--ink); font-family: var(--serif); }
	.claim-citation { color: var(--muted); font-size: 0.72rem; line-height: 1.55; display: block; }

	.chunk-pair { display: grid; grid-template-columns: 1fr 1fr; gap: 0.9rem; margin-bottom: 0.8rem; }
	@media (max-width: 900px) { .chunk-pair { grid-template-columns: 1fr; } }
	.chunk-side {
		background: #f2ecdc; border: 1px solid var(--border-dark);
		border-top: 2px solid var(--gold);
		padding: 0.6rem 0.85rem; font-size: 0.8rem;
	}
	.chunk-side.wiki { background: var(--panel-cool); border-color: #c3ccd8; border-top-color: var(--navy); }
	.chunk-side small { color: var(--gold); font-weight: 700; letter-spacing: 0.06em; text-transform: uppercase; font-size: 0.64rem; }
	.chunk-side.wiki small { color: var(--navy); }
	.chunk-side p { margin: 0.3rem 0 0; color: var(--ink-soft); max-height: 120px; overflow-y: auto; font-family: var(--serif); line-height: 1.55; }

	.audit-table { width: 100%; border-collapse: collapse; font-size: 0.82rem; border-top: 2px solid var(--ink); border-bottom: 2px solid var(--ink); }
	.audit-table th, .audit-table td {
		text-align: left; padding: 0.42rem 0.55rem;
		border-bottom: 1px solid var(--border); color: var(--ink-soft);
	}
	.audit-table th {
		color: var(--ink); font-size: 0.68rem; text-transform: uppercase;
		letter-spacing: 0.1em; border-bottom: 1px solid var(--ink);
	}
	.audit-table code { font-family: var(--mono); color: var(--oxblood); font-size: 0.72rem; }

	.unmatched-box {
		background: rgba(138,101,22,0.05); border: 1px dashed rgba(138,101,22,0.45);
		padding: 1.5rem; text-align: center; margin-top: 1rem;
	}
	.unmatched-box h4 { margin: 0 0 0.5rem; color: #8a6516; font-family: var(--serif); }
	.unmatched-box p { margin: 0.3rem 0; color: var(--muted); font-size: 0.85rem; }

	/* ---------- Sections ---------- */
	.section-container h2 {
		color: var(--ink); font-family: var(--display);
		font-size: 1.9rem; font-weight: 500; margin: 0 0 0.4rem;
	}
	.h2-count {
		font-size: 0.72rem; color: var(--oxblood); font-family: var(--serif);
		font-style: italic; vertical-align: middle; margin-left: 0.3rem;
	}
	.tab-desc {
		color: var(--muted); font-size: 0.92rem; margin-top: 0.35rem;
		font-family: var(--serif); font-style: italic;
	}
	.tab-desc a { color: var(--navy); }

	.plots-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; margin-top: 1.4rem; }
	.plot-card {
		background: var(--panel); border: 1px solid var(--border); padding: 1.25rem;
	}
	.plot-card h3 { margin: 0 0 0.25rem; font-size: 0.85rem; color: var(--ink); font-family: var(--mono); }
	.plot-meta { margin: 0 0 0.9rem; font-size: 0.75rem; color: var(--muted); font-style: italic; font-family: var(--serif); }
	.plot-card img { width: 100%; background: #fff; border: 1px solid var(--border); }

	.table-box {
		background: var(--panel); border-top: 2px solid var(--ink); border-bottom: 2px solid var(--ink);
		margin-top: 1.4rem; overflow: hidden;
	}
	.data-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	.data-table th, .data-table td {
		text-align: left; padding: 0.6rem 0.9rem;
		border-bottom: 1px solid var(--border); color: var(--ink-soft);
	}
	.data-table tbody tr:hover { background: rgba(150,118,43,0.05); }
	.data-table tbody tr:last-child td { border-bottom: none; }
	.data-table th {
		color: var(--ink); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.1em;
		border-bottom: 1px solid var(--ink);
	}
	.data-table code { font-family: var(--mono); font-size: 0.74rem; color: var(--oxblood); }

	.action-btn {
		color: var(--navy); border: 1px solid var(--navy);
		text-decoration: none; padding: 0.3rem 0.6rem;
		font-size: 0.74rem; font-weight: 600; font-family: var(--mono);
		margin-right: 0.4rem; display: inline-block; transition: all 0.15s;
		border-radius: 2px;
	}
	.action-btn:hover { background: var(--navy); color: var(--panel); }
	.action-btn.pdf { color: var(--oxblood); border-color: var(--oxblood); }
	.action-btn.pdf:hover { background: var(--oxblood); color: var(--panel); }

	.runs-list { display: flex; flex-direction: column; gap: 1.1rem; margin-top: 1.4rem; }
	.run-card {
		background: var(--panel); border: 1px solid var(--border);
		border-left: 4px solid #a89a78; padding: 1.3rem 1.5rem;
	}
	.run-card.success { border-left-color: var(--sage); }
	.run-header { display: flex; justify-content: space-between; align-items: center; gap: 1rem; }
	.run-name { font-family: var(--mono); font-size: 0.78rem; color: var(--ink); word-break: break-all; }
	.run-status-badge { font-size: 0.62rem; font-weight: 700; padding: 0.22rem 0.55rem; letter-spacing: 0.1em; flex-shrink: 0; border: 1px solid; }
	.run-status-badge.success { color: var(--sage); border-color: rgba(76,114,87,0.5); background: rgba(76,114,87,0.07); }
	.run-status-badge.failure, .run-status-badge.failed { color: var(--oxblood); border-color: rgba(110,44,51,0.5); background: rgba(110,44,51,0.06); }
	.run-query, .run-meta { font-size: 0.85rem; color: var(--ink-soft); margin: 0.6rem 0 0; font-family: var(--serif); }
	.run-meta { color: var(--muted); font-size: 0.76rem; font-family: var(--sans); }
	.final-answer {
		background: #fffdf7; border: 1px solid var(--border);
		padding: 0.85rem 1rem; margin: 0.85rem 0; font-size: 0.85rem;
	}
	.final-answer strong { color: var(--oxblood); font-size: 0.68rem; text-transform: uppercase; letter-spacing: 0.12em; }
	.final-answer p { margin: 0.4rem 0 0; color: var(--ink-soft); white-space: pre-wrap; line-height: 1.65; font-family: var(--serif); }

	.tool-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin-top: 0.85rem; font-size: 0.74rem; color: var(--muted); }
	.tool-tag {
		border: 1px solid var(--border-dark); color: var(--ink-soft);
		padding: 0.2rem 0.5rem; font-size: 0.7rem; font-family: var(--mono);
	}

	.case-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1.1rem; margin: 1.4rem 0; }
	.case-card {
		background: var(--panel); border: 1px solid var(--border);
		border-left: 3px solid var(--gold);
		padding: 1.1rem 1.25rem;
		text-decoration: none; color: var(--ink);
		display: flex; flex-direction: column; gap: 0.45rem;
		transition: border-color 0.15s, box-shadow 0.15s;
	}
	.case-card:hover { border-color: var(--gold); box-shadow: 0 4px 14px rgba(60,50,25,0.12); }
	.case-card strong { color: var(--ink); font-size: 0.94rem; font-family: var(--serif); }
	.case-card span { color: var(--muted); font-size: 0.7rem; font-family: var(--mono); }

	/* ---------- Colophon footer ---------- */
	.footer {
		border-top: 1px solid var(--border-dark);
		padding: 1.1rem 2.2rem;
		display: flex; gap: 0.7rem; align-items: center; justify-content: center; flex-wrap: wrap;
		font-size: 0.75rem; color: var(--muted);
		background: var(--paper-deep);
		font-family: var(--serif);
	}
	.footer-team { color: var(--oxblood); font-weight: 700; letter-spacing: 0.22em; text-transform: uppercase; font-size: 0.66rem; font-family: var(--sans); }
	.footer-sep { color: var(--border-dark); }
	.footer code { font-family: var(--mono); font-size: 0.7rem; }

	@media (max-width: 900px) {
		.dual-pane-layout { grid-template-columns: 1fr; height: auto; }
		.sidebar { max-height: 320px; }
		.main-content { padding: 1rem; }
		.masthead { padding: 1.5rem 1rem 0; }
		h1 { font-size: 2rem; }
		.stat { padding: 0.7rem 1rem; }
	}
</style>
