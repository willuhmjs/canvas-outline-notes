import type { PageServerLoad } from './$types';
import {
	isKubernetes,
	getAllSettings,
	checkCanvasHealth,
	checkCalDAVHealth,
	checkOutlineHealth,
	listManualJobs
} from '$lib/k8s';
import { readState, computeTokenStatus, formatRelativeTime } from '$lib/state';

export const load: PageServerLoad = async () => {
	// Load settings and state in parallel
	const [settings, state] = await Promise.all([getAllSettings(), Promise.resolve(readState())]);

	const { syncSecrets, outlineSecrets, config } = settings;

	// Token status from issued-at date
	const tokenStatus = computeTokenStatus(syncSecrets.CANVAS_API_TOKEN_ISSUED_AT);

	// Run all health checks in parallel with individual error isolation
	const [canvasHealth, caldavHealth, outlineHealth] = await Promise.all([
		checkCanvasHealth(
			config.CANVAS_BASE_URL ?? syncSecrets.CANVAS_BASE_URL ?? '',
			syncSecrets.CANVAS_API_TOKEN ?? ''
		).catch((e) => ({
			name: 'Canvas',
			status: 'error' as const,
			message: String(e).slice(0, 120)
		})),
		checkCalDAVHealth(
			config.DAV_BASE_URL ?? '',
			syncSecrets.DAV_USERNAME ?? '',
			syncSecrets.DAV_PASSWORD ?? ''
		).catch((e) => ({
			name: 'CalDAV',
			status: 'error' as const,
			message: String(e).slice(0, 120)
		})),
		checkOutlineHealth(
			config.OUTLINE_BASE_URL ?? '',
			outlineSecrets.OUTLINE_API_TOKEN ?? ''
		).catch((e) => ({
			name: 'Outline',
			status: 'error' as const,
			message: String(e).slice(0, 120)
		}))
	]);

	// Recent jobs (k8s only — in docker mode we read from settings file separately)
	let recentJobs: Awaited<ReturnType<typeof listManualJobs>> = [];
	if (isKubernetes()) {
		recentJobs = await listManualJobs().catch(() => []);
	}

	return {
		tokenStatus,
		state,
		lastSync: formatRelativeTime(state.last_sync ?? state.last_assignments_run),
		lastNotes: formatRelativeTime(state.last_notes ?? state.last_assignments_run),
		healthChecks: [canvasHealth, caldavHealth, outlineHealth],
		recentJobs: recentJobs.slice(0, 5)
	};
};
