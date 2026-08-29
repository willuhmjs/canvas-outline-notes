import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { isKubernetes, getSecretData, patchSecret, readDockerSettings, writeDockerSettings } from '$lib/k8s';
import { computeTokenStatus } from '$lib/state';

export const load: PageServerLoad = async () => {
	let issuedAt: string | undefined;
	let tokenLength: number | null = null;

	if (isKubernetes()) {
		const data = await getSecretData('canvas-sync-secrets');
		issuedAt = data.CANVAS_API_TOKEN_ISSUED_AT;
		tokenLength = data.CANVAS_API_TOKEN?.length ?? null;
	} else {
		const settings = readDockerSettings();
		const sec = settings.secrets['canvas-sync-secrets'];
		issuedAt = sec.CANVAS_API_TOKEN_ISSUED_AT;
		tokenLength = sec.CANVAS_API_TOKEN?.length ?? null;
	}

	const tokenStatus = computeTokenStatus(issuedAt);
	return { tokenStatus, tokenLength };
};

export const actions: Actions = {
	save: async ({ request }) => {
		const fd = await request.formData();
		const token = (fd.get('token') as string | null)?.trim() ?? '';

		if (!token) {
			return fail(400, { error: 'Token cannot be empty' });
		}

		const issuedAt = new Date().toISOString().slice(0, 10); // YYYY-MM-DD

		try {
			if (isKubernetes()) {
				await patchSecret('canvas-sync-secrets', {
					CANVAS_API_TOKEN: token,
					CANVAS_API_TOKEN_ISSUED_AT: issuedAt
				});
			} else {
				const settings = readDockerSettings();
				settings.secrets['canvas-sync-secrets'].CANVAS_API_TOKEN = token;
				settings.secrets['canvas-sync-secrets'].CANVAS_API_TOKEN_ISSUED_AT = issuedAt;
				writeDockerSettings(settings);

				// Also write the token.json file that sync.py reads as fallback
				const fs = await import('fs');
				const tokenFile = '/data/token.json';
				const dir = tokenFile.substring(0, tokenFile.lastIndexOf('/'));
				if (dir) fs.default.mkdirSync(dir, { recursive: true });
				fs.default.writeFileSync(tokenFile, JSON.stringify({ token, issued_at: issuedAt }, null, 2));
			}
			return { success: true };
		} catch (e) {
			return fail(500, { error: String(e) });
		}
	}
};
