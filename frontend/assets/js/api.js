// Thin fetch wrapper: consistent errors, friendly messages, a tiny GET cache.
export class ApiError extends Error {
  constructor(message, status = 0, code = 'error', details = null, retryAfter = null) {
    super(message); this.status = status; this.code = code; this.details = details; this.retryAfter = retryAfter;
  }
}

const cache = new Map();
const qs = (params) => {
  const u = new URLSearchParams();
  for (const [k, v] of Object.entries(params || {})) if (v !== '' && v != null) u.append(k, v);
  const s = u.toString();
  return s ? `?${s}` : '';
};

async function request(url, init) {
  let res;
  try { res = await fetch(url, init); }
  catch { throw new ApiError('Cannot reach the server. Check your connection and try again.', 0, 'network'); }
  let body = null;
  if ((res.headers.get('content-type') || '').includes('json')) { try { body = await res.json(); } catch { /* ignore */ } }
  if (!res.ok) {
    const e = body && body.error;
    throw new ApiError(e?.message || `Something went wrong (${res.status}). Please try again.`, res.status, e?.code, e?.details, res.headers.get('retry-after'));
  }
  return body;
}

export function get(path, params, { fresh = false } = {}) {
  const url = path + qs(params);
  if (!fresh && cache.has(url)) return cache.get(url);
  const p = request(url).catch((e) => { cache.delete(url); throw e; });
  cache.set(url, p);
  return p;
}

export async function post(path, formData) {
  const out = await request(path, { method: 'POST', body: formData });
  cache.clear(); // new data exists: every cached read is now stale
  return out;
}
export const invalidate = () => cache.clear();
