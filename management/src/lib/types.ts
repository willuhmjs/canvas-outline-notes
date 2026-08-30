// All keys match the env var names used by sync.py / notes.py

export interface SyncSecrets {
	CANVAS_ICS_URL: string;
	CANVAS_API_TOKEN: string;
	CANVAS_API_TOKEN_ISSUED_AT: string;
	DAV_USERNAME: string;
	DAV_PASSWORD: string;
}

export interface OutlineSecrets {
	CHAT_API_KEY: string;
	OUTLINE_API_TOKEN: string;
}

export interface AppConfig {
	CANVAS_BASE_URL: string;
	DAV_BASE_URL: string;
	DAV_CALENDAR_DISPLAYNAME: string;
	OUTLINE_BASE_URL: string;
	OUTLINE_COLLECTION_NAME: string;
	CHAT_API_BASE_URL: string;
	CHAT_MODEL_TEXT: string;
	CHAT_MODEL_VISION: string;
	/** Custom prompt for assignment notes. If unset, notes.py uses its built-in default. */
	CHAT_PROMPT_ASSIGNMENT: string;
	/** Custom prompt for presentation/slide file notes. */
	CHAT_PROMPT_PRESENTATION: string;
	/** Custom prompt for text-content notes (transcripts, docx, etc.). */
	CHAT_PROMPT_TEXT_NOTES: string;
	TZ: string;
	SYNC_INTERVAL_MINUTES: string;
	NOTES_INTERVAL_MINUTES: string;
	ALARM_TRIGGER: string;
	CURRENT_WINDOW_DAYS: string;
	COMPLETION_LOOKBACK_DAYS: string;
}

export interface AppState {
	last_sync?: string;
	last_notes?: string;
	last_assignments_run?: string;
	last_modules_run?: string;
	[key: string]: string | undefined;
}

export interface TokenStatus {
	isSet: boolean;
	issuedAt: string | null;
	daysRemaining: number | null;
	daysElapsed: number | null;
	daysTotal: number;
	/** healthy = >14 days, warning = 1-14 days, expired = 0 or less, unknown = no issued date */
	level: 'healthy' | 'warning' | 'expired' | 'unknown';
}

export interface HealthCheck {
	name: string;
	status: 'healthy' | 'error' | 'unknown';
	message: string;
	latencyMs?: number;
}

export interface K8sJob {
	name: string;
	namespace: string;
	/** Which cronjob spawned this */
	type: 'sync' | 'notes' | 'unknown';
	status: 'running' | 'succeeded' | 'failed' | 'unknown';
	startTime: string | null;
	completionTime: string | null;
}

export interface DockerJobRecord {
	id: string;
	name: string;
	type: 'sync' | 'notes';
	startTime: string;
	endTime: string | null;
	status: 'running' | 'succeeded' | 'failed';
	output: string;
	exitCode: number | null;
}

export interface DockerSettings {
	secrets: {
		'canvas-sync-secrets': Partial<SyncSecrets>;
		'canvas-outline-secrets': Partial<OutlineSecrets>;
	};
	config: Partial<AppConfig>;
	jobHistory: DockerJobRecord[];
}

export type Mode = 'kubernetes' | 'docker';

export interface RegenerateProgress {
	status: 'idle' | 'listing' | 'deleting' | 'queuing' | 'done' | 'error';
	total: number;
	deleted: number;
	jobName?: string;
	error?: string;
	startedAt?: string;
	/** Bumped on every write while active -- lets the UI/guard detect a hung run. */
	updatedAt?: string;
	finishedAt?: string;
}
