<script lang="ts">
	import type { PageData } from './$types';
	import type { DockerJobRecord, K8sJob } from '$lib/types';

	let { data }: { data: PageData } = $props();

	type JobWithLogs = K8sJob & { logs: string };

	/** Normalized shape that covers both k8s job-with-logs and docker job records */
	interface DisplayJob {
		name: string;
		type: string;
		status: string;
		startTime: string | null;
		endTime: string | null;
		logs: string;
	}

	let activeTab = $state<'sync' | 'notes'>('sync');
	let expandedJob = $state<string | null>(null);

	function relTime(iso: string | null): string {
		if (!iso) return '—';
		const diff = Date.now() - new Date(iso).getTime();
		const s = Math.floor(diff / 1000);
		if (s < 0) return 'just now';
		if (s < 60) return `${s}s ago`;
		if (s < 3600) return `${Math.floor(s / 60)}m ago`;
		if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
		return `${Math.floor(s / 86400)}d ago`;
	}

	function duration(start: string | null, end: string | null): string {
		if (!start || !end) return '';
		const ms = new Date(end).getTime() - new Date(start).getTime();
		if (ms < 1000) return `${ms}ms`;
		if (ms < 60_000) return `${(ms / 1000).toFixed(1)}s`;
		return `${Math.floor(ms / 60_000)}m ${((ms % 60_000) / 1000).toFixed(0)}s`;
	}

	function statusBadge(status: string): string {
		if (status === 'succeeded') return 'bg-green-900/40 text-green-400 border border-green-800';
		if (status === 'failed') return 'bg-red-900/40 text-red-400 border border-red-800';
		if (status === 'running') return 'bg-indigo-900/40 text-indigo-400 border border-indigo-800';
		return 'bg-slate-700 text-slate-400 border border-slate-600';
	}

	function toggleExpand(name: string) {
		expandedJob = expandedJob === name ? null : name;
	}

	// Normalize to a consistent display shape regardless of mode
	function toDisplayJobs(source: JobWithLogs[] | DockerJobRecord[]): DisplayJob[] {
		return (source as Array<Partial<JobWithLogs & DockerJobRecord>>).map((j) => ({
			name: j.name ?? '?',
			type: j.type ?? 'unknown',
			status: j.status ?? 'unknown',
			startTime: j.startTime ?? null,
			endTime: (j as Partial<DockerJobRecord>).endTime ?? (j as Partial<JobWithLogs>).completionTime ?? null,
			logs: (j as Partial<JobWithLogs>).logs ?? (j as Partial<DockerJobRecord>).output ?? ''
		}));
	}

	const activeJobs = $derived<DisplayJob[]>(
		data.mode === 'kubernetes'
			? toDisplayJobs(activeTab === 'sync' ? (data.syncJobs as JobWithLogs[]) : (data.notesJobs as JobWithLogs[]))
			: toDisplayJobs(
				((data.dockerHistory ?? []) as DockerJobRecord[]).filter((j) => j.type === activeTab)
			)
	);
</script>

<svelte:head>
	<title>Logs — Canvas Management</title>
</svelte:head>

<div class="p-8 max-w-4xl mx-auto space-y-6">
	<div>
		<h1 class="text-2xl font-semibold text-slate-100">Logs</h1>
		<p class="text-sm text-slate-400 mt-1">
			{#if data.mode === 'kubernetes'}
				Logs from the last 3 completed manual job runs per script.
			{:else}
				Output from manually triggered Docker subprocess runs.
			{/if}
		</p>
	</div>

	<!-- Tab bar -->
	<div class="flex gap-1 rounded-xl bg-slate-800 border border-slate-700 p-1 w-fit">
		{#each ['sync', 'notes'] as tab}
			<button
				type="button"
				onclick={() => { activeTab = tab as 'sync' | 'notes'; expandedJob = null; }}
				class="flex items-center gap-2 rounded-lg px-4 py-2 text-sm font-medium transition-colors
				       {activeTab === tab
				         ? 'bg-slate-700 text-slate-100 shadow-sm'
				         : 'text-slate-400 hover:text-slate-200'}"
			>
				{#if tab === 'sync'}
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4">
						<path fill-rule="evenodd" d="M13.836 2.477a.75.75 0 0 1 .75.75v3.182a.75.75 0 0 1-.75.75h-3.182a.75.75 0 0 1 0-1.5h1.37l-.84-.841a4.5 4.5 0 0 0-7.08.932.75.75 0 0 1-1.3-.75 6 6 0 0 1 9.44-1.242l.842.84V3.227a.75.75 0 0 1 .75-.75Zm-.911 7.5A.75.75 0 0 1 13.199 11a6 6 0 0 1-9.44 1.241l-.84-.84v1.371a.75.75 0 0 1-1.5 0V9.591a.75.75 0 0 1 .75-.75H5.35a.75.75 0 0 1 0 1.5H3.98l.841.841a4.5 4.5 0 0 0 7.08-.932.75.75 0 0 1 1.025-.273Z" clip-rule="evenodd"/>
					</svg>
					Sync
				{:else}
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 16 16" fill="currentColor" class="w-4 h-4">
						<path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 0 0 3 3.5v9A1.5 1.5 0 0 0 4.5 14h7a1.5 1.5 0 0 0 1.5-1.5V6.621a1.5 1.5 0 0 0-.44-1.06L9.94 2.439A1.5 1.5 0 0 0 8.878 2H4.5Zm2 4.75a.75.75 0 0 0 0 1.5h3a.75.75 0 0 0 0-1.5h-3Zm0 3a.75.75 0 0 0 0 1.5h3a.75.75 0 0 0 0-1.5h-3Z" clip-rule="evenodd"/>
					</svg>
					Notes
				{/if}
			</button>
		{/each}
	</div>

	<!-- Log entries -->
	{#if activeJobs.length === 0}
		<div class="card border-dashed border-slate-600 text-center py-12">
			<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-10 h-10 text-slate-600 mx-auto mb-3">
				<path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 0 0 3 3.5v13A1.5 1.5 0 0 0 4.5 18h11a1.5 1.5 0 0 0 1.5-1.5V7.621a1.5 1.5 0 0 0-.44-1.06l-4.12-4.122A1.5 1.5 0 0 0 11.378 2H4.5Zm2.25 8.5a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Zm0 3a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Zm0-6a.75.75 0 0 0 0 1.5h3.5a.75.75 0 0 0 0-1.5h-3.5Z" clip-rule="evenodd"/>
			</svg>
			<p class="text-slate-400 text-sm">No {activeTab} logs yet.</p>
			{#if data.mode === 'kubernetes'}
				<p class="text-slate-500 text-xs mt-1">
					Trigger a manual run on the <a href="/triggers" class="text-indigo-400 hover:text-indigo-300">Triggers</a> page to see logs here.
				</p>
			{:else}
				<p class="text-slate-500 text-xs mt-1">
					Use the <a href="/triggers" class="text-indigo-400 hover:text-indigo-300">Triggers</a> page to run a job and capture output.
				</p>
			{/if}
		</div>
	{:else}
		<div class="space-y-4">
			{#each activeJobs as job}
				{@const isExpanded = expandedJob === job.name}
				<div class="card space-y-3">
					<!-- Job header -->
					<div class="flex items-center justify-between flex-wrap gap-2">
						<div class="flex items-center gap-2 min-w-0">
							<button
								type="button"
								onclick={() => toggleExpand(job.name)}
								class="flex items-center gap-2 text-left group"
							>
								<svg
									xmlns="http://www.w3.org/2000/svg"
									viewBox="0 0 20 20"
									fill="currentColor"
									class="w-4 h-4 text-slate-500 flex-shrink-0 transition-transform {isExpanded ? 'rotate-90' : ''}"
								>
									<path fill-rule="evenodd" d="M8.22 5.22a.75.75 0 0 1 1.06 0l4.25 4.25a.75.75 0 0 1 0 1.06l-4.25 4.25a.75.75 0 0 1-1.06-1.06L11.94 10 8.22 6.28a.75.75 0 0 1 0-1.06Z" clip-rule="evenodd"/>
								</svg>
								<span class="text-sm font-mono text-slate-300 group-hover:text-slate-100 transition-colors truncate">
									{job.name}
								</span>
							</button>
						</div>
						<div class="flex items-center gap-2 flex-shrink-0">
							<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {statusBadge(job.status)}">
								{job.status}
							</span>
							<span class="text-xs text-slate-500">{relTime(job.startTime)}</span>
							{#if job.endTime && job.startTime}
								<span class="text-xs text-slate-600">
									{duration(job.startTime, job.endTime)}
								</span>
							{/if}
						</div>
					</div>

					<!-- Expanded log view -->
					{#if isExpanded}
						{@const logContent = job.logs.trim()}
						{#if logContent}
							<div class="rounded-lg bg-slate-900 border border-slate-700 overflow-hidden">
								<div class="flex items-center justify-between px-3 py-1.5 bg-slate-800 border-b border-slate-700">
									<span class="text-xs text-slate-500 font-mono">stdout / stderr</span>
									{#if data.mode === 'kubernetes'}
										<span class="text-xs text-slate-600">last 150 lines</span>
									{/if}
								</div>
								<pre class="text-xs font-mono text-slate-300 p-4 overflow-auto max-h-[32rem] whitespace-pre-wrap leading-relaxed">{logContent}</pre>
							</div>
						{:else}
							<p class="text-sm text-slate-500 italic">No log output captured.</p>
						{/if}
					{/if}
				</div>
			{/each}
		</div>
	{/if}

	{#if data.mode === 'docker' && data.dockerHistory && data.dockerHistory.length === 0}
		<div class="card border-dashed border-slate-600">
			<p class="text-sm text-slate-400">
				<strong class="text-slate-300">Docker mode:</strong> Script output is captured when you trigger jobs
				from the <a href="/triggers" class="text-indigo-400 hover:text-indigo-300">Triggers</a> page.
				For CronJob output, use <code class="text-slate-300">docker logs</code> on the container.
			</p>
		</div>
	{/if}
</div>
