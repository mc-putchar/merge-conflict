<script>
	import rawData from '../lib/challenge_data.json';

	let activeTab = 'entries';
	let searchQuery = '';
	let selectedEntryId = rawData.entries[0]?.entry_id || '';
	let filterStatus = 'all'; // all, compared, excluded, plates

	$: plateCount = rawData.entries.filter(e => e.title.includes('Plate') || e.title.includes('PLATE') || e.text.includes('COPPERPLATE')).length;

	$: filteredEntries = rawData.entries.filter((entry) => {
		const matchesQuery = entry.title.toLowerCase().includes(searchQuery.toLowerCase()) ||
			entry.entry_id.toLowerCase().includes(searchQuery.toLowerCase());
		if (filterStatus === 'compared') return matchesQuery && entry.comparison;
		if (filterStatus === 'excluded') return matchesQuery && !entry.comparison;
		if (filterStatus === 'plates') return matchesQuery && (entry.title.includes('Plate') || entry.title.includes('PLATE') || entry.text.includes('COPPERPLATE'));
		return matchesQuery;
	});

	$: selectedEntry = rawData.entries.find((e) => e.entry_id === selectedEntryId) || rawData.entries[0];

	function selectEntry(id) {
		selectedEntryId = id;
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
				<h1>📜 Encyclopaedia Britannica 1771 ⟷ Wikipedia</h1>
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
				<div class="stat-label">BERTopic Clusters</div>
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
				📖 Dual-Pane Reader & Comparisons
			</button>
			<button class:active={activeTab === 'topics'} on:click={() => activeTab = 'topics'}>
				📊 Topics & Semantic Clusters
			</button>
			<button class:active={activeTab === 'latex'} on:click={() => activeTab = 'latex'}>
				📜 Compiled LaTeX Documents ({rawData.entries.length})
			</button>
			<button class:active={activeTab === 'agent'} on:click={() => activeTab = 'agent'}>
				🤖 Hermes Agent Runs & Verification
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
							<button class:active-pill={filterStatus === 'plates'} on:click={() => filterStatus = 'plates'}>🖼️ Plates ({plateCount})</button>
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
									{#if item.comparison}
										<span class="status-tag compared">Compared</span>
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
								<a href={selectedEntry.latex_file} class="download-link" download>Download LaTeX (.tex)</a>
							</div>
						</div>

						<div class="comparison-grid">
							<!-- Left Pane: Historical Britannica -->
							<div class="pane britannica-pane">
								<div class="pane-header">
									<h3>🏛️ Historical Britannica (1771)</h3>
									<span class="char-count">{selectedEntry.character_count} characters</span>
								</div>
								<div class="source-info">
									<p><strong>Source Pages:</strong> {selectedEntry.source_pages.join(', ')}</p>
									<p><strong>Rows:</strong> {selectedEntry.source_row_indices.join(', ')}</p>
								</div>
								<div class="text-content historical-text">
									{#if selectedEntry.text.trim()}
										{selectedEntry.text}
									{:else}
										<p class="empty-notice"><em>(No textual body extracted; historical illustration plate or non-text scan.)</em></p>
									{/if}
								</div>
							</div>

							<!-- Right Pane: Matched Wikipedia Article -->
							<div class="pane wikipedia-pane">
								<div class="pane-header">
									<h3>🌐 Wikipedia (Modern Snapshot)</h3>
									{#if selectedEntry.wikipedia_article}
										<a href={selectedEntry.wikipedia_article.url} target="_blank" rel="noopener noreferrer" class="wiki-link">
											Open Article ↗
										</a>
									{/if}
								</div>

								{#if selectedEntry.wikipedia_article}
									<div class="source-info">
										<p><strong>Title:</strong> {selectedEntry.wikipedia_article.title}</p>
										<p><strong>Page ID:</strong> {selectedEntry.wikipedia_article.page_id} · <strong>Revision:</strong> {selectedEntry.wikipedia_article.revision_id}</p>
										<p><strong>BM25 Rank:</strong> #{selectedEntry.wikipedia_article.rank} (Score: {selectedEntry.wikipedia_article.bm25_score?.toFixed(2)})</p>
									</div>

									{#if selectedEntry.comparison}
										<div class="metrics-card">
											<h4>Comparison Metrics</h4>
											<div class="metrics-row">
												<div class="metric">
													<span class="m-val">{selectedEntry.comparison.length_ratio}</span>
													<span class="m-lbl">Length Ratio (Wiki/Brit)</span>
												</div>
												{#if selectedEntry.comparison.metrics?.cosine_embedding}
													<div class="metric">
														<span class="m-val">{selectedEntry.comparison.metrics.cosine_embedding}</span>
														<span class="m-lbl">Nemotron Embedding Cosine</span>
													</div>
												{/if}
												{#if selectedEntry.comparison.metrics?.jaccard_similarity}
													<div class="metric">
														<span class="m-val">{selectedEntry.comparison.metrics.jaccard_similarity.toFixed(3)}</span>
														<span class="m-lbl">Jaccard Sim</span>
													</div>
												{/if}
											</div>

											{#if selectedEntry.comparison.claims && selectedEntry.comparison.claims.length > 0}
												<div class="claims-list">
													<h4>Cited Comparative Claims ({selectedEntry.comparison.claims.length})</h4>
													{#each selectedEntry.comparison.claims as claim}
														<div class="claim-item" class:factual={claim.claim_type === 'factual'}>
															<span class="claim-badge">{claim.claim_type}</span>
															<p class="claim-text">{claim.claim}</p>
															{#if claim.citation}
																<small class="claim-citation">Ref: {claim.citation}</small>
															{/if}
														</div>
													{/each}
												</div>
											{/if}
										</div>
									{/if}

									<div class="text-content modern-text">
										<p><strong>Article Excerpt:</strong></p>
										<p>{selectedEntry.wikipedia_article.excerpt}</p>
									</div>
								{:else}
									<div class="unmatched-box">
										<h4>No Wikipedia Match Accepted</h4>
										<p><strong>Status:</strong> {selectedEntry.match_status}</p>
										<p>This entry was excluded from lexical comparison according to calibrated threshold rules.</p>
									</div>
								{/if}
							</div>
						</div>
					{/if}
				</section>
			</div>
		{:else if activeTab === 'topics'}
			<div class="topics-container">
				<h2>Semantic Topic Clusters (BERTopic + Nemotron Embeddings)</h2>
				<p class="tab-desc">Clusters derived using UMAP, HDBSCAN, and c-TF-IDF over dual-source vocabulary.</p>

				<div class="topics-grid">
					{#each rawData.topics as topic}
						<div class="topic-card">
							<div class="topic-header">
								<span class="topic-id">Topic #{topic.topic_id}</span>
								<span class="doc-count">{topic.document_count} Documents</span>
							</div>
							<h3 class="topic-label">{topic.label || 'Unlabeled Topic'}</h3>
							<div class="terms-group">
								<div class="term-col">
									<strong>Britannica Terms:</strong>
									<div class="pill-cloud">
										{#each topic.top_terms_britannica as term}
											<span class="term-pill brit">{term}</span>
										{/each}
									</div>
								</div>
								<div class="term-col">
									<strong>Wikipedia Terms:</strong>
									<div class="pill-cloud">
										{#each topic.top_terms_wikipedia as term}
											<span class="term-pill wiki">{term}</span>
										{/each}
									</div>
								</div>
							</div>
						</div>
					{/each}
				</div>
			</div>
		{:else if activeTab === 'latex'}
			<div class="latex-container">
				<h2>Compiled LaTeX Deliverables ({rawData.entries.length} Documents)</h2>
				<p class="tab-desc">Each extracted entry conforms to the challenge LaTeX template with source citations and provenance.</p>

				<div class="latex-table-box">
					<table class="latex-table">
						<thead>
							<tr>
								<th>Entry ID</th>
								<th>Title</th>
								<th>Volume</th>
								<th>Characters</th>
								<th>Action</th>
							</tr>
						</thead>
						<tbody>
							{#each rawData.entries as e}
								<tr>
									<td><code>{e.entry_id}</code></td>
									<td><strong>{e.title}</strong></td>
									<td>{e.volume_id}</td>
									<td>{e.character_count}</td>
									<td>
										<a href={e.latex_file} class="action-btn" download>Download .tex</a>
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
				<p class="tab-desc">Evidence and execution traces for Hermes reasoning with Nemotron-3.5-Super-VL.</p>

				<div class="runs-list">
					{#each rawData.agent_runs as run}
						<div class="run-card" class:success={run.status === 'success'}>
							<div class="run-header">
								<span class="run-name">{run.run}</span>
								<span class="run-status-badge {run.status}">{run.status.toUpperCase()}</span>
							</div>
							<div class="tool-tags">
								<strong>Tools Used:</strong>
								{#each run.tool_calls as tool}
									<span class="tool-tag">{tool}</span>
								{/each}
							</div>
						</div>
					{/each}
				</div>
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

	.app-container {
		min-height: 100vh;
		display: flex;
		flex-direction: column;
	}

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

	h1 {
		margin: 0;
		font-size: 1.75rem;
		font-weight: 700;
		color: #f8fafc;
	}

	.subtitle {
		margin: 0.35rem 0 0;
		color: #94a3b8;
		font-size: 0.95rem;
	}

	.badge-group {
		display: flex;
		flex-wrap: wrap;
		gap: 0.5rem;
	}

	.badge {
		background: #0284c7;
		color: #fff;
		padding: 0.25rem 0.6rem;
		border-radius: 9999px;
		font-size: 0.75rem;
		font-weight: 600;
	}

	.stats-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
		gap: 1rem;
		margin: 1.5rem 0;
	}

	.stat-card {
		background: #0f172a;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 1rem;
		text-align: center;
	}

	.stat-card.accent { border-color: #38bdf8; }
	.stat-card.warn { border-color: #f59e0b; }
	.stat-card.purple { border-color: #a855f7; }
	.stat-card.highlight { border-color: #10b981; }

	.stat-value {
		font-size: 2rem;
		font-weight: 700;
		color: #f1f5f9;
	}

	.stat-label {
		color: #94a3b8;
		font-size: 0.8rem;
		margin-top: 0.25rem;
	}

	.nav-tabs {
		display: flex;
		gap: 0.5rem;
		overflow-x: auto;
	}

	.nav-tabs button {
		background: transparent;
		border: none;
		border-bottom: 3px solid transparent;
		color: #94a3b8;
		padding: 0.75rem 1.25rem;
		font-size: 0.95rem;
		font-weight: 600;
		cursor: pointer;
		transition: all 0.2s;
	}

	.nav-tabs button:hover {
		color: #f8fafc;
	}

	.nav-tabs button.active {
		color: #38bdf8;
		border-bottom-color: #38bdf8;
	}

	.main-content {
		flex: 1;
		padding: 1.5rem 2rem;
	}

	.dual-pane-layout {
		display: grid;
		grid-template-columns: 340px 1fr;
		gap: 1.5rem;
		height: calc(100vh - 340px);
		min-height: 550px;
	}

	.sidebar {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}

	.filter-box {
		padding: 1rem;
		border-bottom: 1px solid #334155;
	}

	.search-input {
		width: 100%;
		box-sizing: border-box;
		background: #0f172a;
		border: 1px solid #334155;
		color: #f8fafc;
		padding: 0.5rem 0.75rem;
		border-radius: 6px;
		font-size: 0.9rem;
	}

	.filter-pills {
		display: flex;
		gap: 0.4rem;
		margin-top: 0.75rem;
	}

	.filter-pills button {
		flex: 1;
		background: #0f172a;
		border: 1px solid #334155;
		color: #94a3b8;
		font-size: 0.75rem;
		padding: 0.35rem 0.2rem;
		border-radius: 4px;
		cursor: pointer;
	}

	.filter-pills button.active-pill {
		background: #38bdf8;
		color: #0f172a;
		font-weight: 600;
		border-color: #38bdf8;
	}

	.entry-list {
		flex: 1;
		overflow-y: auto;
	}

	.entry-item {
		padding: 0.85rem 1rem;
		border-bottom: 1px solid #334155;
		cursor: pointer;
		transition: background 0.15s;
	}

	.entry-item:hover {
		background: #273549;
	}

	.entry-item.selected {
		background: #0369a1;
		border-left: 4px solid #38bdf8;
	}

	.entry-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 0.25rem;
	}

	.entry-title {
		font-size: 0.95rem;
		color: #f1f5f9;
	}

	.status-tag {
		font-size: 0.7rem;
		padding: 0.15rem 0.4rem;
		border-radius: 4px;
		font-weight: 600;
	}

	.status-tag.compared { background: #065f46; color: #6ee7b7; }
	.status-tag.excluded { background: #78350f; color: #fde68a; }

	.entry-meta {
		font-size: 0.75rem;
		color: #94a3b8;
	}

	.detail-view {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 1.5rem;
		overflow-y: auto;
	}

	.detail-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		border-bottom: 1px solid #334155;
		padding-bottom: 1rem;
		margin-bottom: 1rem;
	}

	.detail-header h2 {
		margin: 0;
		color: #f8fafc;
	}

	.detail-tags {
		display: flex;
		gap: 0.75rem;
		align-items: center;
	}

	.meta-tag {
		background: #0f172a;
		padding: 0.35rem 0.6rem;
		border-radius: 4px;
		font-size: 0.8rem;
		color: #94a3b8;
	}

	.download-link {
		background: #0284c7;
		color: #fff;
		text-decoration: none;
		padding: 0.35rem 0.75rem;
		border-radius: 4px;
		font-size: 0.85rem;
		font-weight: 600;
	}

	.comparison-grid {
		display: grid;
		grid-template-columns: 1fr 1fr;
		gap: 1.5rem;
	}

	.pane {
		background: #0f172a;
		border: 1px solid #334155;
		border-radius: 6px;
		padding: 1.25rem;
		display: flex;
		flex-direction: column;
	}

	.pane-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
		border-bottom: 1px solid #334155;
		padding-bottom: 0.75rem;
		margin-bottom: 0.75rem;
	}

	.pane-header h3 {
		margin: 0;
		font-size: 1.1rem;
	}

	.source-info p {
		margin: 0.25rem 0;
		font-size: 0.85rem;
		color: #94a3b8;
	}

	.text-content {
		margin-top: 1rem;
		line-height: 1.6;
		font-size: 0.95rem;
		max-height: 400px;
		overflow-y: auto;
		white-space: pre-wrap;
	}

	.historical-text {
		font-family: Georgia, serif;
		color: #e2e8f0;
	}

	.metrics-card {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 6px;
		padding: 1rem;
		margin: 1rem 0;
	}

	.metrics-card h4 {
		margin: 0 0 0.5rem;
		font-size: 0.9rem;
		color: #38bdf8;
	}

	.metrics-row {
		display: flex;
		gap: 1rem;
	}

	.metric {
		background: #0f172a;
		padding: 0.5rem 0.75rem;
		border-radius: 4px;
		display: flex;
		flex-direction: column;
	}

	.m-val {
		font-weight: 700;
		font-size: 1.1rem;
		color: #f8fafc;
	}

	.m-lbl {
		font-size: 0.7rem;
		color: #94a3b8;
	}

	.claims-list {
		margin-top: 1rem;
	}

	.claim-item {
		background: #0f172a;
		border-left: 3px solid #64748b;
		padding: 0.5rem 0.75rem;
		margin-bottom: 0.5rem;
		border-radius: 0 4px 4px 0;
	}

	.claim-item.factual {
		border-left-color: #10b981;
	}

	.claim-badge {
		font-size: 0.65rem;
		font-weight: 700;
		text-transform: uppercase;
		background: #334155;
		padding: 0.15rem 0.35rem;
		border-radius: 3px;
	}

	.claim-text {
		margin: 0.35rem 0;
		font-size: 0.85rem;
	}

	.claim-citation {
		color: #94a3b8;
		font-size: 0.75rem;
	}

	.unmatched-box {
		background: #1e293b;
		border: 1px dashed #64748b;
		padding: 1.5rem;
		border-radius: 6px;
		text-align: center;
		margin-top: 1rem;
	}

	.topics-grid {
		display: grid;
		grid-template-columns: repeat(auto-fit, minmax(320px, 1fr));
		gap: 1.5rem;
	}

	.topic-card {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 1.25rem;
	}

	.topic-header {
		display: flex;
		justify-content: space-between;
		font-size: 0.85rem;
		color: #94a3b8;
	}

	.topic-label {
		margin: 0.5rem 0 1rem;
		color: #38bdf8;
		font-size: 1.2rem;
	}

	.terms-group {
		display: flex;
		flex-direction: column;
		gap: 0.75rem;
	}

	.pill-cloud {
		display: flex;
		flex-wrap: wrap;
		gap: 0.4rem;
		margin-top: 0.25rem;
	}

	.term-pill {
		font-size: 0.75rem;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
	}

	.term-pill.brit { background: #3b82f6; color: #fff; }
	.term-pill.wiki { background: #8b5cf6; color: #fff; }

	.latex-table-box {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		overflow-x: auto;
	}

	.latex-table {
		width: 100%;
		border-collapse: collapse;
		text-align: left;
	}

	.latex-table th, .latex-table td {
		padding: 0.75rem 1rem;
		border-bottom: 1px solid #334155;
	}

	.latex-table th {
		background: #0f172a;
		font-size: 0.85rem;
		color: #94a3b8;
	}

	.action-btn {
		background: #0284c7;
		color: #fff;
		padding: 0.3rem 0.6rem;
		border-radius: 4px;
		font-size: 0.8rem;
		text-decoration: none;
	}

	.runs-list {
		display: flex;
		flex-direction: column;
		gap: 1rem;
	}

	.run-card {
		background: #1e293b;
		border: 1px solid #334155;
		border-radius: 8px;
		padding: 1.25rem;
	}

	.run-card.success {
		border-left: 4px solid #10b981;
	}

	.run-header {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}

	.run-name {
		font-weight: 600;
	}

	.run-status-badge {
		font-size: 0.75rem;
		padding: 0.25rem 0.5rem;
		border-radius: 4px;
		font-weight: 700;
	}

	.run-status-badge.success { background: #065f46; color: #6ee7b7; }

	.tool-tags {
		margin-top: 0.75rem;
		display: flex;
		gap: 0.5rem;
		align-items: center;
	}

	.tool-tag {
		background: #0f172a;
		border: 1px solid #334155;
		padding: 0.2rem 0.5rem;
		border-radius: 4px;
		font-size: 0.8rem;
	}
</style>
