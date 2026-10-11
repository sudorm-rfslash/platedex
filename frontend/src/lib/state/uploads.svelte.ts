/** The Upload screen's batch. Lives outside the page so switching tabs doesn't lose progress. */
import exifr from 'exifr';
import { api, errorText } from '../api';
import { refreshCounts } from './counts.svelte';

export type RowStatus = 'checking' | 'queued' | 'uploading' | 'reading' | 'review' | 'done' | 'failed';
export type Row = {
	key: string;
	name: string;
	file?: File;
	preview?: string;
	status: RowStatus;
	pct: number;
	sub: string;
	needGps: boolean;
	needTime: boolean;
	pinned: { lat: number; lon: number; label: string } | null;
	timed: { iso: string; label: string } | null;
	device: { lat: number; lon: number; accuracy: number } | null;
	captureMode: 'upload' | 'camera';
	photoId?: number;
	thumb?: string;
	serverFailed?: boolean;
	lastModified?: number;
};

export const uploads = $state({ rows: [] as Row[], loadedRecent: false });

let seq = 0;
let polling: ReturnType<typeof setInterval> | undefined;
let active = 0;
const MAX_PARALLEL = 2;

const LABEL: Record<RowStatus, [string, string]> = {
	checking: ['checking', 'p-queued'],
	queued: ['queued', 'p-queued'],
	uploading: ['reading', 'p-reading'],
	reading: ['reading', 'p-reading'],
	review: ['needs review', 'p-review'],
	done: ['done', 'p-done'],
	failed: ['failed', 'p-failed']
};
export const statusLabel = (s: RowStatus) => LABEL[s];

export function blocked(r: Row) {
	return (r.needGps && !r.pinned) || (r.needTime && !r.timed);
}

function waitingText(r: Row) {
	const gps = r.needGps && !r.pinned;
	const time = r.needTime && !r.timed;
	if (gps && time) return 'Waiting for location and time';
	if (gps) return 'Waiting for a location';
	if (time) return 'Waiting for a capture time';
	return 'Queued';
}

async function inspect(file: File): Promise<{ gps: boolean; time: boolean }> {
	try {
		const tags = await exifr.parse(file, { gps: true, tiff: true, exif: true, xmp: false, icc: false, iptc: false });
		const gps = typeof tags?.latitude === 'number' && typeof tags?.longitude === 'number';
		const time = !!(tags?.DateTimeOriginal || tags?.CreateDate || tags?.DateTimeDigitized);
		return { gps, time };
	} catch {
		return { gps: false, time: false };
	}
}

/** The photo formats the server accepts (it checks the actual bytes too). */
export const PHOTO_ACCEPT = 'image/jpeg,image/png,image/webp,image/heic,image/heif,image/avif,.jpg,.jpeg,.png,.webp,.heic,.heif,.avif';
const PHOTO_MIME = /^image\/(jpeg|pjpeg|png|webp|heic|heif|heic-sequence|heif-sequence|avif)$/;
const PHOTO_EXT = /\.(jpe?g|png|webp|heic|heif|avif)$/i;

export function isPhoto(f: File) {
	// Some browsers leave HEIC files with an empty type, so fall back to the extension.
	return PHOTO_MIME.test(f.type) || (!f.type || f.type === 'application/octet-stream' ? PHOTO_EXT.test(f.name) : false);
}

/** Toast text for a pick/drop/paste: how many were added and how many were skipped. */
export function addedText(added: number, skipped: number, verb = 'added') {
	const a = added ? `${added} photo${added === 1 ? '' : 's'} ${verb}` : '';
	const s = skipped ? `${skipped} file${skipped === 1 ? '' : 's'} skipped (only JPG, HEIC, PNG, WebP and AVIF photos)` : '';
	return [a, s].filter(Boolean).join(' · ');
}

export async function addFiles(
	files: File[],
	opts: { captureMode?: 'upload' | 'camera'; device?: Row['device'] } = {}
) {
	files = files.filter(isPhoto);
	if (!files.length) return;
	const fresh: Row[] = files.map((file) => ({
		key: `r${++seq}`,
		name: file.name || `photo-${seq}.jpg`,
		file,
		preview: /image\/(jpeg|png|webp)/.test(file.type) ? URL.createObjectURL(file) : undefined,
		status: 'checking',
		pct: 0,
		sub: 'Checking location and time…',
		needGps: false,
		needTime: false,
		pinned: null,
		timed: null,
		device: opts.device ?? null,
		captureMode: opts.captureMode ?? 'upload',
		lastModified: file.lastModified
	}));
	uploads.rows = [...fresh, ...uploads.rows];
	for (const r of fresh) {
		const row = uploads.rows.find((x) => x.key === r.key)!;
		if (row.captureMode === 'camera') {
			row.needGps = !row.device;
			row.needTime = false;
			row.timed = { iso: new Date(row.lastModified ?? Date.now()).toISOString(), label: 'now' };
		} else {
			const meta = await inspect(r.file!);
			row.needGps = !meta.gps;
			row.needTime = !meta.time;
		}
		row.status = 'queued';
		row.sub = waitingText(row);
	}
	pump();
}

export function pin(key: string, lat: number, lon: number, label: string) {
	const r = uploads.rows.find((x) => x.key === key);
	if (!r) return;
	r.pinned = { lat, lon, label };
	r.sub = waitingText(r);
	pump();
}

export function setTime(key: string, iso: string, label: string) {
	const r = uploads.rows.find((x) => x.key === key);
	if (!r) return;
	r.timed = { iso, label };
	r.sub = waitingText(r);
	pump();
}

function pump() {
	for (const r of uploads.rows) {
		if (active >= MAX_PARALLEL) break;
		if (r.status === 'queued' && r.file && !blocked(r)) send(r.key);
	}
}

async function send(key: string) {
	const r = uploads.rows.find((x) => x.key === key)!;
	active++;
	r.status = 'uploading';
	r.pct = 4;
	r.sub = 'Uploading…';
	const form = new FormData();
	form.append('file', r.file!, r.name);
	form.append('capture_mode', r.captureMode);
	const loc = r.pinned ?? r.device;
	if (loc && (r.needGps || r.captureMode === 'camera')) {
		form.append('lat', String(loc.lat));
		form.append('lon', String(loc.lon));
		form.append('location_source', r.pinned ? 'manual' : 'device');
		if ('accuracy' in loc) form.append('accuracy', String(loc.accuracy));
	}
	if (r.timed && (r.needTime || r.captureMode === 'camera')) {
		form.append('taken_at', r.timed.iso);
		form.append('time_source', r.captureMode === 'camera' ? 'device' : 'manual');
	}
	try {
		const photo = await api.upload('/api/photos', form, (pct) => {
			const row = uploads.rows.find((x) => x.key === key);
			if (row) row.pct = Math.max(row.pct, Math.round(pct * 0.6));
		});
		const row = uploads.rows.find((x) => x.key === key)!;
		applyServer(row, photo);
		if (photo.duplicate) row.sub = 'Already uploaded · ' + photo.summary;
		startPolling();
	} catch (e) {
		const row = uploads.rows.find((x) => x.key === key);
		if (row) {
			row.status = 'failed';
			row.sub = row.pct > 4 ? `${errorText(e)} at ${row.pct}%` : errorText(e);
		}
	} finally {
		active--;
		pump();
	}
}

type ServerPhoto = { id: number; status: string; summary: string; thumb_url: string; name: string };

function applyServer(r: Row, p: ServerPhoto) {
	r.photoId = p.id;
	r.thumb = p.thumb_url;
	r.serverFailed = p.status === 'failed';
	if (p.status === 'queued' || p.status === 'processing') {
		r.status = 'reading';
		r.pct = Math.max(r.pct, 64);
		r.sub = p.status === 'queued' ? 'Waiting for the reader…' : 'Reading plate…';
	} else if (p.status === 'needs_review') {
		r.status = 'review';
		r.pct = 100;
		r.sub = p.summary;
	} else if (p.status === 'done') {
		r.status = 'done';
		r.pct = 100;
		r.sub = p.summary;
	} else if (p.status === 'failed') {
		r.status = 'failed';
		r.sub = p.summary;
	}
}

function startPolling() {
	if (polling) return;
	polling = setInterval(async () => {
		const ids = uploads.rows.filter((r) => r.photoId && r.status === 'reading').map((r) => r.photoId);
		if (!ids.length) {
			clearInterval(polling);
			polling = undefined;
			return;
		}
		try {
			const photos: ServerPhoto[] = await api.get('/api/photos', { ids: ids.join(',') });
			let finished = false;
			for (const p of photos) {
				const r = uploads.rows.find((x) => x.photoId === p.id);
				if (!r) continue;
				applyServer(r, p);
				if (r.status !== 'reading') finished = true;
				else r.pct = Math.min(96, r.pct + 4);
			}
			if (finished) refreshCounts();
		} catch {
			/* try again next tick */
		}
	}, 1500);
}

export async function retry(key: string) {
	const r = uploads.rows.find((x) => x.key === key);
	if (!r) return;
	if (r.photoId && r.serverFailed) {
		try {
			const p = await api.post(`/api/photos/${r.photoId}/retry`);
			applyServer(r, p);
			startPolling();
		} catch (e) {
			r.sub = errorText(e);
		}
	} else if (r.file) {
		r.status = 'queued';
		r.pct = 0;
		r.sub = 'Queued';
		pump();
	}
}

/** Rows that can be taken off the list: not yet sent, failed, or finished. */
export function removable(r: Row) {
	return r.status !== 'uploading' && r.status !== 'checking';
}

/** Drop a row from the batch. A file that hasn't been sent yet is never uploaded. */
export function remove(key: string) {
	const r = uploads.rows.find((x) => x.key === key);
	if (!r || !removable(r)) return;
	if (r.preview) URL.revokeObjectURL(r.preview);
	uploads.rows = uploads.rows.filter((x) => x.key !== key);
}

/** Clear rows whose photo is fully handled (done or waiting in Review). */
export function clearFinished() {
	const gone = uploads.rows.filter((r) => r.status === 'done' || r.status === 'review');
	for (const r of gone) if (r.preview) URL.revokeObjectURL(r.preview);
	const keys = new Set(gone.map((r) => r.key));
	uploads.rows = uploads.rows.filter((r) => !keys.has(r.key));
}

/** After a reload, show the latest uploads so the screen isn't empty. */
export async function loadRecent() {
	if (uploads.loadedRecent || uploads.rows.length) return;
	uploads.loadedRecent = true;
	try {
		const photos: ServerPhoto[] = await api.get('/api/photos', { limit: 8 });
		uploads.rows = photos.map((p) => {
			const r: Row = {
				key: `p${p.id}`,
				name: p.name,
				status: 'queued',
				pct: 0,
				sub: '',
				needGps: false,
				needTime: false,
				pinned: null,
				timed: null,
				device: null,
				captureMode: 'upload'
			};
			applyServer(r, p);
			return r;
		});
		startPolling();
	} catch {
		/* not signed in yet */
	}
}

/** Photos shared to Platedex from the Android share sheet (stashed by the service worker). */
export async function takeShared(): Promise<number> {
	if (!('caches' in window)) return 0;
	const cache = await caches.open('pdx-shared');
	const keys = await cache.keys();
	const files: File[] = [];
	for (const req of keys) {
		const res = await cache.match(req);
		if (!res) continue;
		const blob = await res.blob();
		const name = decodeURIComponent(res.headers.get('x-name') || 'shared.jpg');
		files.push(new File([blob], name, { type: blob.type, lastModified: Number(res.headers.get('x-modified')) || Date.now() }));
		await cache.delete(req);
	}
	const ok = files.filter(isPhoto);
	if (ok.length) await addFiles(ok);
	return ok.length;
}
