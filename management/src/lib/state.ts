import fs from 'fs';
import type { AppState, TokenStatus } from './types.js';

const TOKEN_LIFETIME_DAYS = 90;

export function readState(stateFile = '/data/state.json'): AppState {
	try {
		if (fs.existsSync(stateFile)) {
			const raw = fs.readFileSync(stateFile, 'utf-8');
			return JSON.parse(raw) as AppState;
		}
	} catch (e) {
		console.error('Failed to read state.json:', e);
	}
	return {};
}

export function formatRelativeTime(isoString: string | undefined | null): string {
	if (!isoString) return 'Never';
	try {
		const date = new Date(isoString);
		if (isNaN(date.getTime())) return isoString;
		const diffMs = Date.now() - date.getTime();
		const diffSec = Math.floor(diffMs / 1000);

		if (diffSec < 0) return 'just now';
		if (diffSec < 60) return `${diffSec}s ago`;
		if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
		if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
		return `${Math.floor(diffSec / 86400)}d ago`;
	} catch {
		return isoString;
	}
}

export function formatAbsoluteTime(isoString: string | undefined | null): string {
	if (!isoString) return '—';
	try {
		const date = new Date(isoString);
		if (isNaN(date.getTime())) return isoString;
		return date.toLocaleString('en-US', {
			month: 'short',
			day: 'numeric',
			hour: '2-digit',
			minute: '2-digit'
		});
	} catch {
		return isoString;
	}
}

export function computeTokenStatus(issuedAt: string | undefined | null): TokenStatus {
	if (!issuedAt) {
		return {
			isSet: false,
			issuedAt: null,
			daysRemaining: null,
			daysElapsed: null,
			daysTotal: TOKEN_LIFETIME_DAYS,
			level: 'unknown'
		};
	}

	try {
		const issued = new Date(issuedAt);
		if (isNaN(issued.getTime())) throw new Error('bad date');

		const now = Date.now();
		const expiryMs = issued.getTime() + TOKEN_LIFETIME_DAYS * 86_400_000;
		const daysRemaining = Math.floor((expiryMs - now) / 86_400_000);
		const daysElapsed = TOKEN_LIFETIME_DAYS - Math.max(daysRemaining, 0);

		let level: TokenStatus['level'];
		if (daysRemaining < 0) level = 'expired';
		else if (daysRemaining < 14) level = 'warning';
		else level = 'healthy';

		return {
			isSet: true,
			issuedAt,
			daysRemaining,
			daysElapsed,
			daysTotal: TOKEN_LIFETIME_DAYS,
			level
		};
	} catch {
		return {
			isSet: true,
			issuedAt,
			daysRemaining: null,
			daysElapsed: null,
			daysTotal: TOKEN_LIFETIME_DAYS,
			level: 'unknown'
		};
	}
}
