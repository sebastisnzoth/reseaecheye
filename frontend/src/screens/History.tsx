import { useCallback, useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  Copy, Database, Download, ExternalLink, FileImage, History as HistoryIcon, KeyRound,
  LockKeyhole, RefreshCw, ShieldCheck, Trash2,
} from 'lucide-react';
import {
  addIndex, deleteAllData, deleteIndexEntry, deleteInvestigation, downloadReport,
  getHistory, getIndex, getOwnerToken, maskedToken, purgeExpired, resetOwnerToken,
} from '../api';
import { EmptyState, ErrorBox, KeyValue, Panel, Spinner, StatusBadge, formatDate } from '../components/ui';
import { useI18n } from '../i18n';
import type { HistoryItem } from '../types';

interface IndexItem {
  id: string; sha256: string; label: string; source_url: string | null; created_at: string; expires_at: string | null;
}

export default function History() {
  const { t, lang, prefs, setPrefs } = useI18n();
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [indexItems, setIndexItems] = useState<IndexItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [indexFile, setIndexFile] = useState<File | null>(null);
  const [indexUrl, setIndexUrl] = useState('');
  const [indexLabel, setIndexLabel] = useState('');

  const refresh = useCallback(async () => {
    setLoading(true);
    try {
      const [history, index] = await Promise.all([getHistory(), getIndex()]);
      setItems(history.items);
      setIndexItems(index.items);
      setError(null);
    } catch (err) { setError(err instanceof Error ? err.message : String(err)); }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { void refresh(); }, [refresh]);

  async function act(action: () => Promise<unknown>, success: string) {
    setError(null); setMessage(null);
    try { await action(); setMessage(success); await refresh(); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function exportReport(id: string) {
    setError(null);
    try { await downloadReport(`/api/investigations/${id}/report/pdf`, `imagetrace-${id.slice(0, 12)}.pdf`); }
    catch (err) { setError(err instanceof Error ? err.message : String(err)); }
  }

  async function submitIndex() {
    if (!indexFile && !indexUrl.trim()) return;
    const form = new FormData();
    if (indexFile) form.append('file', indexFile);
    if (indexUrl.trim()) form.append('image_url', indexUrl.trim());
    form.append('label', indexLabel.trim() || indexFile?.name || 'Imagen permitida');
    form.append('retention_hours', String(prefs.retentionHours));
    await act(() => addIndex(form), t('history.addIndex'));
    setIndexFile(null); setIndexUrl(''); setIndexLabel('');
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{t('history.title')}</h1>
          <p className="muted mt-1">{t('history.subtitle')}</p>
        </div>
        <button onClick={() => void refresh()} className="btn-ghost"><RefreshCw size={15} />{t('analysis.refresh')}</button>
      </div>

      <ErrorBox message={error} />
      {message && <div className="rounded-xl border border-aqua-400/30 bg-aqua-400/10 px-4 py-3 text-sm text-aqua-300"><ShieldCheck size={14} className="mr-2 inline" />{message}</div>}

      <Panel title={t('history.items', { count: items.length })} icon={<HistoryIcon size={18} />} subtitle={t('history.historyNote')}>
        {loading ? <Spinner label={t('common.loading')} /> : items.length === 0 ? (
          <EmptyState title={t('history.empty')} body={t('history.emptyBody')} icon={<FileImage size={22} />} />
        ) : (
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {items.map((item) => (
              <article key={item.id} className="card card-hover overflow-hidden">
                <div className="flex h-36 items-center justify-center border-b border-white/8 bg-ink-950/70">
                  <img src={item.thumbnail_url} alt="" loading="lazy" className="h-full w-full object-contain" />
                </div>
                <div className="space-y-3 p-4">
                  <div className="flex items-start justify-between gap-2"><h3 className="truncate text-sm font-semibold text-white">{item.original_filename || item.source_url || item.id.slice(0, 12)}</h3><StatusBadge status={item.status} /></div>
                  <div className="grid grid-cols-2 gap-2">
                    <KeyValue label={t('history.created')} value={formatDate(item.created_at, lang)} />
                    <KeyValue label={t('history.matches')} value={`${item.verified_matches} / ${item.total_matches}`} />
                    <KeyValue label={t('history.expires')} value={formatDate(item.expires_at, lang)} />
                    <KeyValue label="SHA-256" value={<span className="font-mono text-xs">{item.sha256.slice(0, 12)}…</span>} />
                  </div>
                  <div className="flex flex-wrap gap-2">
                    <Link to={`/results/${item.id}`} className="btn-ghost flex-1"><ExternalLink size={14} />{t('history.open')}</Link>
                    <button onClick={() => void exportReport(item.id)} className="btn-ghost" title={t('history.export')}><Download size={14} /></button>
                    <button onClick={() => { if (window.confirm(t('history.deleteConfirm'))) void act(() => deleteInvestigation(item.id), t('common.delete')); }} className="btn-danger" title={t('common.delete')}><Trash2 size={14} /></button>
                  </div>
                </div>
              </article>
            ))}
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t('history.privacyTitle')} icon={<LockKeyhole size={18} />} subtitle={t('history.privacyBody')}>
          <div className="space-y-4">
            <div>
              <label className="label">{t('history.token')}</label>
              <div className="flex items-center gap-2">
                <code className="mono flex-1 truncate rounded-xl border border-white/10 bg-ink-950/60 px-3 py-2.5">{maskedToken()}</code>
                <button onClick={() => { void navigator.clipboard.writeText(getOwnerToken()); setCopied(true); }} className="btn-ghost"><Copy size={14} />{copied ? t('common.copied') : t('common.copy')}</button>
              </div>
              <p className="muted mt-2 text-xs">{t('history.tokenHelp')}</p>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              <KeyValue label={t('history.retentionNote', { hours: prefs.retentionHours })} value={`${prefs.retentionHours} h`} />
              <KeyValue label={t('home.allowExternal')} value={prefs.allowExternal ? '✓' : '✕'} />
              <KeyValue label={t('home.allowGps')} value={prefs.allowGps ? '✓' : '✕'} />
              <KeyValue label={t('header.lang')} value={prefs.lang.toUpperCase()} />
            </div>
            <div>
              <label className="label">{t('history.privacyDefaults')}</label>
              <div className="flex flex-wrap items-center gap-3">
                <select value={prefs.retentionHours} onChange={(e) => setPrefs({ ...prefs, retentionHours: Number(e.target.value) })} className="input w-auto">
                  {[1, 6, 12, 24, 48, 72, 168].map((hours) => <option key={hours} value={hours}>{hours} h</option>)}
                </select>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={prefs.allowExternal} onChange={(e) => setPrefs({ ...prefs, allowExternal: e.target.checked })} className="h-4 w-4 accent-aqua-400" />{t('home.allowExternal')}</label>
                <label className="flex cursor-pointer items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={prefs.allowGps} onChange={(e) => setPrefs({ ...prefs, allowGps: e.target.checked })} className="h-4 w-4 accent-aqua-400" />{t('home.allowGps')}</label>
              </div>
              <p className="muted mt-2 text-xs">{t('history.defaultsSaved')}</p>
            </div>
            <div className="flex flex-wrap gap-2">
              <button onClick={() => { if (window.confirm(t('history.privacyBody'))) { resetOwnerToken(); void refresh(); setMessage(t('history.regenerateToken')); } }} className="btn-ghost"><KeyRound size={15} />{t('history.regenerateToken')}</button>
              <button onClick={() => void act(() => purgeExpired(), t('history.purge'))} className="btn-ghost"><RefreshCw size={15} />{t('history.purge')}</button>
              <button onClick={() => { if (window.confirm(t('history.deleteAllConfirm'))) void act(() => deleteAllData(), t('history.deleteAll')); }} className="btn-danger"><Trash2 size={15} />{t('history.deleteAll')}</button>
            </div>
          </div>
        </Panel>

        <Panel title={t('history.indexTitle')} icon={<Database size={18} />} subtitle={t('history.indexBody')}>
          <div className="space-y-3">
            <div className="grid gap-2 sm:grid-cols-2">
              <div><label className="label">{t('history.indexLabel')}</label><input value={indexLabel} onChange={(e) => setIndexLabel(e.target.value)} className="input" placeholder="ej. campaña 2024" /></div>
              <div><label className="label">{t('home.urlTab')}</label><input value={indexUrl} onChange={(e) => setIndexUrl(e.target.value)} className="input" placeholder={t('history.indexUrlPlaceholder')} /></div>
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <input type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" onChange={(e) => setIndexFile(e.target.files?.[0] || null)} className="block w-full max-w-xs text-xs text-slate-400 file:mr-3 file:rounded-lg file:border file:border-white/15 file:bg-white/5 file:px-3 file:py-2 file:text-xs file:text-slate-200" />
              <button onClick={() => void submitIndex()} disabled={!indexFile && !indexUrl.trim()} className="btn-primary"><FileImage size={15} />{t('history.addIndex')}</button>
            </div>
            {indexItems.length ? (
              <div className="max-h-64 space-y-2 overflow-y-auto pr-1 scroll-slim">
                {indexItems.map((entry) => (
                  <div key={entry.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2">
                    <div className="min-w-0"><p className="truncate text-xs font-medium text-white">{entry.label}</p><p className="mono mt-0.5 truncate text-[10px] text-slate-500">{entry.sha256.slice(0, 20)}… · {formatDate(entry.created_at, lang)}</p></div>
                    <button onClick={() => void act(() => deleteIndexEntry(entry.id), t('common.delete'))} className="text-slate-500 transition hover:text-signal-rose" title={t('common.delete')}><Trash2 size={14} /></button>
                  </div>
                ))}
              </div>
            ) : <p className="muted text-xs">{t('history.indexEmpty')}</p>}
          </div>
        </Panel>
      </div>
    </div>
  );
}
