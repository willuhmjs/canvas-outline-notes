<script lang="ts">
	import { enhance } from '$app/forms';
	import type { PageData, ActionData } from './$types';
	import {
		DEFAULT_PROMPT_ASSIGNMENT,
		DEFAULT_PROMPT_PRESENTATION,
		DEFAULT_PROMPT_TEXT_NOTES
	} from '$lib/prompts';

	let { data, form }: { data: PageData; form: ActionData } = $props();

	// Show/hide toggles for sensitive fields
	let showIcsUrl = $state(false);
	let showDavPassword = $state(false);
	let showOutlineToken = $state(false);
	let showChatKey = $state(false);

	// Active prompt tab
	let promptTab = $state<'assignment' | 'presentation' | 'text_notes'>('assignment');

	// Alarm trigger preset
	const ALARM_PRESETS = [
		{ value: 'PT1H', label: '1 hour' },
		{ value: 'PT6H', label: '6 hours' },
		{ value: 'PT12H', label: '12 hours' },
		{ value: 'PT24H', label: '24 hours' },
		{ value: 'custom', label: 'Custom (ISO 8601 duration)' }
	];

	// Compute alarm preset from loaded data (runs once at initialization)
	const _initAlarm = data.config.ALARM_TRIGGER ?? 'PT6H';
	const _isKnownPreset = ALARM_PRESETS.some((p) => p.value === _initAlarm && p.value !== 'custom');
	let alarmPreset = $state(_isKnownPreset ? _initAlarm : 'custom');
	let alarmCustom = $state(_isKnownPreset ? 'PT6H' : _initAlarm);

	// Chat models, queried from the configured OpenAI-compatible endpoint
	let models = $state(data.models ?? []);
	let modelsError = $state(data.modelsError ?? null);
	let fetchingModels = $state(false);

	const _initTextModel = data.config.CHAT_MODEL_TEXT ?? 'gpt-oss-120b';
	let textModelSelect = $state(models.includes(_initTextModel) ? _initTextModel : 'custom');
	let textModelCustom = $state(_initTextModel);

	const _initVisionModel = data.config.CHAT_MODEL_VISION ?? 'gemma-4-31b';
	let visionModelSelect = $state(models.includes(_initVisionModel) ? _initVisionModel : 'custom');
	let visionModelCustom = $state(_initVisionModel);

	function handleAiSubmit({ action }: { action: URL }) {
		if (action.search === '?/aiListModels') {
			fetchingModels = true;
			return async ({ result }: { result: { type: string; data?: Record<string, unknown> } }) => {
				fetchingModels = false;
				if (result.type === 'success' && result.data) {
					models = (result.data.models as string[]) ?? [];
					modelsError = null;
					if (models.includes(textModelCustom)) textModelSelect = textModelCustom;
					if (models.includes(visionModelCustom)) visionModelSelect = visionModelCustom;
				} else if (result.type === 'failure' && result.data) {
					modelsError = String(result.data.error ?? 'Failed to fetch models');
				}
				// Intentionally skip update()/invalidateAll — this must not reset
				// unsaved edits to other fields in the form.
			};
		}
		return async ({ update }: { update: () => Promise<void> }) => {
			await update();
		};
	}

	function sectionResult(section: string) {
		if (!form) return null;
		const f = form as Record<string, unknown>;
		if (f.section !== section) return null;
		return f;
	}

	function successMsg(section: string) {
		const r = sectionResult(section);
		return r?.success ? 'Settings saved.' : null;
	}

	function errorMsg(section: string) {
		const r = sectionResult(section);
		return r?.error ? String(r.error) : null;
	}
</script>

<svelte:head>
	<title>Settings — Canvas Management</title>
</svelte:head>

<div class="p-8 max-w-3xl mx-auto space-y-8">
	<div>
		<h1 class="text-2xl font-semibold text-slate-100">Settings</h1>
		<p class="text-sm text-slate-400 mt-1">Configure canvas-sync and canvas-notes behaviour</p>
	</div>

	<!-- ── Canvas ───────────────────────────────────────────────────── -->
	<div class="card space-y-5">
		<div class="flex items-center justify-between">
			<div>
				<h2 class="text-base font-semibold text-slate-100">Canvas</h2>
				<p class="text-xs text-slate-400 mt-0.5">Calendar feed and API configuration</p>
			</div>
		</div>

		<form method="POST" action="?/canvas" use:enhance class="space-y-4">
			<div>
				<label class="form-label" for="CANVAS_ICS_URL">
					ICS Feed URL
					<span class="text-slate-500 font-normal">(contains auth token)</span>
				</label>
				<div class="relative">
					<input
						id="CANVAS_ICS_URL"
						name="CANVAS_ICS_URL"
						type={showIcsUrl ? 'text' : 'password'}
						class="form-input pr-16"
						value={data.syncSecrets.CANVAS_ICS_URL ?? ''}
						placeholder="https://canvas.odu.edu/feeds/calendars/..."
						autocomplete="off"
					/>
					<button
						type="button"
						onclick={() => (showIcsUrl = !showIcsUrl)}
						class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5 rounded"
					>
						{showIcsUrl ? 'Hide' : 'Show'}
					</button>
				</div>
				<p class="text-xs text-slate-500 mt-1">
					Canvas → Account → Settings → Calendar Feed. Contains an auth token — treat as secret.
				</p>
			</div>

			<div>
				<label class="form-label" for="CANVAS_BASE_URL">Canvas Base URL</label>
				<input
					id="CANVAS_BASE_URL"
					name="CANVAS_BASE_URL"
					type="text"
					class="form-input"
					value={data.config.CANVAS_BASE_URL ?? ''}
					placeholder="https://canvas.odu.edu"
				/>
			</div>

			<div>
				<label class="form-label" for="COMPLETION_LOOKBACK_DAYS">
					Completion Lookback Days
				</label>
				<input
					id="COMPLETION_LOOKBACK_DAYS"
					name="COMPLETION_LOOKBACK_DAYS"
					type="number"
					min="1"
					max="365"
					class="form-input w-32"
					value={data.config.COMPLETION_LOOKBACK_DAYS ?? '30'}
				/>
				<p class="text-xs text-slate-500 mt-1">
					How many days past the due date to check Canvas for completion status.
				</p>
			</div>

			{#if successMsg('canvas')}
				<p class="text-sm text-green-400">{successMsg('canvas')}</p>
			{:else if errorMsg('canvas')}
				<p class="text-sm text-red-400">{errorMsg('canvas')}</p>
			{/if}

			<div class="flex justify-end pt-1">
				<button type="submit" class="btn-primary">Save Canvas settings</button>
			</div>
		</form>
	</div>

	<!-- ── CalDAV ─────────────────────────────────────────────────────── -->
	<div class="card space-y-5">
		<div>
			<h2 class="text-base font-semibold text-slate-100">CalDAV</h2>
			<p class="text-xs text-slate-400 mt-0.5">Davis server connection for task storage</p>
		</div>

		<form method="POST" action="?/caldav" use:enhance class="space-y-4">
			<div>
				<label class="form-label" for="DAV_BASE_URL">CalDAV Base URL</label>
				<input
					id="DAV_BASE_URL"
					name="DAV_BASE_URL"
					type="text"
					class="form-input"
					value={data.config.DAV_BASE_URL ?? ''}
					placeholder="http://davis.dav.svc.cluster.local:9000"
				/>
			</div>

			<div class="grid grid-cols-2 gap-4">
				<div>
					<label class="form-label" for="DAV_USERNAME">Username</label>
					<input
						id="DAV_USERNAME"
						name="DAV_USERNAME"
						type="text"
						class="form-input"
						value={data.syncSecrets.DAV_USERNAME ?? ''}
						autocomplete="off"
					/>
				</div>
				<div>
					<label class="form-label" for="DAV_PASSWORD">Password</label>
					<div class="relative">
						<input
							id="DAV_PASSWORD"
							name="DAV_PASSWORD"
							type={showDavPassword ? 'text' : 'password'}
							class="form-input pr-16"
							placeholder="Leave blank to keep existing"
							autocomplete="new-password"
						/>
						<button
							type="button"
							onclick={() => (showDavPassword = !showDavPassword)}
							class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5 rounded"
						>
							{showDavPassword ? 'Hide' : 'Show'}
						</button>
					</div>
				</div>
			</div>

			<div>
				<label class="form-label" for="DAV_CALENDAR_DISPLAYNAME">Calendar Name</label>
				<input
					id="DAV_CALENDAR_DISPLAYNAME"
					name="DAV_CALENDAR_DISPLAYNAME"
					type="text"
					class="form-input"
					value={data.config.DAV_CALENDAR_DISPLAYNAME ?? 'Academics'}
				/>
			</div>

			<div>
				<label class="form-label" for="ALARM_TRIGGER_preset">
					Task Reminder Timing
				</label>
				<select
					id="ALARM_TRIGGER_preset"
					name="ALARM_TRIGGER_preset"
					class="form-input"
					bind:value={alarmPreset}
				>
					{#each ALARM_PRESETS as p}
						<option value={p.value}>{p.label}</option>
					{/each}
				</select>
				{#if alarmPreset === 'custom'}
					<div class="mt-2">
						<label class="form-label" for="ALARM_TRIGGER_custom">
							Custom ISO 8601 duration (e.g. <code class="text-slate-300">PT6H</code>, <code class="text-slate-300">P1D</code>)
						</label>
						<input
							id="ALARM_TRIGGER_custom"
							name="ALARM_TRIGGER_custom"
							type="text"
							class="form-input w-40"
							bind:value={alarmCustom}
							placeholder="PT6H"
						/>
					</div>
				{:else}
					<input type="hidden" name="ALARM_TRIGGER_custom" value={alarmCustom} />
				{/if}
				<p class="text-xs text-slate-500 mt-1">
					How early to show a VALARM reminder on each task.
				</p>
			</div>

			{#if successMsg('caldav')}
				<p class="text-sm text-green-400">{successMsg('caldav')}</p>
			{:else if errorMsg('caldav')}
				<p class="text-sm text-red-400">{errorMsg('caldav')}</p>
			{/if}

			<div class="flex justify-end pt-1">
				<button type="submit" class="btn-primary">Save CalDAV settings</button>
			</div>
		</form>
	</div>

	<!-- ── Outline ────────────────────────────────────────────────────── -->
	<div class="card space-y-5">
		<div>
			<h2 class="text-base font-semibold text-slate-100">Outline</h2>
			<p class="text-xs text-slate-400 mt-0.5">Wiki where AI study notes are saved</p>
		</div>

		<form method="POST" action="?/outline" use:enhance class="space-y-4">
			<div>
				<label class="form-label" for="OUTLINE_BASE_URL">Outline Base URL</label>
				<input
					id="OUTLINE_BASE_URL"
					name="OUTLINE_BASE_URL"
					type="text"
					class="form-input"
					value={data.config.OUTLINE_BASE_URL ?? ''}
					placeholder="https://outline.will.net"
				/>
			</div>

			<div>
				<label class="form-label" for="OUTLINE_API_TOKEN">API Token</label>
				<div class="relative">
					<input
						id="OUTLINE_API_TOKEN"
						name="OUTLINE_API_TOKEN"
						type={showOutlineToken ? 'text' : 'password'}
						class="form-input pr-16"
						placeholder="Leave blank to keep existing"
						autocomplete="new-password"
					/>
					<button
						type="button"
						onclick={() => (showOutlineToken = !showOutlineToken)}
						class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5 rounded"
					>
						{showOutlineToken ? 'Hide' : 'Show'}
					</button>
				</div>
				<p class="text-xs text-slate-500 mt-1">
					Outline → Settings → API tokens. Leave blank to keep the existing token.
				</p>
			</div>

			<div>
				<label class="form-label" for="OUTLINE_COLLECTION_NAME">Collection Name</label>
				<input
					id="OUTLINE_COLLECTION_NAME"
					name="OUTLINE_COLLECTION_NAME"
					type="text"
					class="form-input"
					value={data.config.OUTLINE_COLLECTION_NAME ?? 'Automatic Notes'}
				/>
				<p class="text-xs text-slate-500 mt-1">
					Top-level collection where notes are filed. Created if it doesn't exist.
				</p>
			</div>

			<div>
				<label class="form-label" for="CURRENT_WINDOW_DAYS">
					Current Window Days
				</label>
				<input
					id="CURRENT_WINDOW_DAYS"
					name="CURRENT_WINDOW_DAYS"
					type="number"
					min="1"
					max="60"
					class="form-input w-32"
					value={data.config.CURRENT_WINDOW_DAYS ?? '14'}
				/>
				<p class="text-xs text-slate-500 mt-1">
					Assignments due within this many days appear in the "Current" bucket.
				</p>
			</div>

			{#if successMsg('outline')}
				<p class="text-sm text-green-400">{successMsg('outline')}</p>
			{:else if errorMsg('outline')}
				<p class="text-sm text-red-400">{errorMsg('outline')}</p>
			{/if}

			<div class="flex justify-end pt-1">
				<button type="submit" class="btn-primary">Save Outline settings</button>
			</div>
		</form>
	</div>

	<!-- ── AI / LLM ───────────────────────────────────────────────────── -->
	<div class="card space-y-5">
		<div>
			<h2 class="text-base font-semibold text-slate-100">AI / LLM</h2>
			<p class="text-xs text-slate-400 mt-0.5">Language model used to generate study notes</p>
		</div>

		<form method="POST" action="?/ai" use:enhance={handleAiSubmit} class="space-y-4">
			<div>
				<label class="form-label" for="CHAT_API_BASE_URL">API Base URL</label>
				<input
					id="CHAT_API_BASE_URL"
					name="CHAT_API_BASE_URL"
					type="text"
					class="form-input"
					value={data.config.CHAT_API_BASE_URL ?? ''}
					placeholder="https://chat.cs.odu.edu/api/v1"
				/>
				<p class="text-xs text-slate-500 mt-1">OpenAI-compatible chat completions endpoint.</p>
			</div>

			<div>
				<label class="form-label" for="CHAT_API_KEY">API Key</label>
				<div class="relative">
					<input
						id="CHAT_API_KEY"
						name="CHAT_API_KEY"
						type={showChatKey ? 'text' : 'password'}
						class="form-input pr-16"
						placeholder="Leave blank to keep existing"
						autocomplete="new-password"
					/>
					<button
						type="button"
						onclick={() => (showChatKey = !showChatKey)}
						class="absolute right-2 top-1/2 -translate-y-1/2 text-xs text-slate-400 hover:text-slate-200 px-1 py-0.5 rounded"
					>
						{showChatKey ? 'Hide' : 'Show'}
					</button>
				</div>
			</div>

			<div>
				<button
					type="submit"
					formaction="?/aiListModels"
					class="btn-secondary text-sm"
					disabled={fetchingModels}
				>
					{fetchingModels ? 'Fetching models…' : 'Fetch available models'}
				</button>
				<p class="text-xs text-slate-500 mt-1">
					Queries <code class="text-slate-400">/models</code> on the API Base URL above using the
					API Key above (or the saved key, if left blank) to populate the dropdowns below.
				</p>
				{#if modelsError}
					<p class="text-sm text-red-400 mt-1">{modelsError}</p>
				{/if}
			</div>

			<div class="grid grid-cols-2 gap-4">
				<div>
					<label class="form-label" for="CHAT_MODEL_TEXT_select">Text Model</label>
					<select
						id="CHAT_MODEL_TEXT_select"
						class="form-input"
						bind:value={textModelSelect}
					>
						{#each models as m}
							<option value={m}>{m}</option>
						{/each}
						<option value="custom">Custom…</option>
					</select>
					{#if textModelSelect === 'custom'}
						<input
							name="CHAT_MODEL_TEXT"
							type="text"
							class="form-input mt-2"
							bind:value={textModelCustom}
							placeholder="gpt-oss-120b"
						/>
					{:else}
						<input type="hidden" name="CHAT_MODEL_TEXT" value={textModelSelect} />
					{/if}
					<p class="text-xs text-slate-500 mt-1">For text-based assignments.</p>
				</div>
				<div>
					<label class="form-label" for="CHAT_MODEL_VISION_select">Vision Model</label>
					<select
						id="CHAT_MODEL_VISION_select"
						class="form-input"
						bind:value={visionModelSelect}
					>
						{#each models as m}
							<option value={m}>{m}</option>
						{/each}
						<option value="custom">Custom…</option>
					</select>
					{#if visionModelSelect === 'custom'}
						<input
							name="CHAT_MODEL_VISION"
							type="text"
							class="form-input mt-2"
							bind:value={visionModelCustom}
							placeholder="gemma-4-31b"
						/>
					{:else}
						<input type="hidden" name="CHAT_MODEL_VISION" value={visionModelSelect} />
					{/if}
					<p class="text-xs text-slate-500 mt-1">For PDF / image attachments.</p>
				</div>
			</div>

			<!-- Prompt Templates -->
			<div class="space-y-3">
				<div>
					<h3 class="text-sm font-medium text-slate-300">Prompt Templates</h3>
					<p class="text-xs text-slate-500 mt-0.5">
						Customize the system prompts sent to the LLM. Variables in <code class="text-slate-400">{'{curly braces}'}</code>
						are filled in by notes.py at runtime. Leave a field empty to use the built-in default.
					</p>
				</div>

				<!-- Prompt tab switcher -->
				<div class="flex gap-1 rounded-lg bg-slate-900 border border-slate-600 p-1 w-fit">
					{#each [
						{ id: 'assignment', label: 'Assignment' },
						{ id: 'presentation', label: 'Slides / Files' },
						{ id: 'text_notes', label: 'Text / Video' }
					] as tab}
						<button
							type="button"
							onclick={() => (promptTab = tab.id as typeof promptTab)}
							class="rounded px-3 py-1 text-xs font-medium transition-colors
							       {promptTab === tab.id
							         ? 'bg-slate-700 text-slate-100'
							         : 'text-slate-400 hover:text-slate-200'}"
						>
							{tab.label}
						</button>
					{/each}
				</div>

				<!-- All three prompt panels always in DOM (hidden via CSS so values submit with the form).
				     Clearing a textarea back to empty resets it to the built-in default on save. -->

				<!-- Assignment prompt -->
				<div class="{promptTab !== 'assignment' ? 'hidden' : ''}">
					<label class="form-label" for="CHAT_PROMPT_ASSIGNMENT">
						Assignment Notes Prompt
					</label>
					<textarea
						id="CHAT_PROMPT_ASSIGNMENT"
						name="CHAT_PROMPT_ASSIGNMENT"
						rows="18"
						class="form-input font-mono text-xs leading-relaxed resize-y"
					>{data.config.CHAT_PROMPT_ASSIGNMENT || DEFAULT_PROMPT_ASSIGNMENT}</textarea>
					<div class="flex items-center justify-between mt-1">
						<p class="text-xs text-slate-500">
							Variables: <code class="text-slate-400">{'{course}'}</code>,
							<code class="text-slate-400">{'{name}'}</code>,
							<code class="text-slate-400">{'{due}'}</code>,
							<code class="text-slate-400">{'{points}'}</code>,
							<code class="text-slate-400">{'{submission_types}'}</code>,
							<code class="text-slate-400">{'{rubric_text}'}</code>,
							<code class="text-slate-400">{'{description}'}</code>,
							<code class="text-slate-400">{'{attachment_text}'}</code>,
							<code class="text-slate-400">{'{thin_content_note}'}</code>
						</p>
						{#if data.config.CHAT_PROMPT_ASSIGNMENT}
							<span class="text-xs text-indigo-400 flex-shrink-0 ml-4">custom</span>
						{:else}
							<span class="text-xs text-slate-500 flex-shrink-0 ml-4">using default</span>
						{/if}
					</div>
				</div>

				<!-- Presentation prompt -->
				<div class="{promptTab !== 'presentation' ? 'hidden' : ''}">
					<label class="form-label" for="CHAT_PROMPT_PRESENTATION">
						Slides / Files Notes Prompt
					</label>
					<textarea
						id="CHAT_PROMPT_PRESENTATION"
						name="CHAT_PROMPT_PRESENTATION"
						rows="16"
						class="form-input font-mono text-xs leading-relaxed resize-y"
					>{data.config.CHAT_PROMPT_PRESENTATION || DEFAULT_PROMPT_PRESENTATION}</textarea>
					<div class="flex items-center justify-between mt-1">
						<p class="text-xs text-slate-500">
							Variables: <code class="text-slate-400">{'{course}'}</code>,
							<code class="text-slate-400">{'{name}'}</code>,
							<code class="text-slate-400">{'{content}'}</code>
						</p>
						{#if data.config.CHAT_PROMPT_PRESENTATION}
							<span class="text-xs text-indigo-400 flex-shrink-0 ml-4">custom</span>
						{:else}
							<span class="text-xs text-slate-500 flex-shrink-0 ml-4">using default</span>
						{/if}
					</div>
				</div>

				<!-- Text notes prompt -->
				<div class="{promptTab !== 'text_notes' ? 'hidden' : ''}">
					<label class="form-label" for="CHAT_PROMPT_TEXT_NOTES">
						Text / Video Notes Prompt
					</label>
					<textarea
						id="CHAT_PROMPT_TEXT_NOTES"
						name="CHAT_PROMPT_TEXT_NOTES"
						rows="16"
						class="form-input font-mono text-xs leading-relaxed resize-y"
					>{data.config.CHAT_PROMPT_TEXT_NOTES || DEFAULT_PROMPT_TEXT_NOTES}</textarea>
					<div class="flex items-center justify-between mt-1">
						<p class="text-xs text-slate-500">
							Variables: <code class="text-slate-400">{'{course}'}</code>,
							<code class="text-slate-400">{'{title}'}</code>,
							<code class="text-slate-400">{'{source_label}'}</code>,
							<code class="text-slate-400">{'{content}'}</code>
						</p>
						{#if data.config.CHAT_PROMPT_TEXT_NOTES}
							<span class="text-xs text-indigo-400 flex-shrink-0 ml-4">custom</span>
						{:else}
							<span class="text-xs text-slate-500 flex-shrink-0 ml-4">using default</span>
						{/if}
					</div>
				</div>

				<p class="text-xs text-slate-500 bg-slate-700/40 rounded p-2 border border-slate-600">
					<strong class="text-slate-400">Note:</strong> notes.py must be updated to read
					<code class="text-slate-300">CHAT_PROMPT_*</code> environment variables for custom
					prompts to take effect. The stored values are passed via the canvas-config ConfigMap.
				</p>
			</div>

			{#if successMsg('ai')}
				<p class="text-sm text-green-400">{successMsg('ai')}</p>
			{:else if errorMsg('ai')}
				<p class="text-sm text-red-400">{errorMsg('ai')}</p>
			{/if}

			<div class="flex justify-end pt-1">
				<button type="submit" class="btn-primary">Save AI settings</button>
			</div>
		</form>
	</div>

	<!-- ── Schedule ───────────────────────────────────────────────────── -->
	<div class="card space-y-5">
		<div>
			<h2 class="text-base font-semibold text-slate-100">Schedule</h2>
			<p class="text-xs text-slate-400 mt-0.5">
				Run intervals stored in the ConfigMap — update CronJob schedules separately in Git.
			</p>
		</div>

		<form method="POST" action="?/schedule" use:enhance class="space-y-4">
			<div class="grid grid-cols-2 gap-4">
				<div>
					<label class="form-label" for="SYNC_INTERVAL_MINUTES">
						Sync Interval (min)
					</label>
					<input
						id="SYNC_INTERVAL_MINUTES"
						name="SYNC_INTERVAL_MINUTES"
						type="number"
						min="1"
						max="1440"
						class="form-input"
						value={data.config.SYNC_INTERVAL_MINUTES ?? '15'}
					/>
				</div>
				<div>
					<label class="form-label" for="NOTES_INTERVAL_MINUTES">
						Notes Interval (min)
					</label>
					<input
						id="NOTES_INTERVAL_MINUTES"
						name="NOTES_INTERVAL_MINUTES"
						type="number"
						min="1"
						max="1440"
						class="form-input"
						value={data.config.NOTES_INTERVAL_MINUTES ?? '60'}
					/>
				</div>
			</div>

			<div>
				<label class="form-label" for="TZ">Timezone</label>
				<input
					id="TZ"
					name="TZ"
					type="text"
					class="form-input"
					value={data.config.TZ ?? 'America/New_York'}
					placeholder="America/New_York"
				/>
				<p class="text-xs text-slate-500 mt-1">
					IANA timezone name, e.g. <code class="text-slate-300">America/New_York</code>.
					Used for displaying assignment due times.
				</p>
			</div>

			{#if successMsg('schedule')}
				<p class="text-sm text-green-400">{successMsg('schedule')}</p>
			{:else if errorMsg('schedule')}
				<p class="text-sm text-red-400">{errorMsg('schedule')}</p>
			{/if}

			<div class="flex justify-end pt-1">
				<button type="submit" class="btn-primary">Save schedule settings</button>
			</div>
		</form>
	</div>
</div>
