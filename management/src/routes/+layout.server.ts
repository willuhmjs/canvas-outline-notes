import type { LayoutServerLoad } from './$types';
import { isKubernetes, getNamespace } from '$lib/k8s';

export const load: LayoutServerLoad = async ({ request }) => {
	const username = request.headers.get('x-authentik-username') ?? '';
	const mode = isKubernetes() ? 'kubernetes' : 'docker';
	const namespace = isKubernetes() ? getNamespace() : null;

	return {
		username,
		mode,
		namespace
	};
};
