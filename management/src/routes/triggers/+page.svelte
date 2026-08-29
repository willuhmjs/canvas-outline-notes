<script lang="ts">
	import { enhance } from '$app/forms';
	import type { PageData, ActionData } from './$types';
	import type { DockerJobRecord } from '$lib/types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	let syncLoading = $state(false);
	let notesLoading = $state(false);
	let alarmLoading = $state(false);

	function formResult(action: string) {
		if (!form) return null;
		const f = form as Record<string, unknown>;
		if (f.action !== action) return null;
		return f;
	}

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
		if (!start || !end) return '—';
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

	function typeBadge(type: string): string {
		if (type === 'sync') return 'bg-indigo-900/40 text-indigo-300 border border-indigo-800';
		if (type === 'notes') return 'bg-purple-900/40 text-purple-300 border border-purple-800';
		return 'bg-slate-700 text-slate-400 border border-slate-600';
	}

	// Compute combined job list for display
	const jobs = $derived(
		data.mode === 'kubernetes'
			? data.recentJobs
			: data.dockerHistory
	);
</script>

<svelte:head>
	<title>Triggers — Canvas Management</title>
</svelte:head>

<div class="p-8 max-w-3xl mx-auto space-y-8">
	<div>
		<h1 class="text-2xl font-semibold text-slate-100">Triggers</h1>
		<p class="text-sm text-slate-400 mt-1">
			{#if data.mode === 'kubernetes'}
				Creates one-off Kubernetes Jobs from the existing CronJob templates.
			{:else}
				Runs the Python scripts as subprocesses (Docker mode).
			{/if}
		</p>
	</div>

	<!-- Action buttons -->
	<div class="grid grid-cols-1 sm:grid-cols-2 gap-4">
		<!-- Run Sync -->
		<div class="card space-y-4">
			<div class="flex items-center gap-3">
				<div class="flex h-10 w-10 items-center justify-center rounded-xl bg-indigo-600/20 border border-indigo-700">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-indigo-400">
						<path fill-rule="evenodd" d="M15.312 11.424a5.5 5.5 0 0 1-9.201 2.466l-.312-.311h2.433a.75.75 0 0 0 0-1.5H3.989a.75.75 0 0 0-.75.75v4.242a.75.75 0 0 0 1.5 0v-2.43l.31.31a7 7 0 0 0 11.712-3.138.75.75 0 0 0-1.449-.39Zm1.23-3.723a.75.75 0 0 0 .219-.53V3.928a.75.75 0 0 0-1.5 0v2.43l-.31-.31A7 7 0 0 0 3.239 9.187a.75.75 0 1 0 1.448.389A5.5 5.5 0 0 1 13.89 6.11l.311.31h-2.432a.75.75 0 0 0 0 1.5h4.243a.75.75 0 0 0 .53-.219Z" clip-rule="evenodd"/>
					</svg>
				</div>
				<div>
					<h2 class="text-sm font-semibold text-slate-200">Run Sync Now</h2>
					<p class="text-xs text-slate-400">Canvas → CalDAV (assignments)</p>
				</div>
			</div>

			{#if formResult('sync')?.success}
				<div class="rounded-lg bg-green-900/20 border border-green-800 px-3 py-2">
					<p class="text-sm text-green-400">
						Job started: <code class="font-mono text-xs">{formResult('sync')?.jobName}</code>
					</p>
				</div>
			{:else if formResult('sync')?.error}
				<div class="rounded-lg bg-red-900/20 border border-red-800 px-3 py-2">
					<p class="text-sm text-red-400">{formResult('sync')?.error as string}</p>
				</div>
			{/if}

			<form
				method="POST"
				action="?/sync"
				use:enhance={() => {
					syncLoading = true;
					return async ({ update }) => {
						await update();
						syncLoading = false;
					};
				}}
			>
				<button type="submit" class="btn-primary w-full justify-center" disabled={syncLoading}>
					{#if syncLoading}
						<svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
						</svg>
						Starting…
					{:else}
						Run Canvas Sync
					{/if}
				</button>
			</form>
		</div>

		<!-- Run Notes -->
		<div class="card space-y-4">
			<div class="flex items-center gap-3">
				<div class="flex h-10 w-10 items-center justify-center rounded-xl bg-purple-600/20 border border-purple-700">
					<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-purple-400">
						<path d="M10.75 16.82A7.462 7.462 0 0 1 10 17c-.385 0-.766-.02-1.141-.06l.993-1.57a5.987 5.987 0 0 0 .898.06Zm-2.845-.47-1.072 1.697A7.501 7.501 0 0 1 3.51 14.9l1.912-.518a5.988 5.988 0 0 0 2.483 1.968ZM3.012 12.62l-1.91.516a7.466 7.466 0 0 1-.102-1.136C1 7.375 4.375 4 8.5 4h1.5v2h-1.5c-2.485 0-4.5 2.015-4.5 4.5 0 .731.176 1.42.487 2.03v.09ZM12 6h1.5A6.5 6.5 0 0 1 20 12.5a6.454 6.454 0 0 1-.537 2.592l-1.748-.748A4.46 4.46 0 0 0 18 12.5C18 9.46 15.54 7 12.5 7H12V5Z"/>
					</svg>
				</div>
				<div>
					<h2 class="text-sm font-semibold text-slate-200">Run Notes Now</h2>
					<p class="text-xs text-slate-400">Canvas → Outline (AI study notes)</p>
				</div>
			</div>

			{#if formResult('notes')?.success}
				<div class="rounded-lg bg-green-900/20 border border-green-800 px-3 py-2">
					<p class="text-sm text-green-400">
						Job started: <code class="font-mono text-xs">{formResult('notes')?.jobName}</code>
					</p>
				</div>
			{:else if formResult('notes')?.error}
				<div class="rounded-lg bg-red-900/20 border border-red-800 px-3 py-2">
					<p class="text-sm text-red-400">{formResult('notes')?.error as string}</p>
				</div>
			{/if}

			<form
				method="POST"
				action="?/notes"
				use:enhance={() => {
					notesLoading = true;
					return async ({ update }) => {
						await update();
						notesLoading = false;
					};
				}}
			>
				<button type="submit" class="btn-primary w-full justify-center" disabled={notesLoading}>
					{#if notesLoading}
						<svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
							<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
							<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
						</svg>
						Starting…
					{:else}
						Run AI Notes
					{/if}
				</button>
			</form>
		</div>
	</div>

	<!-- Clear Credential Alarm -->
	<div class="card space-y-4">
		<div class="flex items-center gap-3">
			<div class="flex h-10 w-10 items-center justify-center rounded-xl bg-red-600/20 border border-red-800">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-red-400">
					<path fill-rule="evenodd" d="M10 18a8 8 0 1 0 0-16 8 8 0 0 0 0 16ZM8.28 7.22a.75.75 0 0 0-1.06 1.06L8.94 10l-1.72 1.72a.75.75 0 1 0 1.06 1.06L10 11.06l1.72 1.72a.75.75 0 1 0 1.06-1.06L11.06 10l1.72-1.72a.75.75 0 0 0-1.06-1.06L10 8.94 8.28 7.22Z" clip-rule="evenodd"/>
				</svg>
			</div>
			<div>
				<h2 class="text-sm font-semibold text-slate-200">Clear Credential Alarm</h2>
				<p class="text-xs text-slate-400">
					Deletes the "FIX ME" VTODO that notes.py raises on a 401/403 error.
					It auto-resolves on the next successful run anyway — use this to clear it immediately.
				</p>
			</div>
		</div>

		{#if formResult('clearAlarm')?.success}
			<div class="rounded-lg bg-green-900/20 border border-green-800 px-3 py-2">
				<p class="text-sm text-green-400">Credential alarm VTODO deleted (or was already gone).</p>
			</div>
		{:else if formResult('clearAlarm')?.error}
			<div class="rounded-lg bg-red-900/20 border border-red-800 px-3 py-2">
				<p class="text-sm text-red-400">{formResult('clearAlarm')?.error as string}</p>
			</div>
		{/if}

		<form
			method="POST"
			action="?/clearAlarm"
			use:enhance={() => {
				alarmLoading = true;
				return async ({ update }) => {
					await update();
					alarmLoading = false;
				};
			}}
		>
			<button type="submit" class="btn-danger" disabled={alarmLoading}>
				{#if alarmLoading}
					<svg class="animate-spin w-4 h-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
						<circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
						<path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
					</svg>
					Clearing…
				{:else}
					Clear Credential Alarm
				{/if}
			</button>
		</form>
	</div>

	<!-- Job History -->
	<div class="card">
		<h2 class="text-base font-semibold text-slate-200 mb-4">
			Job History
			{#if data.mode === 'docker'}
				<span class="ml-2 text-xs font-normal text-slate-400">(Docker subprocess records)</span>
			{/if}
		</h2>

		{#if jobs.length === 0}
			<p class="text-sm text-slate-500 text-center py-6">No manual jobs yet.</p>
		{:else}
			<div class="space-y-2">
				{#each jobs as job}
					{@const j = job as typeof job & Partial<DockerJobRecord>}
					<div class="rounded-lg bg-slate-700/50 border border-slate-600/50 p-3">
						<div class="flex items-center justify-between flex-wrap gap-2">
							<div class="flex items-center gap-2 min-w-0">
								<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium flex-shrink-0 {typeBadge(job.type)}">
									{job.type}
								</span>
								<span class="text-xs font-mono text-slate-300 truncate">{job.name}</span>
							</div>
							<div class="flex items-center gap-2 flex-shrink-0">
								<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium {statusBadge(job.status)}">
									{job.status}
								</span>
								<span class="text-xs text-slate-500">{relTime(job.startTime)}</span>
								{#if j.endTime && job.startTime}
									<span class="text-xs text-slate-600">({duration(job.startTime, j.endTime)})</span>
								{/if}
							</div>
						</div>

						<!-- Docker: show abbreviated output -->
						{#if data.mode === 'docker' && j.output}
							<pre class="mt-2 text-xs text-slate-400 bg-slate-800/50 rounded p-2 overflow-auto max-h-24 font-mono whitespace-pre-wrap">{j.output.slice(-800)}</pre>
						{/if}
					</div>
				{/each}
			</div>
		{/if}

		{#if data.mode === 'kubernetes' && jobs.length > 0}
			<p class="text-xs text-slate-500 mt-4">
				Jobs auto-delete 1 hour after completion (<code class="text-slate-400">ttlSecondsAfterFinished: 3600</code>).
				View full logs on the <a href="/logs" class="text-indigo-400 hover:text-indigo-300">Logs</a> page.
			</p>
		{/if}
	</div>
</div>
