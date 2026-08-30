import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { getAllSettings, saveSettings, listChatModels } from '$lib/k8s';

export const load: PageServerLoad = async () => {
	const { syncSecrets, outlineSecrets, config } = await getAllSettings();

	let models: string[] = [];
	let modelsError: string | null = null;
	if (config.CHAT_API_BASE_URL && outlineSecrets.CHAT_API_KEY) {
		const result = await listChatModels(config.CHAT_API_BASE_URL, outlineSecrets.CHAT_API_KEY);
		if ('error' in result) modelsError = result.error;
		else models = result.models;
	}

	return { syncSecrets, outlineSecrets, config, models, modelsError };
};

function str(fd: FormData, key: string): string {
	return (fd.get(key) as string | null)?.trim() ?? '';
}

export const actions: Actions = {
	canvas: async ({ request }) => {
		const fd = await request.formData();
		try {
			await saveSettings(
				{ CANVAS_ICS_URL: str(fd, 'CANVAS_ICS_URL') },
				{},
				{
					CANVAS_BASE_URL: str(fd, 'CANVAS_BASE_URL'),
					COMPLETION_LOOKBACK_DAYS: str(fd, 'COMPLETION_LOOKBACK_DAYS')
				}
			);
			return { success: true, section: 'canvas' };
		} catch (e) {
			return fail(500, { error: String(e), section: 'canvas' });
		}
	},

	caldav: async ({ request }) => {
		const fd = await request.formData();

		// Build alarm trigger value
		const alarmPreset = str(fd, 'ALARM_TRIGGER_preset');
		const alarmCustom = str(fd, 'ALARM_TRIGGER_custom');
		const alarmTrigger = alarmPreset === 'custom' ? alarmCustom : alarmPreset;

		const syncUpdates: Record<string, string> = {
			DAV_USERNAME: str(fd, 'DAV_USERNAME'),
			DAV_PASSWORD: str(fd, 'DAV_PASSWORD')
		};
		// Only update password if a new one was provided (blank = keep existing)
		if (!syncUpdates.DAV_PASSWORD) delete syncUpdates.DAV_PASSWORD;

		try {
			await saveSettings(
				syncUpdates,
				{},
				{
					DAV_BASE_URL: str(fd, 'DAV_BASE_URL'),
					DAV_CALENDAR_DISPLAYNAME: str(fd, 'DAV_CALENDAR_DISPLAYNAME'),
					ALARM_TRIGGER: alarmTrigger
				}
			);
			return { success: true, section: 'caldav' };
		} catch (e) {
			return fail(500, { error: String(e), section: 'caldav' });
		}
	},

	outline: async ({ request }) => {
		const fd = await request.formData();
		const outlineUpdates: Record<string, string> = {
			OUTLINE_API_TOKEN: str(fd, 'OUTLINE_API_TOKEN')
		};
		if (!outlineUpdates.OUTLINE_API_TOKEN) delete outlineUpdates.OUTLINE_API_TOKEN;

		try {
			await saveSettings(
				{},
				outlineUpdates,
				{
					OUTLINE_BASE_URL: str(fd, 'OUTLINE_BASE_URL'),
					OUTLINE_COLLECTION_NAME: str(fd, 'OUTLINE_COLLECTION_NAME'),
					CURRENT_WINDOW_DAYS: str(fd, 'CURRENT_WINDOW_DAYS')
				}
			);
			return { success: true, section: 'outline' };
		} catch (e) {
			return fail(500, { error: String(e), section: 'outline' });
		}
	},

	ai: async ({ request }) => {
		const fd = await request.formData();
		const aiKeyUpdate: Record<string, string> = {
			CHAT_API_KEY: str(fd, 'CHAT_API_KEY')
		};
		if (!aiKeyUpdate.CHAT_API_KEY) delete aiKeyUpdate.CHAT_API_KEY;

		// Prompts: store custom value; if empty string submitted, remove the key
		// so notes.py falls back to its built-in default
		const configUpdates: Record<string, string> = {
			CHAT_API_BASE_URL: str(fd, 'CHAT_API_BASE_URL'),
			CHAT_MODEL_TEXT: str(fd, 'CHAT_MODEL_TEXT'),
			CHAT_MODEL_VISION: str(fd, 'CHAT_MODEL_VISION')
		};

		// Prompts: save non-empty values; empty string clears the override (notes.py uses built-in default).
		// All three textareas are always in the DOM (CSS hidden when inactive), so all three
		// fields are always submitted — we can safely distinguish "set" from "cleared".
		const promptAssignment = (fd.get('CHAT_PROMPT_ASSIGNMENT') as string | null) ?? '';
		const promptPresentation = (fd.get('CHAT_PROMPT_PRESENTATION') as string | null) ?? '';
		const promptTextNotes = (fd.get('CHAT_PROMPT_TEXT_NOTES') as string | null) ?? '';

		// Store in configmap (empty string = remove the override key on next read, keep as empty for now)
		configUpdates.CHAT_PROMPT_ASSIGNMENT = promptAssignment;
		configUpdates.CHAT_PROMPT_PRESENTATION = promptPresentation;
		configUpdates.CHAT_PROMPT_TEXT_NOTES = promptTextNotes;

		try {
			await saveSettings({}, aiKeyUpdate, configUpdates);
			return { success: true, section: 'ai' };
		} catch (e) {
			return fail(500, { error: String(e), section: 'ai' });
		}
	},

	aiListModels: async ({ request }) => {
		const fd = await request.formData();
		const baseUrl = str(fd, 'CHAT_API_BASE_URL');
		let apiKey = str(fd, 'CHAT_API_KEY');
		if (!apiKey) {
			// Blank key field means "keep existing" — fall back to the stored one.
			const { outlineSecrets } = await getAllSettings();
			apiKey = outlineSecrets.CHAT_API_KEY ?? '';
		}

		const result = await listChatModels(baseUrl, apiKey);
		if ('error' in result) {
			return fail(502, { error: result.error, section: 'ai_models' });
		}
		return { success: true, section: 'ai_models', models: result.models };
	},

	schedule: async ({ request }) => {
		const fd = await request.formData();
		try {
			await saveSettings(
				{},
				{},
				{
					SYNC_INTERVAL_MINUTES: str(fd, 'SYNC_INTERVAL_MINUTES'),
					NOTES_INTERVAL_MINUTES: str(fd, 'NOTES_INTERVAL_MINUTES'),
					TZ: str(fd, 'TZ')
				}
			);
			return { success: true, section: 'schedule' };
		} catch (e) {
			return fail(500, { error: String(e), section: 'schedule' });
		}
	}
};
