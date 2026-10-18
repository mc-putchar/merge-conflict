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
	<title>Britannica 1771 vs Wikipedia — Nemotron Challenge</title>
</svelte:head>

<div class="app-container">
	<!-- Header -->
	<header class="header">
		<div class="header-content">
			<div class="title-group">
				<h1>Encyclopaedia Britannica 1771 ⟷ Wikipedia</h1>
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
			<div class="stat-card accent">
				<div class="stat-value">{rawData.stats.compared_count}</div>
				<div class="stat-label">Matched & Compared</div>
			</div>
			<div class="stat-card warn">
				<div class="stat-value">{rawData.stats.excluded_count}</div>
				<div class="stat-label">Excluded (Accounted)</div>
			</div>
			<div class="stat-card">
				<div class="stat-value">{rawData.topics.length}</div>
				<div class="stat-label">Topic Clusters</div>
			</div>
			<div class="stat-card purple">
				<div class="stat-value">{plateCount}</div>
				<div class="stat-label">Copperplates (Super-VL)</div>
			</div>
			<div class="stat-card highlight">
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
				Exclusions ({rawData.exclusions.length})
			</button>
			<button class:active={activeTab === 'latex'} on:click={() => activeTab = 'latex'}>
				LaTeX Documents ({rawData.entries.length})
			</button>
			<button class:active={activeTab === 'agent'} on:click={() => activeTab = 'agent'}>
				Agent Runs ({rawData.agent_runs.length})
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
							<button class:active-pill={filterStatus === 'all'} on:click={() => filterStatus = 'all'}>All ({rawData.entries.length})</button>
							<button class:active-pill={filterStatus === 'compared'} on:click={() => filterStatus = 'compared'}>Compared ({rawData.stats.compared_count})</button>
							<button class:active-pill={filterStatus === 'excluded'} on:click={() => filterStatus = 'excluded'}>Excluded ({rawData.stats.excluded_count})</button>
							<button class:active-pill={filterStatus === 'plates'} on:click={() => filterStatus = 'plates'}>Plates ({plateCount})</button>
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
									Chars: {item.character_count} · Vol: {item.volume_id}
								</div>
							</div>
						{/each}
					</div>
				</aside>

				<!-- Entry Detail Viewer -->
				<section class="detail-view">
					{#if selectedEntry}
						<div class="detail-header">
							<h2>{selectedEntry.title}</h2>
							<div class="detail-tags">
								<span class="meta-tag">ID: {selectedEntry.entry_id}</span>
								<span class="meta-tag">Volume: {selectedEntry.volume_id}</span>
								<a href={selectedEntry.latex_file} class="download-link" download>.tex</a>
								{#if pdfAvailable(selectedEntry)}
									<a href={selectedEntry.pdf_file} class="download-link pdf">.pdf</a>
								{/if}
							</div>
						</div>

						{#if detailLoading}
							<p class="loading-notice">Loading entry detail…</p>
						{:else if detailError}
							<p class="error-notice">{detailError}</p>
						{:else if selectedDetail}
							<div class="comparison-grid">
								<!-- Left Pane: Historical Britannica -->
								<div class="pane britannica-pane">
									<div class="pane-header">
										<h3>Historical Britannica (1771)</h3>
										<span class="char-count">{selectedEntry.character_count} characters</span>
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
										<h3>Wikipedia (Modern Snapshot)</h3>
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
									<div class="metrics-card">
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
												<div class="metric">
													<span class="m-val">#{selectedDetail.comparison.topic_id}</span>
													<span class="m-lbl">Topic: {(selectedDetail.comparison.topic_terms || []).join(', ')}</span>
												</div>
											{/if}
										</div>
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
			<div class="plots-container">
				<h2>Comparison Analysis Plots</h2>
				<p class="tab-desc">Deterministic SVGs generated by the compare stage; document counts verified in run record.</p>
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
			<div class="exclusions-container">
				<h2>Exclusion Audit ({rawData.exclusions.length})</h2>
				<p class="tab-desc">Every extracted entry is accounted for: compared, or excluded with a recorded reason.</p>
				<div class="latex-table-box">
					<table class="latex-table">
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
			<div class="latex-container">
				<h2>Compiled LaTeX Deliverables ({rawData.entries.length} Documents)</h2>
				<p class="tab-desc">
					Each entry compiles to PDF with the embedded source scan.
					{#if latexReport}
						Compiled: <strong>{latexReport.compiled}</strong>
						{#if latexReport.failed?.length}· Failed: <strong>{latexReport.failed.length}</strong>{/if}
						{#if latexReport.error}· {latexReport.error}{/if}
					{/if}
					<a href="latex/compile_report.json" target="_blank" rel="noopener noreferrer">compile report</a>
				</p>
				{#if latexReport?.failed?.length}
					<div class="unmatched-box">
						<h4>Compile Failures (recorded honestly)</h4>
						{#each latexReport.failed as f}<p><code>{f.file}</code></p>{/each}
					</div>
				{/if}

				<div class="latex-table-box">
					<table class="latex-table">
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
											<a href={e.pdf_file} class="action-btn pdf" download>.pdf</a>
										{/if}
									</td>
								</tr>
							{/each}
						</tbody>
					</table>
				</div>
			</div>
		{:else if activeTab === 'agent'}
			<div class="agent-container">
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
								<strong>Tools Used:</strong>
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
			<div class="evaluate-container">
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
</div>

<style>
	:global(body) {
		margin: 0;
		font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
		background: #0f172a;
		color: #e2e8f0;
	}

	.app-container { min-height: 100vh; display: flex; flex-direction: column; }

	.header {
		background: #1e293b;
		border-bottom: 1px solid #334155;
		padding: 1.5rem 2rem 0;
	}

	.header-content {
		display: flex;
		justify-content: space-between;
		align-items: flex-start;
		flex-wrap: wrap;
		gap: 1rem;
	}

	h1 { margin: 0; font-size: 1.75rem; font-weight: 700; color: #f8fafc; }
	.subtitle { margin: 0.35rem 0 0; color: #94a3b8; font-size: 0.95rem; }

	.badge-group { display: flex; flex-wrap: wrap; gap: 0.5rem; }
	.badge {
		background: #0284c7; color: #fff; padding: 0.25rem 0.6rem;
		border-radius: 9999px; font-size: 0.75rem; font-weight: 600;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem; margin: 1.5rem 0;
	}

	.stat-card {
		background: #0f172a; border: 1px solid #334155;
		border-radius: 8px; padding: 1rem; text-align: center;
	}
	.stat-card.accent { border-color: #38bdf8; }
	.stat-card.warn { border-color: #f59e0b; }
	.stat-card.purple { border-color: #a855f7; }
	.stat-card.highlight { border-color: #10b981; }
	.stat-value { font-size: 2rem; font-weight: 700; color: #f1f5f9; }
	.stat-label { color: #94a3b8; font-size: 0.8rem; margin-top: 0.25rem; }

	.nav-tabs { display: flex; gap: 0.5rem; overflow-x: auto; }
	.nav-tabs button {
		background: transparent; border: none;
		border-bottom: 3px solid transparent;
		color: #94a3b8; padding: 0.75rem 1.25rem;
		font-size: 0.95rem; font-weight: 600; cursor: pointer;
		transition: all 0.2s; white-space: nowrap;
	}
	.nav-tabs button:hover { color: #f8fafc; }
	.nav-tabs button.active { color: #38bdf8; border-bottom-color: #38bdf8; }

	.main-content { flex: 1; padding: 1.5rem 2rem; }

	.dual-pane-layout {
		display: grid;
		grid-template-columns: 340px 1fr;
		gap: 1.5rem;
		height: calc(100vh - 340px);
		min-height: 550px;
	}

	.sidebar {
		background: #1e293b; border: 1px solid #334155;
		border-radius: 8px; display: flex; flex-direction: column; overflow: hidden;
	}
	.filter-box { padding: 1rem; border-bottom: 1px solid #334155; }
	.search-input {
		width: 100%; box-sizing: border-box;
		background: #0f172a; border: 1px solid #334155; color: #f8fafc;
		padding: 0.5rem 0.75rem; border-radius: 6px; font-size: 0.9rem;
	}
	.filter-pills { display: flex; gap: 0.4rem; margin-top: 0.75rem; }
	.filter-pills button {
		flex: 1; background: #0f172a; border: 1px solid #334155; color: #94a3b8;
		font-size: 0.75rem; padding: 0.35rem 0.2rem; border-radius: 4px; cursor: pointer;
	}
	.filter-pills button.active-pill { background: #38bdf8; color: #0f172a; font-weight: 600; border-color: #38bdf8; }

	.entry-list { flex: 1; overflow-y: auto; }
	.entry-item { padding: 0.85rem 1rem; border-bottom: 1px solid #334155; cursor: pointer; transition: background 0.15s; }
	.entry-item:hover { background: #273549; }
	.entry-item.selected { background: #0369a1; border-left: 4px solid #38bdf8; }
	.entry-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 0.25rem; }
	.entry-title { font-size: 0.95rem; color: #f1f5f9; }
	.status-tag { font-size: 0.7rem; padding: 0.15rem 0.4rem; border-radius: 4px; font-weight: 600; }
	.status-tag.compared { background: #065f46; color: #6ee7b7; }
	.status-tag.excluded { background: #78350f; color: #fde68a; }
	.status-tag.plate { background: #581c87; color: #d8b4fe; }
	.entry-meta { font-size: 0.75rem; color: #94a3b8; }

	.detail-view {
		background: #1e293b; border: 1px solid #334155;
		border-radius: 8px; padding: 1.5rem; overflow-y: auto;
	}
	.detail-header {
		display: flex; justify-content: space-between; align-items: center;
		border-bottom: 1px solid #334155; padding-bottom: 1rem; margin-bottom: 1rem;
	}
	.detail-header h2 { margin: 0; color: #f8fafc; }
	.detail-tags { display: flex; gap: 0.75rem; align-items: center; }
	.meta-tag { background: #0f172a; padding: 0.35rem 0.6rem; border-radius: 4px; font-size: 0.8rem; color: #94a3b8; }
	.download-link {
		background: #0284c7; color: #fff; text-decoration: none;
		padding: 0.35rem 0.75rem; border-radius: 4px; font-size: 0.85rem; font-weight: 600;
	}
	.download-link.pdf { background: #b91c1c; }

	.loading-notice { color: #94a3b8; }
	.error-notice { color: #fca5a5; }

	.comparison-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 1.5rem; }
	.pane {
		background: #0f172a; border: 1px solid #334155;
		border-radius: 6px; padding: 1.25rem;
		display: flex; flex-direction: column;
	}
	.pane-header {
		display: flex; justify-content: space-between; align-items: center;
		border-bottom: 1px solid #334155; padding-bottom: 0.75rem; margin-bottom: 0.75rem;
	}
	.pane-header h3 { margin: 0; font-size: 1.1rem; }
	.source-info p { margin: 0.25rem 0; font-size: 0.85rem; color: #94a3b8; word-break: break-all; }
	.source-info code { font-size: 0.75rem; }
	.truncated-note { color: #fbbf24; }

	.scan-figure { margin: 0.75rem 0; }
	.scan-figure img {
		max-width: 100%; border: 1px solid #334155; border-radius: 4px;
		background: #fff; max-height: 380px; object-fit: contain;
	}
	.scan-figure figcaption { font-size: 0.7rem; color: #94a3b8; margin-top: 0.25rem; word-break: break-all; }

	.annotation-box {
		background: #1e293b; border: 1px solid #a855f7; border-radius: 6px;
		padding: 0.75rem 1rem; margin: 0.75rem 0; font-size: 0.85rem;
	}
	.annotation-box h4 { margin: 0 0 0.4rem; color: #d8b4fe; font-size: 0.85rem; }
	.annotation-box p { margin: 0.25rem 0; color: #cbd5e1; }

	.text-content {
		margin-top: 1rem; line-height: 1.6; font-size: 0.95rem;
		max-height: 400px; overflow-y: auto; white-space: pre-wrap;
	}
	.historical-text { font-family: Georgia, serif; color: #e2e8f0; }
	.empty-notice { color: #94a3b8; }

	.evidence-section { margin-top: 1.5rem; border-top: 1px dashed #334155; padding-top: 1rem; }
	.evidence-section h3 { margin: 0 0 0.75rem; color: #f8fafc; }
	.derived-tag {
		font-size: 0.65rem; background: #334155; color: #fbbf24;
		padding: 0.15rem 0.4rem; border-radius: 3px; vertical-align: middle;
		text-transform: uppercase; letter-spacing: 0.05em;
	}

	.metrics-card {
		background: #1e293b; border: 1px solid #334155;
		border-radius: 6px; padding: 1rem; margin: 1rem 0;
	}
	.metrics-row { display: flex; gap: 1rem; flex-wrap: wrap; }
	.metric {
		background: #0f172a; padding: 0.5rem 0.75rem; border-radius: 4px;
		display: flex; flex-direction: column; max-width: 280px;
	}
	.m-val { font-weight: 700; font-size: 1.1rem; color: #f8fafc; }
	.m-lbl { font-size: 0.7rem; color: #94a3b8; }

	.claims-list { margin-top: 1rem; }
	.claims-list h4, .chunks-list h4, .changes-list h4 { color: #38bdf8; font-size: 0.95rem; margin: 0.75rem 0 0.5rem; }
	.claim-item {
		background: #0f172a; border-left: 3px solid #64748b;
		padding: 0.5rem 0.75rem; margin-bottom: 0.5rem; border-radius: 0 4px 4px 0;
	}
	.claim-item.factual { border-left-color: #10b981; }
	.claim-badge {
		font-size: 0.65rem; font-weight: 700; text-transform: uppercase;
		background: #334155; padding: 0.15rem 0.35rem; border-radius: 3px;
	}
	.claim-text { margin: 0.35rem 0; font-size: 0.85rem; }
	.claim-citation { color: #94a3b8; font-size: 0.75rem; }

	.chunk-pair {
		display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem;
		margin-bottom: 0.75rem;
	}
	.chunk-side {
		background: #0f172a; border: 1px solid #334155; border-radius: 4px;
		padding: 0.5rem 0.75rem; font-size: 0.8rem;
	}
	.chunk-side small { color: #38bdf8; }
	.chunk-side.wiki small { color: #a78bfa; }
	.chunk-side p { margin: 0.25rem 0 0; color: #cbd5e1; max-height: 120px; overflow-y: auto; }

	.audit-table { width: 100%; border-collapse: collapse; font-size: 0.8rem; }
	.audit-table th, .audit-table td {
		text-align: left; padding: 0.35rem 0.5rem;
		border-bottom: 1px solid #334155; color: #cbd5e1;
	}
	.audit-table th { color: #94a3b8; }

	.unmatched-box {
		background: #1e293b; border: 1px dashed #64748b;
		padding: 1.5rem; border-radius: 6px; text-align: center; margin-top: 1rem;
	}

	.plots-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(420px, 1fr)); gap: 1.5rem; }
	.plot-card {
		background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1rem;
	}
	.plot-card h3 { margin: 0 0 0.25rem; font-size: 1rem; color: #f8fafc; }
	.plot-meta { margin: 0 0 0.75rem; font-size: 0.8rem; color: #94a3b8; }
	.plot-card img { width: 100%; background: #fff; border-radius: 4px; }

	.topics-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1.5rem; }
	.topic-card { background: #1e293b; border: 1px solid #334155; border-radius: 8px; padding: 1.25rem; }
	.topic-header { display: flex; justify-content: space-between; font-size: 0.85rem; color: #94a3b8; }
	.topic-label { margin: 0.5rem 0 1rem; color: #38bdf8; font-size: 1.2rem; }
	.terms-group { display: flex; flex-direction: column; gap: 0.75rem; }
	.pill-cloud { display: flex; flex-wrap: wrap; gap: 0.4rem; margin-top: 0.25rem; }
	.term-pill { font-size: 0.75rem; padding: 0.2rem 0.5rem; border-radius: 4px; }
	.term-pill.brit { background: #3b82f6; color: #fff; }
	.term-pill.wiki { background: #8b5cf6; color: #fff; }

	.latex-table-box { background: #1e293b; border: 1px solid #334155; border-radius: 8px; overflow: hidden; margin-top: 1rem; }
	.latex-table { width: 100%; border-collapse: collapse; font-size: 0.85rem; }
	.latex-table th, .latex-table td {
		text-align: left; padding: 0.6rem 0.75rem;
		border-bottom: 1px solid #334155; color: #e2e8f0;
	}
	.latex-table th { background: #0f172a; color: #94a3b8; font-size: 0.75rem; text-transform: uppercase; }
	.action-btn {
		background: #0284c7; color: #fff; text-decoration: none;
		padding: 0.3rem 0.6rem; border-radius: 4px; font-size: 0.8rem; font-weight: 600;
		margin-right: 0.4rem; display: inline-block;
	}
	.action-btn.pdf { background: #b91c1c; }

	.runs-list { display: flex; flex-direction: column; gap: 1rem; }
	.run-card {
		background: #1e293b; border: 1px solid #334155;
		border-left: 4px solid #f59e0b; border-radius: 8px; padding: 1.25rem;
	}
	.run-card.success { border-left-color: #10b981; }
	.run-header { display: flex; justify-content: space-between; align-items: center; }
	.run-name { font-family: monospace; font-size: 0.85rem; color: #f8fafc; }
	.run-status-badge { font-size: 0.7rem; font-weight: 700; padding: 0.2rem 0.5rem; border-radius: 4px; }
	.run-status-badge.success { background: #065f46; color: #6ee7b7; }
	.run-status-badge.failure, .run-status-badge.failed { background: #7f1d1d; color: #fca5a5; }
	.run-query, .run-meta { font-size: 0.85rem; color: #cbd5e1; margin: 0.5rem 0 0; }
	.final-answer {
		background: #0f172a; border-radius: 4px; padding: 0.75rem;
		margin: 0.75rem 0; font-size: 0.85rem;
	}
	.final-answer p { margin: 0.35rem 0 0; color: #cbd5e1; white-space: pre-wrap; }

	.tool-tags { display: flex; flex-wrap: wrap; gap: 0.4rem; align-items: center; margin-top: 0.75rem; font-size: 0.8rem; color: #94a3b8; }
	.tool-tag { background: #334155; padding: 0.2rem 0.5rem; border-radius: 4px; font-size: 0.75rem; color: #e2e8f0; }

	.case-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 1rem; margin: 1rem 0; }
	.case-card {
		background: #1e293b; border: 1px solid #334155; border-radius: 8px;
		padding: 1rem; text-decoration: none; color: #e2e8f0;
		display: flex; flex-direction: column; gap: 0.4rem;
	}
	.case-card:hover { border-color: #38bdf8; }
	.case-card strong { color: #f8fafc; font-size: 0.9rem; }
	.case-card span { color: #94a3b8; font-size: 0.75rem; font-family: monospace; }

	.tab-desc { color: #94a3b8; font-size: 0.9rem; }
	.tab-desc a { color: #38bdf8; }
	h2 { color: #f8fafc; }
</style>
