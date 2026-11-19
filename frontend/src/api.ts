import type { AppConfig, Comparison, Investigation, HistoryItem } from './types';

const TOKEN_KEY = 'imagetrace.ownerToken';
const PREFS_KEY = 'imagetrace.preferences';

// Same-origin by default. Set VITE_API_BASE_URL for a split frontend/backend deploy.
const API_BASE = String(import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');

export function apiUrl(path: string): string {
  if (/^https?:\/\//i.test(path) || path.startsWith('//')) return path;
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`;
}

export interface Preferences {
  lang: 'es' | 'pt' | 'en';
  allowGps: boolean;
  allowExternal: boolean;
  retentionHours: number;
}

export const defaultPreferences: Preferences = {
  lang: 'es',
  allowGps: false,
  allowExternal: true,
  retentionHours: 24,
};

function randomToken(): string {
  const bytes = new Uint8Array(32);
  crypto.getRandomValues(bytes);
  let binary = '';
  bytes.forEach((b) => { binary += String.fromCharCode(b); });
  return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '');
}

export function getOwnerToken(): string {
  let token = localStorage.getItem(TOKEN_KEY);
  if (!token || token.length < 16) {
    token = randomToken();
    localStorage.setItem(TOKEN_KEY, token);
  }
  return token;
}

export function resetOwnerToken(): string {
  const token = randomToken();
  localStorage.setItem(TOKEN_KEY, token);
  return token;
}

export function maskedToken(): string {
  const token = getOwnerToken();
  return `${token.slice(0, 6)}••••••••${token.slice(-4)}`;
}

export function loadPreferences(): Preferences {
  try {
    const raw = localStorage.getItem(PREFS_KEY);
    return raw ? { ...defaultPreferences, ...JSON.parse(raw) } : { ...defaultPreferences };
  } catch {
    return { ...defaultPreferences };
  }
}

export function savePreferences(prefs: Preferences): void {
  localStorage.setItem(PREFS_KEY, JSON.stringify(prefs));
}

async function parseError(response: Response): Promise<string> {
  try {
    const data = await response.json();
    if (typeof data.detail === 'string') return data.detail;
    if (Array.isArray(data.detail)) return data.detail.map((d: { msg?: string }) => d.msg || '').join('; ');
    return JSON.stringify(data);
  } catch {
    return `HTTP ${response.status}`;
  }
}

export async function apiFetch<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers || {});
  headers.set('X-Owner-Token', getOwnerToken());
  const response = await fetch(apiUrl(path), { ...init, headers });
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as T;
}

export async function apiPublic<T>(path: string): Promise<T> {
  const response = await fetch(apiUrl(path));
  if (!response.ok) throw new Error(await parseError(response));
  return (await response.json()) as T;
}

function prefixInvestigation(investigation: Investigation): Investigation {
  const prefixed = { ...investigation };
  if (prefixed.display_url) prefixed.display_url = apiUrl(prefixed.display_url);
  if (prefixed.diff_url) prefixed.diff_url = apiUrl(prefixed.diff_url);
  if (prefixed.report_urls) {
    prefixed.report_urls = {
      json: apiUrl(prefixed.report_urls.json),
      pdf: apiUrl(prefixed.report_urls.pdf),
    };
  }
  prefixed.matches = (prefixed.matches || []).map((match) => ({
    ...match,
    thumbnail_url_signed: match.thumbnail_url_signed ? apiUrl(match.thumbnail_url_signed) : undefined,
  }));
  if (prefixed.comparison?.diff_url) {
    prefixed.comparison = { ...prefixed.comparison, diff_url: apiUrl(prefixed.comparison.diff_url) };
  }
  return prefixed;
}

export function getConfig(): Promise<AppConfig> {
  return apiPublic<AppConfig>('/api/config');
}

export async function getHistory(): Promise<{ items: HistoryItem[]; count: number }> {
  const result = await apiFetch<{ items: HistoryItem[]; count: number }>('/api/investigations');
  return {
    ...result,
    items: result.items.map((item) => ({ ...item, thumbnail_url: apiUrl(item.thumbnail_url) })),
  };
}

export async function getInvestigation(id: string): Promise<{ investigation: Investigation }> {
  const response = await apiFetch<{ investigation: Investigation }>(`/api/investigations/${id}`);
  return { investigation: prefixInvestigation(response.investigation) };
}

export function getStatus(id: string): Promise<{ status: string; stage: string; progress: number; error: string | null }> {
  return apiFetch(`/api/investigations/${id}/status`);
}

export function createFromFile(form: FormData): Promise<{ id: string }> {
  return apiFetch('/api/investigations', { method: 'POST', body: form });
}

export function createFromUrl(payload: {
  image_url: string; keywords: string; allow_gps: boolean; allow_external: boolean; retention_hours: number; lang: string;
}): Promise<{ id: string }> {
  return apiFetch('/api/investigations/url', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  });
}

export async function downloadReport(path: string, filename: string): Promise<void> {
  const response = await fetch(apiUrl(path), { headers: { 'X-Owner-Token': getOwnerToken() } });
  if (!response.ok) throw new Error(await parseError(response));
  const blob = await response.blob();
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = filename;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  setTimeout(() => URL.revokeObjectURL(url), 4000);
}

export function deleteInvestigation(id: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/api/investigations/${id}`, { method: 'DELETE' });
}

export async function compareImages(id: string, file: File): Promise<Comparison> {
  const form = new FormData();
  form.append('file', file);
  const result = await apiFetch<Comparison>(`/api/investigations/${id}/compare`, { method: 'POST', body: form });
  return { ...result, diff_url: result.diff_url ? apiUrl(result.diff_url) : undefined };
}

export function getIndex(): Promise<{ items: { id: string; sha256: string; label: string; source_url: string | null; created_at: string; expires_at: string | null }[] }> {
  return apiFetch('/api/index');
}

export function addIndex(form: FormData): Promise<{ id: string }> {
  return apiFetch('/api/index', { method: 'POST', body: form });
}

export function deleteIndexEntry(id: string): Promise<{ deleted: boolean }> {
  return apiFetch(`/api/index/${id}`, { method: 'DELETE' });
}

export function purgeExpired(): Promise<{ removed: number }> {
  return apiFetch('/api/privacy/purge', { method: 'POST' });
}

export function deleteAllData(): Promise<{ deleted_investigations: number; deleted_index_entries: number }> {
  return apiFetch('/api/privacy/all', { method: 'DELETE' });
}

export async function createSignedLink(id: string, format: 'pdf' | 'json'): Promise<{ url: string; expires_in_seconds: number; note: string }> {
  const result = await apiFetch<{ url: string; expires_in_seconds: number; note: string }>(
    `/api/investigations/${id}/signed-link`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ format }),
    },
  );
  return { ...result, url: apiUrl(result.url) };
}
