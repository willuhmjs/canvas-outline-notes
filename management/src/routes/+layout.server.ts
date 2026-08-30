import type { LayoutServerLoad } from './$types';
import { isKubernetes, getNamespace } from '$lib/k8s';

export const load: LayoutServerLoad = async (event) => {
	const session = await event.locals.auth();
	const username = session?.user?.name ?? session?.user?.email ?? '';
	const mode = isKubernetes() ? 'kubernetes' : 'docker';
	const namespace = isKubernetes() ? getNamespace() : null;

	return {
		username,
		mode,
		namespace
	};
};
