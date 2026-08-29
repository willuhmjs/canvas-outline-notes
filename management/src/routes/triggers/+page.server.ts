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

export const load: PageServerLoad = async () => {
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
		dockerHistory
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
