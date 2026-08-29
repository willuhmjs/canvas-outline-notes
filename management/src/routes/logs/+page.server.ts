import type { PageServerLoad } from './$types';
import { isKubernetes, getRecentJobLogs, readDockerSettings } from '$lib/k8s';
import type { K8sJob } from '$lib/types';

type JobWithLogs = K8sJob & { logs: string };

export const load: PageServerLoad = async () => {
	if (isKubernetes()) {
		// Fetch last 3 completed jobs for each type in parallel
		const [syncJobs, notesJobs] = await Promise.all([
			getRecentJobLogs('sync', 3).catch((): JobWithLogs[] => []),
			getRecentJobLogs('notes', 3).catch((): JobWithLogs[] => [])
		]);

		return {
			syncJobs,
			notesJobs,
			dockerHistory: null as null
		};
	}

	// Docker mode: show job history output
	const settings = readDockerSettings();
	const history = settings.jobHistory ?? [];

	return {
		syncJobs: [] as JobWithLogs[],
		notesJobs: [] as JobWithLogs[],
		dockerHistory: history.slice(0, 10)
	};
};
