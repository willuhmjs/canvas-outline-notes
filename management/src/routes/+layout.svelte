<script lang="ts">
	import '../app.css';
	import { page } from '$app/state';
	import type { LayoutData } from './$types';

	let { data, children }: { data: LayoutData; children: import('svelte').Snippet } = $props();

	const nav = [
		{
			href: '/',
			label: 'Dashboard',
			icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
				<path d="M2 10a8 8 0 1 1 16 0 8 8 0 0 1-16 0Zm8-5.5a.75.75 0 0 1 .75.75v4.69l2.78 2.78a.75.75 0 1 1-1.06 1.06L9.22 11.53A.75.75 0 0 1 9 11V5.25A.75.75 0 0 1 10 4.5Z" clip-rule="evenodd" fill-rule="evenodd"/>
			</svg>`
		},
		{
			href: '/settings',
			label: 'Settings',
			icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
				<path fill-rule="evenodd" d="M7.84 1.804A1 1 0 0 1 8.82 1h2.36a1 1 0 0 1 .98.804l.331 1.652a6.993 6.993 0 0 1 1.929 1.115l1.598-.54a1 1 0 0 1 1.186.447l1.18 2.044a1 1 0 0 1-.205 1.251l-1.267 1.113a7.047 7.047 0 0 1 0 2.228l1.267 1.113a1 1 0 0 1 .206 1.25l-1.18 2.045a1 1 0 0 1-1.187.447l-1.598-.54a6.993 6.993 0 0 1-1.929 1.115l-.33 1.652a1 1 0 0 1-.98.804H8.82a1 1 0 0 1-.98-.804l-.331-1.652a6.993 6.993 0 0 1-1.929-1.115l-1.598.54a1 1 0 0 1-1.186-.447l-1.18-2.044a1 1 0 0 1 .205-1.251l1.267-1.114a7.05 7.05 0 0 1 0-2.227L1.821 7.773a1 1 0 0 1-.206-1.25l1.18-2.045a1 1 0 0 1 1.187-.447l1.598.54A6.992 6.992 0 0 1 7.51 3.456l.33-1.652ZM10 13a3 3 0 1 0 0-6 3 3 0 0 0 0 6Z" clip-rule="evenodd"/>
			</svg>`
		},
		{
			href: '/token',
			label: 'Token',
			icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
				<path fill-rule="evenodd" d="M8 7a5 5 0 1 1 3.61 4.804l-1.903 1.903A1 1 0 0 1 9 14H8v1a1 1 0 0 1-1 1H6v1a1 1 0 0 1-1 1H3a1 1 0 0 1-1-1v-2a1 1 0 0 1 .293-.707L7.196 9.39A5.002 5.002 0 0 1 8 7Zm5-3a.75.75 0 0 0 0 1.5A1.5 1.5 0 0 1 14.5 7 .75.75 0 0 0 16 7a3 3 0 0 0-3-3Z" clip-rule="evenodd"/>
			</svg>`
		},
		{
			href: '/triggers',
			label: 'Triggers',
			icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
				<path d="M6.3 2.84A1.5 1.5 0 0 1 8.5 4.134v11.733a1.5 1.5 0 0 1-2.2 1.294l-6-3.333C-.013 13.38 0 12.838 0 12V8c0-.838-.013-1.38.3-1.796l6-3.364ZM14.3 2.84A1.5 1.5 0 0 1 16.5 4.134v11.733a1.5 1.5 0 0 1-2.2 1.294l-6-3.333C8.3 13.595 8 13.09 8 12.5v-5c0-.59.3-1.095.3-1.666l6-4Zm0 0"/>
			</svg>`
		},
		{
			href: '/logs',
			label: 'Logs',
			icon: `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5">
				<path fill-rule="evenodd" d="M4.5 2A1.5 1.5 0 0 0 3 3.5v13A1.5 1.5 0 0 0 4.5 18h11a1.5 1.5 0 0 0 1.5-1.5V7.621a1.5 1.5 0 0 0-.44-1.06l-4.12-4.122A1.5 1.5 0 0 0 11.378 2H4.5Zm2.25 8.5a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Zm0 3a.75.75 0 0 0 0 1.5h6.5a.75.75 0 0 0 0-1.5h-6.5Zm0-6a.75.75 0 0 0 0 1.5h3.5a.75.75 0 0 0 0-1.5h-3.5Z" clip-rule="evenodd"/>
			</svg>`
		}
	];

	function isActive(href: string): boolean {
		const path = page.url.pathname;
		if (href === '/') return path === '/';
		return path.startsWith(href);
	}
</script>

<div class="flex h-full min-h-screen">
	<!-- Sidebar -->
	<aside class="fixed inset-y-0 left-0 z-50 flex w-56 flex-col bg-slate-800 border-r border-slate-700">
		<!-- Logo / title -->
		<div class="flex h-16 items-center gap-3 px-4 border-b border-slate-700 flex-shrink-0">
			<div class="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600">
				<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" class="w-5 h-5 text-white">
					<path d="M10.75 16.82A7.462 7.462 0 0 1 10 17c-.385 0-.766-.02-1.141-.06l.993-1.57a5.987 5.987 0 0 0 .898.06Zm-2.845-.47-1.072 1.697A7.501 7.501 0 0 1 3.51 14.9l1.912-.518a5.988 5.988 0 0 0 2.483 1.968ZM3.012 12.62l-1.91.516a7.466 7.466 0 0 1-.102-1.136C1 7.375 4.375 4 8.5 4h1.5v2h-1.5c-2.485 0-4.5 2.015-4.5 4.5 0 .731.176 1.42.487 2.03v.09ZM12 6h1.5A6.5 6.5 0 0 1 20 12.5a6.454 6.454 0 0 1-.537 2.592l-1.748-.748A4.46 4.46 0 0 0 18 12.5C18 9.46 15.54 7 12.5 7H12V5Z"/>
				</svg>
			</div>
			<div class="overflow-hidden">
				<p class="text-sm font-semibold text-slate-100 truncate">Canvas</p>
				<p class="text-xs text-slate-400 truncate">Management</p>
			</div>
		</div>

		<!-- Nav items -->
		<nav class="flex-1 overflow-y-auto py-4 px-2 space-y-0.5">
			{#each nav as item}
				<a
					href={item.href}
					class="group flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors
					       {isActive(item.href)
					         ? 'bg-indigo-600 text-white'
					         : 'text-slate-400 hover:bg-slate-700 hover:text-slate-100'}"
				>
					<!-- svelte-ignore a11y_unknown_aria_attribute -->
					<span class="flex-shrink-0 {isActive(item.href) ? 'text-white' : 'text-slate-500 group-hover:text-slate-300'}">
						{@html item.icon}
					</span>
					{item.label}
				</a>
			{/each}
		</nav>

		<!-- Footer: mode badge + username -->
		<div class="border-t border-slate-700 p-3 space-y-2 flex-shrink-0">
			<div class="flex items-center gap-2">
				<span class="inline-flex items-center rounded-full px-2 py-0.5 text-xs font-medium
				             {data.mode === 'kubernetes' ? 'bg-indigo-900 text-indigo-300' : 'bg-slate-700 text-slate-400'}">
					{data.mode === 'kubernetes' ? `k8s / ${data.namespace}` : 'docker'}
				</span>
			</div>
			{#if data.username}
				<div class="flex items-center gap-2 px-1">
					<div class="flex h-6 w-6 items-center justify-center rounded-full bg-slate-600 text-xs font-medium text-slate-200 flex-shrink-0">
						{data.username.slice(0, 1).toUpperCase()}
					</div>
					<span class="text-xs text-slate-400 truncate">{data.username}</span>
				</div>
			{/if}
		</div>
	</aside>

	<!-- Main content -->
	<main class="ml-56 flex-1 min-h-screen bg-slate-900">
		{@render children()}
	</main>
</div>
