import { SvelteKitAuth } from '@auth/sveltekit';
import { sequence } from '@sveltejs/kit/hooks';
import { redirect, type Handle } from '@sveltejs/kit';
import { env } from '$env/dynamic/private';

const allowedGroups = (env.ALLOWED_GROUPS ?? '')
	.split(',')
	.map((g) => g.trim())
	.filter(Boolean);

const { handle: authHandle } = SvelteKitAuth({
	trustHost: true,
	secret: env.AUTH_SECRET,
	providers: [
		{
			id: 'oidc',
			name: 'OIDC',
			type: 'oidc',
			issuer: env.AUTH_OIDC_ISSUER,
			clientId: env.AUTH_OIDC_ID,
			clientSecret: env.AUTH_OIDC_SECRET
		}
	],
	callbacks: {
		async signIn({ profile }) {
			// No ALLOWED_GROUPS configured: any user who can complete the OIDC flow is let in.
			if (allowedGroups.length === 0) return true;
			const groups = (profile?.groups as string[] | undefined) ?? [];
			return groups.some((g) => allowedGroups.includes(g));
		}
	}
});

const requireAuth: Handle = async ({ event, resolve }) => {
	const session = await event.locals.auth();
	if (!session && !event.url.pathname.startsWith('/auth')) {
		throw redirect(303, `/auth/signin?callbackUrl=${encodeURIComponent(event.url.pathname)}`);
	}
	return resolve(event);
};

export const handle = sequence(authHandle, requireAuth);
