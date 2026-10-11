export class ApiError extends Error {
	constructor(
		public status: number,
		message: string
	) {
		super(message);
	}
}

async function parse(res: Response) {
	const type = res.headers.get('content-type') || '';
	const body = type.includes('json') ? await res.json() : await res.text();
	if (!res.ok) {
		let msg = typeof body === 'string' ? body : body?.detail;
		if (Array.isArray(msg)) msg = msg.map((d) => d.msg).join(', ');
		throw new ApiError(res.status, msg || `Request failed (${res.status})`);
	}
	return body;
}

function headers(extra?: HeadersInit): HeadersInit {
	// The custom header is the CSRF guard the server checks on every write.
	return { 'x-platedex': '1', ...extra };
}

export const api = {
	async get<T = any>(path: string, params?: Record<string, unknown>): Promise<T> {
		const q = params ? toQuery(params) : '';
		return parse(await fetch(path + (q ? `?${q}` : ''), { headers: headers() }));
	},
	async send<T = any>(method: string, path: string, body?: unknown): Promise<T> {
		return parse(
			await fetch(path, {
				method,
				headers: headers(body === undefined ? undefined : { 'content-type': 'application/json' }),
				body: body === undefined ? undefined : JSON.stringify(body)
			})
		);
	},
	post<T = any>(path: string, body?: unknown) {
		return this.send<T>('POST', path, body ?? {});
	},
	patch<T = any>(path: string, body: unknown) {
		return this.send<T>('PATCH', path, body);
	},
	put<T = any>(path: string, body: unknown) {
		return this.send<T>('PUT', path, body);
	},
	del<T = any>(path: string) {
		return this.send<T>('DELETE', path);
	},
	/** Multipart upload with progress (fetch has no upload progress). */
	upload(path: string, form: FormData, onProgress: (pct: number) => void): Promise<any> {
		return new Promise((resolve, reject) => {
			const xhr = new XMLHttpRequest();
			xhr.open('POST', path);
			xhr.setRequestHeader('x-platedex', '1');
			xhr.upload.onprogress = (e) => e.lengthComputable && onProgress(Math.round((e.loaded / e.total) * 100));
			xhr.onload = () => {
				let body: any = xhr.responseText;
				try {
					body = JSON.parse(xhr.responseText);
				} catch {
					/* not JSON */
				}
				if (xhr.status >= 200 && xhr.status < 300) resolve(body);
				else reject(new ApiError(xhr.status, body?.detail || `Upload failed (${xhr.status})`));
			};
			xhr.onerror = () => reject(new ApiError(0, 'Connection dropped'));
			xhr.send(form);
		});
	}
};

export function toQuery(params: Record<string, unknown>): string {
	const q = new URLSearchParams();
	for (const [k, v] of Object.entries(params)) {
		if (v === undefined || v === null || v === '' || v === false) continue;
		if (Array.isArray(v)) {
			if (v.length) q.set(k, v.join(','));
		} else q.set(k, String(v));
	}
	return q.toString();
}

export function errorText(e: unknown): string {
	if (e instanceof ApiError) return e.message;
	if (e instanceof Error) return e.message;
	return 'Something went wrong';
}
