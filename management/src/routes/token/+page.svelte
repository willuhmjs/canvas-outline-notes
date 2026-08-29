<script lang="ts">
	import { enhance } from '$app/forms';
	import type { PageData, ActionData } from './$types';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	const { tokenStatus, tokenLength } = $derived(data);

	let showToken = $state(false);

	function progressPercent(): number {
		if (!tokenStatus.isSet || tokenStatus.daysElapsed === null) return 0;
		return Math.min(100, Math.max(0, (tokenStatus.daysElapsed / tokenStatus.daysTotal) * 100));
	}

	function barColorClass(): string {
		if (tokenStatus.level === 'expired') return 'bg-red-500';
		if (tokenStatus.level === 'warning') return 'bg-yellow-500';
		return 'bg-green-500';
	}

	function badgeClass(): string {
		if (tokenStatus.level === 'expired') return 'bg-red-900/40 text-red-400 border border-red-800';
		if (tokenStatus.level === 'warning') return 'bg-yellow-900/40 text-yellow-400 border border-yellow-800';
		if (tokenStatus.level === 'healthy') return 'bg-green-900/40 text-green-400 border border-green-800';
		return 'bg-slate-700 text-slate-400 border border-slate-600';
	}

	function statusLabel(): string {
		if (!tokenStatus.isSet) return 'Not configured';
		if (tokenStatus.level === 'expired') return `Expired ${Math.abs(tokenStatus.daysRemaining ?? 0)} days ago`;
		if (tokenStatus.level === 'warning') return `Expiring in ${tokenStatus.daysRemaining} days — renew soon`;
		if (tokenStatus.level === 'healthy') return `Valid — ${tokenStatus.daysRemaining} days remaining`;
		return 'Unknown status (missing issue date)';
	}

	function issuedLabel(): string {
		if (!tokenStatus.issuedAt) return '';
		try {
			return new Date(tokenStatus.issuedAt).toLocaleDateString('en-US', {
				weekday: 'long',
				year: 'numeric',
				month: 'long',
				day: 'numeric'
			});
		} catch {
			return tokenStatus.issuedAt;
		}
	}

	function estimatedExpiry(): string {
		if (!tokenStatus.issuedAt) return '';
		try {
			const issued = new Date(tokenStatus.issuedAt);
			const expiry = new Date(issued.getTime() + tokenStatus.daysTotal * 86_400_000);
			return expiry.toLocaleDateString('en-US', {
				weekday: 'long',
				year: 'numeric',
				month: 'long',
				day: 'numeric'
			});
		} catch {
			return '';
		}
	}
</script>

<svelte:head>
	<title>Token — Canvas Management</title>
</svelte:head>

<div class="p-8 max-w-2xl mx-auto space-y-8">
	<div>
		<h1 class="text-2xl font-semibold text-slate-100">Canvas API Token</h1>
		<p class="text-sm text-slate-400 mt-1">
			Canvas personal access tokens expire after ~90 days. Rotate here to keep sync running.
		</p>
	</div>

	<!-- Current status card -->
	<div class="card space-y-5">
		<h2 class="text-base font-semibold text-slate-200">Current Token Status</h2>

		{#if tokenStatus.isSet && tokenStatus.daysElapsed !== null}
			<!-- Expiry bar -->
			<div class="space-y-2">
				<div class="flex items-center justify-between text-xs text-slate-400">
					<span>Issued</span>
					<span>~Expires</span>
				</div>
				<div class="relative h-3 rounded-full bg-slate-700 overflow-hidden">
					<div
						class="absolute inset-y-0 left-0 rounded-full transition-all {barColorClass()}"
						style="width: {progressPercent()}%"
					></div>
					<!-- Warning zone: last 14 days = 14/90 ≈ 15.6% from right -->
					<div class="absolute inset-y-0 bg-yellow-900/30 border-l border-yellow-700/50"
					     style="left: {(76 / 90) * 100}%; right: 0">
					</div>
				</div>
				<div class="flex items-center justify-between text-xs text-slate-500">
					{#if tokenStatus.issuedAt}
						<span>{new Date(tokenStatus.issuedAt).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}</span>
					{:else}
						<span>Unknown</span>
					{/if}
					<span>
						{tokenStatus.daysElapsed}d / {tokenStatus.daysTotal}d
					</span>
					{#if tokenStatus.issuedAt}
						<span>{estimatedExpiry()
							? new Date(new Date(tokenStatus.issuedAt).getTime() + tokenStatus.daysTotal * 86_400_000)
								.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
							: '?'}</span>
					{:else}
						<span>Unknown</span>
					{/if}
				</div>
			</div>

			<div class="flex items-center justify-between rounded-lg bg-slate-700/60 px-4 py-3">
				<div>
					<p class="text-sm font-medium {tokenStatus.level === 'healthy' ? 'text-green-400' : tokenStatus.level === 'warning' ? 'text-yellow-400' : 'text-red-400'}">
						{statusLabel()}
					</p>
					{#if tokenStatus.issuedAt}
						<p class="text-xs text-slate-500 mt-0.5">Last rotated: {issuedLabel()}</p>
					{/if}
				</div>
				<span class="inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium {badgeClass()}">
					{#if tokenStatus.level === 'healthy'}
						Valid
					{:else if tokenStatus.level === 'warning'}
						Expiring
					{:else if tokenStatus.level === 'expired'}
						Expired
					{:else}
						Unknown
					{/if}
				</span>
			</div>

			{#if tokenLength}
				<p class="text-xs text-slate-500">
					Token length: {tokenLength} characters
				</p>
			{/if}
		{:else if tokenStatus.isSet}
			<div class="flex items-center gap-3 rounded-lg bg-yellow-900/20 border border-yellow-800 px-4 py-3">
				<div class="status-dot-yellow"></div>
				<div>
					<p class="text-sm font-medium text-yellow-400">Token is set but issue date is missing</p>
					<p class="text-xs text-slate-400 mt-0.5">
						Paste a new token below to record the issue date and enable the expiry bar.
					</p>
				</div>
			</div>
		{:else}
			<div class="flex items-center gap-3 rounded-lg bg-red-900/20 border border-red-800 px-4 py-3">
				<div class="status-dot-red"></div>
				<div>
					<p class="text-sm font-medium text-red-400">No token configured</p>
					<p class="text-xs text-slate-400 mt-0.5">Canvas sync and completion tracking won't work without a token.</p>
				</div>
			</div>
		{/if}
	</div>

	<!-- Instructions card -->
	<div class="card space-y-3 border-slate-700/60">
		<h2 class="text-base font-semibold text-slate-200">How to get a new token</h2>
		<ol class="text-sm text-slate-300 space-y-2 list-decimal list-inside">
			<li>Open Canvas and go to <strong class="text-slate-100">Account → Settings</strong></li>
			<li>Scroll to <strong class="text-slate-100">Approved Integrations</strong></li>
			<li>Click <strong class="text-slate-100">+ New Access Token</strong></li>
			<li>Enter a purpose (e.g. "canvas-sync") — set no expiry date (Canvas caps them at ~90 days anyway)</li>
			<li>Click <strong class="text-slate-100">Generate Token</strong> and copy it immediately</li>
			<li>Paste it in the form below and click <strong class="text-slate-100">Save Token</strong></li>
		</ol>
		<p class="text-xs text-slate-500">
			Note: Canvas doesn't expose the real expiry date via API, so the bar above is an estimate
			based on the ~90-day cap from when the token was entered here.
		</p>
	</div>

	<!-- Paste form -->
	<div class="card space-y-4">
		<h2 class="text-base font-semibold text-slate-200">Paste New Token</h2>

		{#if (form as Record<string, unknown> | null)?.success}
			<div class="flex items-center gap-3 rounded-lg bg-green-900/20 border border-green-800 px-4 py-3">
				<div class="status-dot-green"></div>
				<p class="text-sm text-green-400">
					Token saved. Sync will use the new token on the next run.
				</p>
			</div>
		{/if}

		{#if (form as Record<string, unknown> | null)?.error}
			<div class="rounded-lg bg-red-900/20 border border-red-800 px-4 py-3">
				<p class="text-sm text-red-400">{(form as Record<string, unknown>).error as string}</p>
			</div>
		{/if}

		<form method="POST" action="?/save" use:enhance class="space-y-4">
			<div>
				<label class="form-label" for="token">Access Token</label>
				<div class="relative">
					<input
						id="token"
						name="token"
						type={showToken ? 'text' : 'password'}
						class="form-input pr-16 font-mono text-sm"
						placeholder="Paste your Canvas access token here"
						autocomplete="off"
						required
					/>
					<button
						type="button"
						onclick={() => (showToken = !showToken)}
						class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5 rounded"
					>
						{showToken ? 'Hide' : 'Show'}
					</button>
				</div>
				<p class="text-xs text-slate-500 mt-1">
					The token is stored securely — {#if data.mode === 'kubernetes'}in the <code class="text-slate-300">canvas-sync-secrets</code> Kubernetes Secret{:else}in <code class="text-slate-300">/data/settings.json</code>{/if}.
				</p>
			</div>

			<div class="flex justify-end">
				<button type="submit" class="btn-primary">
					Save Token
				</button>
			</div>
		</form>
	</div>
</div>
