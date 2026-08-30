import fs from 'fs';
import type { RegenerateProgress } from './types.js';

// Same /data volume used for state.json and settings.json in both
// Kubernetes and Docker mode -- lets the progress survive a page reload
// (and a pod restart) since the regeneration runs in the background.
const PROGRESS_FILE = process.env.REGENERATE_PROGRESS_FILE ?? '/data/regenerate-progress.json';

const IDLE: RegenerateProgress = { status: 'idle', total: 0, deleted: 0 };

export function readRegenerateProgress(): RegenerateProgress {
	try {
		if (fs.existsSync(PROGRESS_FILE)) {
			return JSON.parse(fs.readFileSync(PROGRESS_FILE, 'utf-8')) as RegenerateProgress;
		}
	} catch (e) {
		console.error('Failed to read regenerate-progress.json:', e);
	}
	return IDLE;
}

export function writeRegenerateProgress(progress: RegenerateProgress): void {
	try {
		fs.writeFileSync(PROGRESS_FILE, JSON.stringify(progress));
	} catch (e) {
		console.error('Failed to write regenerate-progress.json:', e);
	}
}
