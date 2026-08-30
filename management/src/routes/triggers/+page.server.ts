import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import {
	isKubernetes,
	getAllSettings,
	listManualJobs,
	triggerSync,
	triggerNotes,
	clearCredentialAlarm,
	readDockerSettings
} from '$lib/k8s';
import { readRegenerateProgress, writeRegenerateProgress } from '$lib/regenerate';

// A run is considered stalled if its progress hasn't been updated in this
// long -- guards against a hung fetch (e.g. AbortSignal.timeout not firing
// for some in-flight request) leaving the "in progress" state stuck forever
// with no way to retry.
const STALE_MS = 60_000;

function isStale(p: { status: string; updatedAt?: string }): boolean {
	// No liveness timestamp at all (e.g. a run started before this field
	// existed) is itself a sign of a stuck run -- treat it as stale rather
	// than getting stuck forever waiting for an update that will never come.
	if (!p.updatedAt) return true;
	return Date.now() - new Date(p.updatedAt).getTime() > STALE_MS;
}

// Independent of fetch's own AbortSignal -- a plain setTimeout/Promise race
// that guarantees forward progress even if the underlying request never
// settles for some undici/Node edge case.
function withTimeout<T>(promise: Promise<T>, ms: number, label: string): Promise<T> {
	return new Promise((resolve, reject) => {
		const timer = setTimeout(() => reject(new Error(`${label} timed out after ${ms}ms`)), ms);
		promise.then(
			(v) => { clearTimeout(timer); resolve(v); },
			(e) => { clearTimeout(timer); reject(e); }
		);
	});
}

async function wipeOutlineCollection(
	baseUrl: string,
	apiToken: string,
	collectionName: string,
	onProgress: (deleted: number, total: number) => void
): Promise<{ deleted: number }> {
	const headers = {
		Authorization: `Bearer ${apiToken}`,
		'Content-Type': 'application/json'
	};

	const post = async (path: string, body: object) => {
		const r = await withTimeout(
			fetch(`${baseUrl}/api/${path}`, {
				method: 'POST',
				headers,
				body: JSON.stringify(body),
				signal: AbortSignal.timeout(15_000)
			}),
			20_000,
			`Outline ${path}`
		);
		const text = await withTimeout(r.text(), 10_000, `Outline ${path} (reading response)`);
		if (!r.ok) {
			throw new Error(`Outline ${path} failed: HTTP ${r.status} — ${text.slice(0, 200)}`);
		}
		try {
			return JSON.parse(text);
		} catch {
			throw new Error(`Outline ${path} returned a non-JSON response: ${text.slice(0, 200)}`);
		}
	};

	// Find collection
	const cols = await post('collections.list', { limit: 25 });
	const col = (cols.data as { name: string; id: string }[]).find(c => c.name === collectionName);
	if (!col) return { deleted: 0 };

	// List all docs (paginated)
	const allDocs: { id: string }[] = [];
	let offset = 0;
	while (true) {
		const r = await post('documents.list', { collectionId: col.id, limit: 100, offset });
		allDocs.push(...r.data);
		if (allDocs.length >= r.pagination.total) break;
		offset += 100;
	}

	onProgress(0, allDocs.length);

	// Delete a few at a time — Outline's Postgres pool is small and deleting in
	// large parallel batches exhausts it, causing its own health check (and
	// this request) to fail with a 502 partway through.
	let deleted = 0;
	for (let i = 0; i < allDocs.length; i += 3) {
		const batch = allDocs.slice(i, i + 3);
		await Promise.all(batch.map(doc =>
			post('documents.delete', { id: doc.id }).then(() => {
				deleted++;
				onProgress(deleted, allDocs.length);
			})
		));
	}

	return { deleted };
}

/**
 * Runs in the background, outside the request/response cycle — deleting
 * ~200 documents plus queuing a notes job can take well over a minute,
 * which upstream proxies were killing with a 502 while the form action
 * waited on it. Progress is persisted to disk so the UI can poll it and
 * survive a page reload.
 */
async function runRegenerate(outlineBaseUrl: string, outlineApiToken: string, collectionName: string) {
	const startedAt = new Date().toISOString();
	let total = 0;
	let deleted = 0;
	try {
		writeRegenerateProgress({ status: 'listing', total, deleted, startedAt, updatedAt: new Date().toISOString() });

		const result = await wipeOutlineCollection(outlineBaseUrl, outlineApiToken, collectionName, (d, t) => {
			deleted = d;
			total = t;
			writeRegenerateProgress({ status: 'deleting', total, deleted, startedAt, updatedAt: new Date().toISOString() });
		});
		deleted = result.deleted;

		writeRegenerateProgress({ status: 'queuing', total, deleted, startedAt, updatedAt: new Date().toISOString() });
		const jobResult = await triggerNotes();
		const jobName = jobResult.mode === 'kubernetes' ? jobResult.jobName : jobResult.record.name;

		writeRegenerateProgress({
			status: 'done',
			total,
			deleted,
			jobName,
			startedAt,
			updatedAt: new Date().toISOString(),
			finishedAt: new Date().toISOString()
		});
	} catch (e) {
		writeRegenerateProgress({
			status: 'error',
			total,
			deleted,
			error: String(e),
			startedAt,
			updatedAt: new Date().toISOString(),
			finishedAt: new Date().toISOString()
		});
	}
}

/**
 * If the last run stalled (no progress in over a minute -- e.g. a hung
 * fetch that never resolved), restart it automatically instead of leaving
 * the UI's progress bar frozen waiting on manual intervention.
 */
async function autoHealRegenerate(): Promise<import('$lib/types').RegenerateProgress> {
	const current = readRegenerateProgress();
	const active =
		current.status === 'listing' || current.status === 'deleting' || current.status === 'queuing';
	if (!active || !isStale(current)) return current;

	const { outlineSecrets, config } = await getAllSettings();
	const outlineBaseUrl = config.OUTLINE_BASE_URL ?? '';
	const outlineApiToken = outlineSecrets.OUTLINE_API_TOKEN ?? '';
	const collectionName = config.OUTLINE_COLLECTION_NAME ?? 'Automatic Notes';
	if (!outlineBaseUrl || !outlineApiToken) return current;

	void runRegenerate(outlineBaseUrl, outlineApiToken, collectionName);
	return readRegenerateProgress();
}

export const load: PageServerLoad = async ({ depends }) => {
	depends('triggers:regenerate');

	let recentJobs: Awaited<ReturnType<typeof listManualJobs>> = [];
	let dockerHistory: import('$lib/types').DockerJobRecord[] = [];

	if (isKubernetes()) {
		recentJobs = await listManualJobs().catch(() => []);
	} else {
		const settings = readDockerSettings();
		dockerHistory = (settings.jobHistory ?? []).slice(0, 10);
	}

	return {
		recentJobs: recentJobs.slice(0, 10),
		dockerHistory,
		regenerateProgress: await autoHealRegenerate()
	};
};

export const actions: Actions = {
	sync: async () => {
		try {
			const result = await triggerSync();
			const name = result.mode === 'kubernetes' ? result.jobName : result.record.name;
			return { success: true, action: 'sync', jobName: name };
		} catch (e) {
			return fail(500, { error: String(e), action: 'sync' });
		}
	},

	notes: async () => {
		try {
			const result = await triggerNotes();
			const name = result.mode === 'kubernetes' ? result.jobName : result.record.name;
			return { success: true, action: 'notes', jobName: name };
		} catch (e) {
			return fail(500, { error: String(e), action: 'notes' });
		}
	},

	regenerate: async () => {
		const current = readRegenerateProgress();
		const currentlyActive =
			current.status === 'listing' || current.status === 'deleting' || current.status === 'queuing';
		if (currentlyActive && !isStale(current)) {
			return fail(409, { error: 'A regeneration is already in progress.', action: 'regenerate' });
		}

		const { outlineSecrets, config } = await getAllSettings();
		const outlineBaseUrl = config.OUTLINE_BASE_URL ?? '';
		const outlineApiToken = outlineSecrets.OUTLINE_API_TOKEN ?? '';
		const collectionName = config.OUTLINE_COLLECTION_NAME ?? 'Automatic Notes';

		if (!outlineBaseUrl || !outlineApiToken) {
			return fail(400, {
				error: 'Outline is not configured. Set the base URL and API token in Settings first.',
				action: 'regenerate'
			});
		}

		// Don't await — this can take well over a minute and must not block
		// the HTTP response (long-running requests were getting killed by
		// upstream proxies with a "Bad Gateway"). Progress is polled from disk.
		void runRegenerate(outlineBaseUrl, outlineApiToken, collectionName);

		return { success: true, action: 'regenerate', started: true };
	},

	clearAlarm: async () => {
		try {
			const { syncSecrets, config } = await getAllSettings();
			const davBaseUrl = config.DAV_BASE_URL ?? '';
			const davUsername = syncSecrets.DAV_USERNAME ?? '';
			const davPassword = syncSecrets.DAV_PASSWORD ?? '';
			const calendarName = config.DAV_CALENDAR_DISPLAYNAME ?? 'Academics';

			if (!davBaseUrl || !davUsername || !davPassword) {
				return fail(400, {
					error: 'CalDAV credentials are not configured. Configure them in Settings first.',
					action: 'clearAlarm'
				});
			}

			await clearCredentialAlarm(davBaseUrl, davUsername, davPassword, calendarName);
			return { success: true, action: 'clearAlarm' };
		} catch (e) {
			return fail(500, { error: String(e), action: 'clearAlarm' });
		}
	}
};
