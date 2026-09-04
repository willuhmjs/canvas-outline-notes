import { fail } from '@sveltejs/kit';
import type { PageServerLoad, Actions } from './$types';
import { isKubernetes, getSecretData, patchSecret, readDockerSettings, writeDockerSettings } from '$lib/k8s';
import { computeTokenStatus } from '$lib/state';

// The token exactly as the sync jobs see it: in docker mode sync.py/notes.py
// fall back to /data/token.json when the settings secret is empty, so both
// stores are read. In k8s mode the pods read the canvas-sync-secrets Secret
// directly, which getSecretData already covers.
async function readStoredTokenDocker(): Promise<{ token?: string; issuedAt?: string }> {
	const sec = readDockerSettings().secrets['canvas-sync-secrets'];
	let token = sec.CANVAS_API_TOKEN;
	let issuedAt = sec.CANVAS_API_TOKEN_ISSUED_AT;
	if (!token) {
		try {
			const fs = await import('fs');
			const raw = JSON.parse(fs.default.readFileSync('/data/token.json', 'utf-8'));
			if (typeof raw.token === 'string') token = raw.token;
			if (!issuedAt && typeof raw.issued_at === 'string') issuedAt = raw.issued_at;
		} catch {
			// no token file -- token genuinely unset
		}
	}
	return { token, issuedAt };
}

export const load: PageServerLoad = async () => {
	let issuedAt: string | undefined;
	let tokenLength: number | null = null;

	if (isKubernetes()) {
		const data = await getSecretData('canvas-sync-secrets');
		issuedAt = data.CANVAS_API_TOKEN_ISSUED_AT;
		tokenLength = data.CANVAS_API_TOKEN?.length ?? null;
	} else {
		const stored = await readStoredTokenDocker();
		issuedAt = stored.issuedAt;
		tokenLength = stored.token?.length ?? null;
	}

	const tokenStatus = computeTokenStatus(issuedAt);

	let canvasBaseUrl = 'https://canvas.odu.edu';
	if (isKubernetes()) {
		const { getConfigMapData } = await import('$lib/k8s');
		const cfg = await getConfigMapData('canvas-config').catch(() => ({}));
		canvasBaseUrl = cfg.CANVAS_BASE_URL ?? canvasBaseUrl;
	} else {
		const settings = readDockerSettings();
		canvasBaseUrl = settings.config?.CANVAS_BASE_URL ?? canvasBaseUrl;
	}

	return { tokenStatus, tokenLength, canvasBaseUrl };
};

export const actions: Actions = {
	reveal: async () => {
		let token: string | undefined;
		if (isKubernetes()) {
			const data = await getSecretData('canvas-sync-secrets');
			token = data.CANVAS_API_TOKEN;
		} else {
			token = (await readStoredTokenDocker()).token;
		}
		if (!token) {
			return fail(404, { revealError: 'No token is stored yet — paste one below first.' });
		}
		return { revealedToken: token };
	},

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
