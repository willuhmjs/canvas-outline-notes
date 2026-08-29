<script lang="ts">
	import type { PageData } from './$types';

	let { data }: { data: PageData } = $props();

	const { tokenStatus, healthChecks, lastSync, lastNotes, recentJobs } = $derived(data);

	function statusDotClass(status: string) {
		if (status === 'healthy') return 'status-dot-green';
		if (status === 'error') return 'status-dot-red';
		return 'status-dot-slate';
	}

	function statusTextClass(status: string) {
		if (status === 'healthy') return 'text-green-400';
		if (status === 'error') return 'text-red-400';
		return 'text-slate-400';
	}

	function tokenLevelClass(level: string) {
		if (level === 'healthy') return 'bg-green-500';
		if (level === 'warning') return 'bg-yellow-500';
		if (level === 'expired') return 'bg-red-500';
		return 'bg-slate-500';
	}

	function tokenBadgeClass(level: string) {
		if (level === 'healthy') return 'bg-green-900/40 text-green-400 border border-green-800';
		if (level === 'warning') return 'bg-yellow-900/40 text-yellow-400 border border-yellow-800';
		if (level === 'expired') return 'bg-red-900/40 text-red-400 border border-red-800';
		return 'bg-slate-700 text-slate-400 border border-slate-600';
	}

	function tokenLabel(level: string, daysRemaining: number | null) {
		if (level === 'expired') return 'Expired';
		if (level === 'warning') return `Expiring soon — ${daysRemaining}d left`;
		if (level === 'healthy') return `Valid — ${daysRemaining}d remaining`;
		return 'Unknown';
	}

	function jobStatusBadge(status: string) {
		if (status === 'succeeded')
			return 'bg-green-900/40 text-green-400 border border-green-800';
		if (status === 'failed')
			return 'bg-red-900/40 text-red-400 border border-red-800';
		if (status === 'running')
			return 'bg-indigo-900/40 text-indigo-400 border border-indigo-800';
		return 'bg-slate-700 text-slate-400 border border-slate-600';
	}

	function relTime(iso: string | null) {
		if (!iso) return '—';
		const diff = Date.now() - new Date(iso).getTime();
		const s = Math.floor(diff / 1000);
		if (s < 60) return `${s}s ago`;
		if (s < 3600) return `${Math.floor(s / 60)}m ago`;
		if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
		return `${Math.floor(s / 86400)}d ago`;
	}

	// Clamp progress bar between 0–100
	function tokenProgress(): number {
		if (!tokenStatus.isSet || tokenStatus.daysElapsed === null) return 0;
		return Math.min(100, Math.max(0, (tokenStatus.daysElapsed / tokenStatus.daysTotal) * 100));
	}
</script>

<svelte:head>
	<title>Dashboard — Canvas Management</title>
</svelte:head>

<div class="p-8 max-w-5xl mx-auto space-y-8">
	<div>
		<h1 class="text-2xl font-semibold text-slate-100">Dashboard</h1>
		<p class="text-sm text-slate-400 mt-1">System status and recent activity</p>
	</div>

	<!-- Connection health row -->
	<div class="grid grid-cols-1 sm:grid-cols-3 gap-4">
		{#each healthChecks as check}
			<div class="card">
				<div class="flex items-center justify-between mb-3">
					<span class="text-sm font-medium text-slate-300">{check.name}</span>
					<span class="flex-shrink-0 {statusDotClass(check.status)} w-2.5 h-2.5 rounded-full"></span>
				</div>
				<p class="text-xs {statusTextClass(check.status)} font-medium">{check.message}</p>
				{#if check.latencyMs !== undefined}
					<p class="text-xs text-slate-500 mt-1">{check.latencyMs}ms</p>
				{/if}
			</div>
		{/each}
	</div>

	<!-- Token + last-run row -->
	<div class="grid grid-cols-1 md:grid-cols-2 gap-4">
		<!-- Canvas API Token status -->
		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-sm font-semibold text-slate-200">Canvas API Token</h2>
				<a href="/token" class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">Rotate →</a>
			</div>

			{#if tokenStatus.isSet && tokenStatus.daysElapsed !== null}
				<!-- Progress bar -->
				<div class="relative h-2 rounded-full bg-slate-700 overflow-hidden mb-3">
					<div
						class="absolute inset-y-0 left-0 rounded-full transition-all {tokenLevelClass(tokenStatus.level)}"
						style="width: {tokenProgress()}%"
					></div>
					<!-- Warning zone marker at 83% (when 14 days remain of 90) -->
					<div class="absolute inset-y-0 bg-yellow-600/30" style="left: 83.3%; right: 0;"></div>
				</div>
				<div class="flex items-center justify-between">
					<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {tokenBadgeClass(tokenStatus.level)}">
						{tokenLabel(tokenStatus.level, tokenStatus.daysRemaining)}
					</span>
					<span class="text-xs text-slate-500">
						{tokenStatus.daysElapsed}d / {tokenStatus.daysTotal}d used
					</span>
				</div>
				{#if tokenStatus.issuedAt}
					<p class="text-xs text-slate-500 mt-2">
						Issued {new Date(tokenStatus.issuedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
					</p>
				{/if}
			{:else if tokenStatus.isSet}
				<div class="flex items-center gap-2">
					<span class="status-dot-yellow"></span>
					<span class="text-sm text-yellow-400">Token set, issue date unknown</span>
				</div>
			{:else}
				<div class="flex items-center gap-2">
					<span class="status-dot-red"></span>
					<span class="text-sm text-red-400">Token not configured</span>
				</div>
				<a href="/token" class="btn-primary mt-3 text-xs">Set token</a>
			{/if}
		</div>

		<!-- Last run times -->
		<div class="card">
			<h2 class="text-sm font-semibold text-slate-200 mb-4">Last Run Times</h2>
			<div class="space-y-4">
				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						<div class="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4 text-indigo-400">
								<path d="M1 3.5A1.5 1.5 0 0 1 2.5 2h10.768a1.5 1.5 0 0 1 1.354 2.139l-1.964 4.5A1.5 1.5 0 0 1 11.304 9.5H5.124a1.5 1.5 0 0 0-1.5 1.5v.5H12a.75.75 0 0 1 0 1.5H3a.75.75 0 0 1-.75-.75v-1.25A3 3 0 0 1 5.124 8H11.304l1.964-4.5H2.5a.75.75 0 0 1 0-1.5H1A1.5 1.5 0 0 1 1 3.5Z"/>
							</svg>
						</div>
						<div>
							<p class="text-sm font-medium text-slate-200">Canvas Sync</p>
							<p class="text-xs text-slate-500">Assignments → CalDAV</p>
						</div>
					</div>
					<span class="text-sm text-slate-300">{lastSync}</span>
				</div>

				<div class="h-px bg-slate-700"></div>

				<div class="flex items-center justify-between">
					<div class="flex items-center gap-2">
						<div class="flex h-7 w-7 items-center justify-center rounded-md bg-slate-700">
							<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4 text-purple-400">
								<path d="M11.97 1.35a.75.75 0 0 0-1.06 0L9.565 2.695A4.07 4.07 0 0 0 8 2.5a4.5 4.5 0 1 0 4.5 4.5c0-.539-.095-1.056-.269-1.535l1.04-1.039a.75.75 0 0 0 0-1.06l-1.3-1.016ZM12 7a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z"/>
							</svg>
						</div>
						<div>
							<p class="text-sm font-medium text-slate-200">AI Notes</p>
							<p class="text-xs text-slate-500">Canvas → Outline</p>
						</div>
					</div>
					<span class="text-sm text-slate-300">{lastNotes}</span>
				</div>
			</div>

			<div class="mt-4 pt-4 border-t border-slate-700">
				<a href="/triggers" class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">
					Run manually →
				</a>
			</div>
		</div>
	</div>

	<!-- Recent jobs (k8s mode) -->
	{#if recentJobs.length > 0}
		<div class="card">
			<div class="flex items-center justify-between mb-4">
				<h2 class="text-sm font-semibold text-slate-200">Recent Manual Jobs</h2>
				<a href="/triggers" class="text-xs text-indigo-400 hover:text-indigo-300 transition-colors">View all →</a>
			</div>
			<div class="space-y-2">
				{#each recentJobs as job}
					<div class="flex items-center justify-between rounded-lg bg-slate-700/50 px-3 py-2">
						<div class="flex items-center gap-3 min-w-0">
							<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium
							             {job.type === 'sync' ? 'bg-indigo-900/40 text-indigo-300 border border-indigo-800'
							                                  : 'bg-purple-900/40 text-purple-300 border border-purple-800'}">
								{job.type}
							</span>
							<span class="text-sm text-slate-300 truncate font-mono">{job.name}</span>
						</div>
						<div class="flex items-center gap-3 flex-shrink-0 ml-3">
							<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {jobStatusBadge(job.status)}">
								{job.status}
							</span>
							<span class="text-xs text-slate-500">{relTime(job.startTime)}</span>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else if data.mode === 'docker'}
		<div class="card border-dashed border-slate-600">
			<p class="text-sm text-slate-400">
				Running in <strong class="text-slate-300">Docker mode</strong> — no Kubernetes job history available.
				Use the <a href="/triggers" class="text-indigo-400 hover:text-indigo-300">Triggers</a> page to run scripts manually.
			</p>
		</div>
	{/if}
</div>
