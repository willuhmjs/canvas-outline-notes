/**
 * Backend abstraction layer. Auto-detects Kubernetes vs Docker mode.
 *
 * k8s mode:  reads the in-cluster ServiceAccount token to call the k8s API.
 *            All secrets/configmaps are stored in the cluster.
 *
 * Docker mode: reads/writes /data/settings.json. Scripts are invoked as
 *              child processes if the paths exist.
 *
 * NODE_EXTRA_CA_CERTS is set in the Dockerfile to the k8s CA cert so
 * Node's native fetch trusts the k8s API server.
 */

import fs from 'fs';
import https from 'https';
import { execFile } from 'child_process';
import { promisify } from 'util';
import { randomUUID } from 'crypto';
import type {
	AppConfig,
	SyncSecrets,
	OutlineSecrets,
	K8sJob,
	DockerSettings,
	DockerJobRecord,
	HealthCheck
} from './types.js';

const execFileAsync = promisify(execFile);

// ── Constants ────────────────────────────────────────────────────────────────

const SA_DIR = '/var/run/secrets/kubernetes.io/serviceaccount';
const DOCKER_SETTINGS_FILE = process.env.DOCKER_SETTINGS_FILE ?? '/data/settings.json';

// UID of the credential alarm VTODO written by notes.py
const CREDENTIAL_ALARM_UID = 'canvas-outline-notes-credential-alarm';

// ── Mode detection ───────────────────────────────────────────────────────────

export function isKubernetes(): boolean {
	return (
		fs.existsSync(`${SA_DIR}/token`) &&
		!!process.env.KUBERNETES_SERVICE_HOST
	);
}

export function getNamespace(): string {
	try {
		return fs.readFileSync(`${SA_DIR}/namespace`, 'utf-8').trim();
	} catch {
		return process.env.K8S_NAMESPACE ?? 'dav';
	}
}

// ── k8s API client ───────────────────────────────────────────────────────────

function getSAToken(): string {
	return fs.readFileSync(`${SA_DIR}/token`, 'utf-8').trim();
}

/**
 * Make an authenticated request to the in-cluster k8s API.
 * Returns parsed JSON, or raw string for log endpoints.
 */
async function k8sRequest<T>(
	method: string,
	path: string,
	body?: unknown,
	contentType = 'application/json'
): Promise<T> {
	const token = getSAToken();
	const host = process.env.KUBERNETES_SERVICE_HOST!;
	const port = parseInt(process.env.KUBERNETES_SERVICE_PORT ?? '443');
	const caFile = `${SA_DIR}/ca.crt`;

	const headers: Record<string, string> = {
		Authorization: `Bearer ${token}`,
		Accept: 'application/json'
	};

	let bodyBuf: Buffer | undefined;
	if (body !== undefined) {
		bodyBuf = Buffer.from(JSON.stringify(body), 'utf-8');
		headers['Content-Type'] = contentType;
		headers['Content-Length'] = bodyBuf.length.toString();
	}

	return new Promise<T>((resolve, reject) => {
		const options: https.RequestOptions = {
			hostname: host,
			port,
			path,
			method,
			headers,
			// The CA cert is trusted via NODE_EXTRA_CA_CERTS env var set in Dockerfile.
			// As a safety net for local dev, also load it explicitly.
			ca: fs.existsSync(caFile) ? fs.readFileSync(caFile) : undefined
		};

		const req = https.request(options, (res) => {
			const chunks: Buffer[] = [];
			res.on('data', (chunk: Buffer) => chunks.push(chunk));
			res.on('end', () => {
				const text = Buffer.concat(chunks).toString('utf-8');
				const status = res.statusCode ?? 0;

				if (status >= 400) {
					reject(new Error(`k8s ${method} ${path} → ${status}: ${text.slice(0, 800)}`));
					return;
				}

				// Log endpoints return plain text
				const ct = res.headers['content-type'] ?? '';
				if (!ct.includes('json')) {
					resolve(text as unknown as T);
					return;
				}

				try {
					resolve(JSON.parse(text) as T);
				} catch {
					resolve(text as unknown as T);
				}
			});
		});

		req.on('error', reject);
		if (bodyBuf) req.write(bodyBuf);
		req.end();
	});
}

// ── Secrets ──────────────────────────────────────────────────────────────────

export async function getSecretData(secretName: string): Promise<Record<string, string>> {
	const ns = getNamespace();
	try {
		const secret = await k8sRequest<{ data?: Record<string, string> }>(
			'GET',
			`/api/v1/namespaces/${ns}/secrets/${secretName}`
		);
		const data = secret.data ?? {};
		return Object.fromEntries(
			Object.entries(data).map(([k, v]) => [k, Buffer.from(v, 'base64').toString('utf-8')])
		);
	} catch (e) {
		console.error(`getSecretData(${secretName}):`, e);
		return {};
	}
}

export async function patchSecret(
	secretName: string,
	updates: Record<string, string>
): Promise<void> {
	const ns = getNamespace();
	// stringData lets k8s handle the base64 encoding
	await k8sRequest(
		'PATCH',
		`/api/v1/namespaces/${ns}/secrets/${secretName}`,
		{ stringData: updates },
		'application/merge-patch+json'
	);
}

// ── ConfigMaps ───────────────────────────────────────────────────────────────

export async function getConfigMapData(cmName: string): Promise<Record<string, string>> {
	const ns = getNamespace();
	try {
		const cm = await k8sRequest<{ data?: Record<string, string> }>(
			'GET',
			`/api/v1/namespaces/${ns}/configmaps/${cmName}`
		);
		return cm.data ?? {};
	} catch (e) {
		const msg = String(e);
		if (!msg.includes('404')) {
			console.error(`getConfigMapData(${cmName}):`, e);
		}
		return {};
	}
}

export async function patchConfigMap(
	cmName: string,
	updates: Record<string, string>
): Promise<void> {
	const ns = getNamespace();
	try {
		await k8sRequest(
			'PATCH',
			`/api/v1/namespaces/${ns}/configmaps/${cmName}`,
			{ data: updates },
			'application/merge-patch+json'
		);
	} catch (e) {
		// If it doesn't exist yet, create it
		if (String(e).includes('404') || String(e).includes('not found')) {
			await k8sRequest('POST', `/api/v1/namespaces/${ns}/configmaps`, {
				apiVersion: 'v1',
				kind: 'ConfigMap',
				metadata: { name: cmName, namespace: ns },
				data: updates
			});
		} else {
			throw e;
		}
	}
}

// ── Jobs ─────────────────────────────────────────────────────────────────────

interface K8sCronJobBody {
	spec: { jobTemplate: { spec: unknown } };
}

interface K8sJobListBody {
	items: Array<{
		metadata: {
			name: string;
			namespace: string;
			creationTimestamp: string;
			labels?: Record<string, string>;
			annotations?: Record<string, string>;
		};
		status: {
			active?: number;
			succeeded?: number;
			failed?: number;
			startTime?: string;
			completionTime?: string;
		};
	}>;
}

interface K8sPodListBody {
	items: Array<{
		metadata: { name: string };
		status: { phase?: string };
	}>;
}

/** Create a one-off Job from a CronJob template. */
export async function createJobFromCronJob(
	cronJobName: string,
	jobName: string
): Promise<void> {
	const ns = getNamespace();
	const cron = await k8sRequest<K8sCronJobBody>(
		'GET',
		`/apis/batch/v1/namespaces/${ns}/cronjobs/${cronJobName}`
	);

	await k8sRequest('POST', `/apis/batch/v1/namespaces/${ns}/jobs`, {
		apiVersion: 'batch/v1',
		kind: 'Job',
		metadata: {
			name: jobName,
			namespace: ns,
			labels: {
				'app.kubernetes.io/managed-by': 'canvas-management',
				'canvas-management/trigger': 'manual',
				'canvas-management/cronjob': cronJobName
			},
			annotations: {
				'canvas-management/triggered-at': new Date().toISOString()
			}
		},
		spec: {
			...cron.spec.jobTemplate.spec,
			ttlSecondsAfterFinished: 3600
		}
	});
}

/** List recently triggered manual jobs, newest first. */
export async function listManualJobs(): Promise<K8sJob[]> {
	const ns = getNamespace();
	const selector = encodeURIComponent('canvas-management/trigger=manual');
	try {
		const body = await k8sRequest<K8sJobListBody>(
			'GET',
			`/apis/batch/v1/namespaces/${ns}/jobs?labelSelector=${selector}&limit=20`
		);

		return body.items
			.map((j) => {
				const cronName = j.metadata.labels?.['canvas-management/cronjob'] ?? '';
				const type: K8sJob['type'] =
					cronName === 'canvas-sync'
						? 'sync'
						: cronName === 'canvas-notes'
							? 'notes'
							: 'unknown';

				let status: K8sJob['status'] = 'unknown';
				if ((j.status.active ?? 0) > 0) status = 'running';
				else if ((j.status.succeeded ?? 0) > 0) status = 'succeeded';
				else if ((j.status.failed ?? 0) > 0) status = 'failed';

				return {
					name: j.metadata.name,
					namespace: j.metadata.namespace,
					type,
					status,
					startTime: j.status.startTime ?? j.metadata.creationTimestamp,
					completionTime: j.status.completionTime ?? null
				};
			})
			.sort((a, b) => (b.startTime ?? '').localeCompare(a.startTime ?? ''))
			.slice(0, 10);
	} catch (e) {
		console.error('listManualJobs:', e);
		return [];
	}
}

async function getPodNameForJob(jobName: string): Promise<string | null> {
	const ns = getNamespace();
	try {
		const pods = await k8sRequest<K8sPodListBody>(
			'GET',
			`/api/v1/namespaces/${ns}/pods?labelSelector=${encodeURIComponent(`job-name=${jobName}`)}`
		);
		if (!pods.items.length) return null;
		const done = pods.items.find(
			(p) => p.status.phase === 'Succeeded' || p.status.phase === 'Failed'
		);
		return (done ?? pods.items[0]).metadata.name;
	} catch {
		return null;
	}
}

export async function getJobLogs(jobName: string, tailLines = 150): Promise<string> {
	const ns = getNamespace();
	const pod = await getPodNameForJob(jobName);
	if (!pod) return '(no pod found for this job)';
	try {
		const logs = await k8sRequest<string>(
			'GET',
			`/api/v1/namespaces/${ns}/pods/${pod}/log?tailLines=${tailLines}&timestamps=true`
		);
		return typeof logs === 'string' ? logs : JSON.stringify(logs);
	} catch (e) {
		return `(error fetching logs: ${e})`;
	}
}

/** Get recent completed jobs of a given type with their logs. */
export async function getRecentJobLogs(
	type: 'sync' | 'notes',
	count = 3
): Promise<Array<K8sJob & { logs: string }>> {
	const all = await listManualJobs();
	const filtered = all
		.filter((j) => j.type === type && j.status !== 'running')
		.slice(0, count);

	return Promise.all(
		filtered.map(async (j) => ({ ...j, logs: await getJobLogs(j.name) }))
	);
}

// ── Docker mode ──────────────────────────────────────────────────────────────

const DEFAULT_DOCKER_SETTINGS: DockerSettings = {
	secrets: {
		'canvas-sync-secrets': {},
		'canvas-outline-secrets': {}
	},
	config: {},
	jobHistory: []
};

export function readDockerSettings(): DockerSettings {
	try {
		if (fs.existsSync(DOCKER_SETTINGS_FILE)) {
			const raw = JSON.parse(fs.readFileSync(DOCKER_SETTINGS_FILE, 'utf-8')) as DockerSettings;
			// Merge defaults so new keys are always present
			return {
				secrets: {
					'canvas-sync-secrets': {
						...raw.secrets?.['canvas-sync-secrets']
					},
					'canvas-outline-secrets': {
						...raw.secrets?.['canvas-outline-secrets']
					}
				},
				config: { ...raw.config },
				jobHistory: raw.jobHistory ?? []
			};
		}
	} catch (e) {
		console.error('readDockerSettings:', e);
	}
	return structuredClone(DEFAULT_DOCKER_SETTINGS);
}

export function writeDockerSettings(settings: DockerSettings): void {
	const dir = DOCKER_SETTINGS_FILE.substring(0, DOCKER_SETTINGS_FILE.lastIndexOf('/'));
	if (dir) fs.mkdirSync(dir, { recursive: true });
	fs.writeFileSync(DOCKER_SETTINGS_FILE, JSON.stringify(settings, null, 2), 'utf-8');
}

function buildDockerEnv(settings: DockerSettings): NodeJS.ProcessEnv {
	return {
		...process.env,
		...(settings.secrets['canvas-sync-secrets'] as Record<string, string>),
		...(settings.secrets['canvas-outline-secrets'] as Record<string, string>),
		...(settings.config as Record<string, string>)
	};
}

/** Launch a script as a subprocess, persist a job record, resolve immediately. */
export function launchDockerScript(
	scriptPath: string,
	type: 'sync' | 'notes'
): DockerJobRecord {
	const id = randomUUID();
	const record: DockerJobRecord = {
		id,
		name: `${type}-manual-${Date.now()}`,
		type,
		startTime: new Date().toISOString(),
		endTime: null,
		status: 'running',
		output: '',
		exitCode: null
	};

	const settings = readDockerSettings();
	settings.jobHistory.unshift(record);
	settings.jobHistory = settings.jobHistory.slice(0, 20);
	writeDockerSettings(settings);

	// Fire-and-forget; update the record when done
	execFileAsync('python3', [scriptPath], {
		timeout: 300_000,
		env: buildDockerEnv(settings)
	})
		.then(({ stdout, stderr }) => {
			updateJobRecord(id, {
				endTime: new Date().toISOString(),
				status: 'succeeded',
				output: `${stdout}\n${stderr}`.trim().slice(0, 50_000),
				exitCode: 0
			});
		})
		.catch((err: { stdout?: string; stderr?: string; code?: number }) => {
			updateJobRecord(id, {
				endTime: new Date().toISOString(),
				status: 'failed',
				output: `${err.stdout ?? ''}\n${err.stderr ?? ''}`.trim().slice(0, 50_000),
				exitCode: err.code ?? -1
			});
		});

	return record;
}

function updateJobRecord(id: string, updates: Partial<DockerJobRecord>): void {
	try {
		const settings = readDockerSettings();
		const idx = settings.jobHistory.findIndex((j) => j.id === id);
		if (idx !== -1) {
			settings.jobHistory[idx] = { ...settings.jobHistory[idx], ...updates };
			writeDockerSettings(settings);
		}
	} catch (e) {
		console.error('updateJobRecord:', e);
	}
}

// ── Aggregated settings access ────────────────────────────────────────────────

// Defaults matching sync.py / notes.py so the settings UI is never blank.
// These are merged under whatever's in the ConfigMap / settings.json.
const CONFIG_DEFAULTS: Record<string, string> = {
	CANVAS_BASE_URL: 'https://canvas.odu.edu',
	DAV_BASE_URL: 'http://davis:9000',
	DAV_CALENDAR_DISPLAYNAME: 'Academics',
	OUTLINE_BASE_URL: '',
	OUTLINE_COLLECTION_NAME: 'Automatic Notes',
	CHAT_API_BASE_URL: 'https://chat.cs.odu.edu/api/v1',
	CHAT_MODEL_TEXT: 'gpt-oss-120b',
	CHAT_MODEL_VISION: 'gemma-4-31b',
	TZ: 'America/New_York',
	SYNC_INTERVAL_MINUTES: '15',
	NOTES_INTERVAL_MINUTES: '60',
	ALARM_TRIGGER: 'PT6H',
	CURRENT_WINDOW_DAYS: '14',
	COMPLETION_LOOKBACK_DAYS: '30',
	// Prompts: empty string here means the UI will load defaults from prompts.ts client-side
	CHAT_PROMPT_ASSIGNMENT: '',
	CHAT_PROMPT_PRESENTATION: '',
	CHAT_PROMPT_TEXT_NOTES: ''
};

export async function getAllSettings(): Promise<{
	syncSecrets: Record<string, string>;
	outlineSecrets: Record<string, string>;
	config: Record<string, string>;
}> {
	if (isKubernetes()) {
		const [syncSecrets, outlineSecrets, rawConfig] = await Promise.all([
			getSecretData('canvas-sync-secrets'),
			getSecretData('canvas-outline-secrets'),
			getConfigMapData('canvas-config')
		]);
		const config = { ...CONFIG_DEFAULTS, ...rawConfig };
		return { syncSecrets, outlineSecrets, config };
	}

	const s = readDockerSettings();
	const rawConfig = (s.config ?? {}) as Record<string, string>;
	return {
		syncSecrets: (s.secrets['canvas-sync-secrets'] ?? {}) as Record<string, string>,
		outlineSecrets: (s.secrets['canvas-outline-secrets'] ?? {}) as Record<string, string>,
		config: { ...CONFIG_DEFAULTS, ...rawConfig }
	};
}

export async function saveSettings(
	syncSecretUpdates: Record<string, string>,
	outlineSecretUpdates: Record<string, string>,
	configUpdates: Record<string, string>
): Promise<void> {
	if (isKubernetes()) {
		const tasks: Promise<void>[] = [];
		if (Object.keys(syncSecretUpdates).length > 0)
			tasks.push(patchSecret('canvas-sync-secrets', syncSecretUpdates));
		if (Object.keys(outlineSecretUpdates).length > 0)
			tasks.push(patchSecret('canvas-outline-secrets', outlineSecretUpdates));
		if (Object.keys(configUpdates).length > 0)
			tasks.push(patchConfigMap('canvas-config', configUpdates));
		await Promise.all(tasks);
	} else {
		const s = readDockerSettings();
		Object.assign(s.secrets['canvas-sync-secrets'], syncSecretUpdates);
		Object.assign(s.secrets['canvas-outline-secrets'], outlineSecretUpdates);
		Object.assign(s.config, configUpdates);
		writeDockerSettings(s);
	}
}

// ── Health checks ─────────────────────────────────────────────────────────────

async function timedFetch(
	fn: () => Promise<Response>
): Promise<{ ok: boolean; status: number; latencyMs: number; text: string }> {
	const t0 = Date.now();
	try {
		const resp = await fn();
		const text = await resp.text().catch(() => '');
		return { ok: resp.ok, status: resp.status, latencyMs: Date.now() - t0, text };
	} catch (e) {
		return { ok: false, status: 0, latencyMs: Date.now() - t0, text: String(e) };
	}
}

export async function checkCanvasHealth(
	baseUrl: string,
	apiToken: string
): Promise<HealthCheck> {
	if (!baseUrl || !apiToken) {
		return { name: 'Canvas', status: 'unknown', message: 'Not configured' };
	}
	const { ok, status, latencyMs, text } = await timedFetch(() =>
		fetch(`${baseUrl}/api/v1/courses?per_page=1&enrollment_state=active`, {
			headers: { Authorization: `Bearer ${apiToken}` },
			signal: AbortSignal.timeout(6000)
		})
	);
	if (ok) return { name: 'Canvas', status: 'healthy', message: `Connected (${status})`, latencyMs };
	if (status === 401) return { name: 'Canvas', status: 'error', message: 'Invalid API token (401)', latencyMs };
	if (status === 0) return { name: 'Canvas', status: 'error', message: `Unreachable: ${text.slice(0, 120)}` };
	return { name: 'Canvas', status: 'error', message: `HTTP ${status}`, latencyMs };
}

export async function checkCalDAVHealth(
	baseUrl: string,
	username: string,
	password: string
): Promise<HealthCheck> {
	if (!baseUrl || !username || !password) {
		return { name: 'CalDAV', status: 'unknown', message: 'Not configured' };
	}
	const auth = Buffer.from(`${username}:${password}`).toString('base64');
	const { ok, status, latencyMs, text } = await timedFetch(() =>
		fetch(`${baseUrl}/`, {
			method: 'PROPFIND',
			headers: {
				Authorization: `Basic ${auth}`,
				Depth: '0',
				'Content-Type': 'application/xml; charset=utf-8'
			},
			signal: AbortSignal.timeout(6000)
		})
	);
	// 207 Multi-Status is the success response for PROPFIND
	if (ok || status === 207) {
		return { name: 'CalDAV', status: 'healthy', message: `Connected (${status})`, latencyMs };
	}
	if (status === 401) return { name: 'CalDAV', status: 'error', message: 'Invalid credentials (401)', latencyMs };
	if (status === 0) return { name: 'CalDAV', status: 'error', message: `Unreachable: ${text.slice(0, 120)}` };
	return { name: 'CalDAV', status: 'error', message: `HTTP ${status}`, latencyMs };
}

export async function checkOutlineHealth(
	baseUrl: string,
	apiToken: string
): Promise<HealthCheck> {
	if (!baseUrl || !apiToken) {
		return { name: 'Outline', status: 'unknown', message: 'Not configured' };
	}
	const { ok, status, latencyMs, text } = await timedFetch(() =>
		fetch(`${baseUrl}/api/collections.list`, {
			method: 'POST',
			headers: {
				Authorization: `Bearer ${apiToken}`,
				'Content-Type': 'application/json'
			},
			body: JSON.stringify({}),
			signal: AbortSignal.timeout(6000)
		})
	);
	if (ok) return { name: 'Outline', status: 'healthy', message: `Connected (${status})`, latencyMs };
	if (status === 401) return { name: 'Outline', status: 'error', message: 'Invalid API token (401)', latencyMs };
	if (status === 0) return { name: 'Outline', status: 'error', message: `Unreachable: ${text.slice(0, 120)}` };
	return { name: 'Outline', status: 'error', message: `HTTP ${status}`, latencyMs };
}

/**
 * Query an OpenAI-compatible `/models` endpoint so the UI can offer a
 * dropdown instead of requiring the exact model id to be typed by hand.
 */
export async function listChatModels(
	baseUrl: string,
	apiKey: string
): Promise<{ models: string[] } | { error: string }> {
	if (!baseUrl || !apiKey) {
		return { error: 'API Base URL and API Key are required' };
	}
	const { ok, status, text } = await timedFetch(() =>
		fetch(`${baseUrl.replace(/\/+$/, '')}/models`, {
			headers: { Authorization: `Bearer ${apiKey}` },
			signal: AbortSignal.timeout(8000)
		})
	);
	if (!ok) {
		if (status === 401) return { error: 'Invalid API key (401)' };
		if (status === 0) return { error: `Unreachable: ${text.slice(0, 120)}` };
		return { error: `HTTP ${status}` };
	}
	try {
		const parsed = JSON.parse(text);
		const list = Array.isArray(parsed?.data) ? parsed.data : Array.isArray(parsed) ? parsed : [];
		const models = list
			.map((m: unknown) => (typeof m === 'string' ? m : (m as { id?: string })?.id))
			.filter((id: unknown): id is string => typeof id === 'string')
			.sort();
		return { models };
	} catch {
		return { error: 'Invalid response from models endpoint' };
	}
}

// ── CalDAV alarm management ───────────────────────────────────────────────────

/**
 * Discover the Academics calendar href via PROPFIND.
 * Davis uses /dav/{username}/{calendarname}/ as its URL scheme.
 */
async function discoverCalendarHref(
	baseUrl: string,
	username: string,
	password: string,
	calendarName: string
): Promise<string> {
	// Try direct URL pattern first (Davis convention)
	const direct = `${baseUrl}/dav/${encodeURIComponent(username)}/${encodeURIComponent(calendarName)}/`;
	const auth = Buffer.from(`${username}:${password}`).toString('base64');
	const resp = await fetch(direct, {
		method: 'PROPFIND',
		headers: {
			Authorization: `Basic ${auth}`,
			Depth: '0',
			'Content-Type': 'application/xml; charset=utf-8'
		},
		signal: AbortSignal.timeout(8000)
	});
	if (resp.ok || resp.status === 207) return direct;

	// Fallback: also try without encoding
	const plain = `${baseUrl}/dav/${username}/${calendarName}/`;
	const resp2 = await fetch(plain, {
		method: 'PROPFIND',
		headers: {
			Authorization: `Basic ${auth}`,
			Depth: '0',
			'Content-Type': 'application/xml; charset=utf-8'
		},
		signal: AbortSignal.timeout(8000)
	});
	if (resp2.ok || resp2.status === 207) return plain;

	// Last resort: return the direct URL and hope for the best
	return direct;
}

/**
 * Delete the credential alarm VTODO from the CalDAV calendar.
 * This is the "canvas-outline-notes-credential-alarm" VTODO written by notes.py
 * when a 401/403 is encountered.
 */
export async function clearCredentialAlarm(
	baseUrl: string,
	username: string,
	password: string,
	calendarName: string
): Promise<void> {
	const calHref = await discoverCalendarHref(baseUrl, username, password, calendarName);
	const objectUrl = `${calHref.replace(/\/$/, '')}/${CREDENTIAL_ALARM_UID}.ics`;
	const auth = Buffer.from(`${username}:${password}`).toString('base64');

	const resp = await fetch(objectUrl, {
		method: 'DELETE',
		headers: { Authorization: `Basic ${auth}` },
		signal: AbortSignal.timeout(8000)
	});

	if (!resp.ok && resp.status !== 404) {
		throw new Error(`DELETE ${objectUrl} → ${resp.status}: ${await resp.text()}`);
	}
}

// ── Unified trigger ────────────────────────────────────────────────────────────

export type TriggerResult = { mode: 'kubernetes'; jobName: string } | { mode: 'docker'; record: DockerJobRecord };

export async function triggerSync(): Promise<TriggerResult> {
	if (isKubernetes()) {
		const jobName = `canvas-sync-manual-${Date.now()}`;
		await createJobFromCronJob('canvas-sync', jobName);
		return { mode: 'kubernetes', jobName };
	}
	const record = launchDockerScript('/app/sync.py', 'sync');
	return { mode: 'docker', record };
}

export async function triggerNotes(): Promise<TriggerResult> {
	if (isKubernetes()) {
		const jobName = `canvas-notes-manual-${Date.now()}`;
		await createJobFromCronJob('canvas-notes', jobName);
		return { mode: 'kubernetes', jobName };
	}
	const record = launchDockerScript('/app/notes.py', 'notes');
	return { mode: 'docker', record };
}
