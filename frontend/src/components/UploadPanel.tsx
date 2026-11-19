import { useEffect, useRef, useState } from 'react';
import { FileImage, Globe2, ImagePlus, Link2, MapPin, ScanLine, ShieldCheck, Trash2, UploadCloud } from 'lucide-react';
import { createFromFile, createFromUrl, getConfig } from '../api';
import { useI18n } from '../i18n';
import type { AppConfig } from '../types';
import { ErrorBox } from './ui';

const ACCEPTED = ['image/jpeg', 'image/png', 'image/webp'];

export default function UploadPanel({ onCreated }: { onCreated: (id: string) => void }) {
  const { t, lang, prefs, setPrefs } = useI18n();
  const [mode, setMode] = useState<'file' | 'url'>('file');
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [imageUrl, setImageUrl] = useState('');
  const [keywords, setKeywords] = useState('');
  const [allowGps, setAllowGps] = useState(prefs.allowGps);
  const [allowExternal, setAllowExternal] = useState(prefs.allowExternal);
  const [retentionHours, setRetentionHours] = useState(prefs.retentionHours);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [dragging, setDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { getConfig().then(setConfig).catch(() => setConfig(null)); }, []);
  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  function selectFile(selected: File | null) {
    setError(null);
    if (!selected) { setFile(null); return; }
    const extOk = /\.(jpe?g|png|webp)$/i.test(selected.name);
    if (!ACCEPTED.includes(selected.type) && !extOk) {
      setError(lang === 'es' ? 'Formato no permitido: solo JPG, PNG o WEBP.' : lang === 'pt' ? 'Formato não permitido: apenas JPG, PNG ou WEBP.' : 'Unsupported format: JPG, PNG or WEBP only.');
      return;
    }
    if (selected.size > (config?.max_upload_mb || 15) * 1024 * 1024) {
      setError(t('home.supported', { size: config?.max_upload_mb || 15 }));
      return;
    }
    setFile(selected);
  }

  async function analyze() {
    setError(null);
    if (mode === 'file' && !file) {
      setError(lang === 'es' ? 'Seleccioná una imagen primero.' : lang === 'pt' ? 'Selecione uma imagem primeiro.' : 'Select an image first.');
      return;
    }
    if (mode === 'url' && !imageUrl.trim()) {
      setError(lang === 'es' ? 'Introducí una URL pública.' : lang === 'pt' ? 'Informe uma URL pública.' : 'Enter a public URL.');
      return;
    }
    setBusy(true);
    try {
      setPrefs({ ...prefs, lang, allowGps, allowExternal, retentionHours });
      let result: { id: string };
      if (mode === 'url') {
        result = await createFromUrl({
          image_url: imageUrl.trim(), keywords, allow_gps: allowGps, allow_external: allowExternal,
          retention_hours: retentionHours, lang,
        });
      } else {
        const form = new FormData();
        form.append('file', file as File);
        form.append('keywords', keywords);
        form.append('allow_gps', String(allowGps));
        form.append('allow_external', String(allowExternal));
        form.append('retention_hours', String(retentionHours));
        form.append('lang', lang);
        result = await createFromFile(form);
      }
      onCreated(result.id);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="card relative overflow-hidden p-5 sm:p-7">
      <div className="pointer-events-none absolute -right-20 -top-24 h-56 w-56 rounded-full bg-aqua-400/10 blur-3xl" />
      <div className="relative">
        <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
          <div>
            <h2 className="section-title">{t('home.uploadTitle')}</h2>
            <p className="muted mt-1">{t('home.supported', { size: config?.max_upload_mb || 15 })}</p>
          </div>
          <div className="flex rounded-xl border border-white/10 bg-ink-950/60 p-1">
            <button onClick={() => setMode('file')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition ${mode === 'file' ? 'bg-aqua-400 text-ink-950' : 'text-slate-400 hover:text-white'}`}>
              <FileImage size={14} />{t('home.fileTab')}
            </button>
            <button onClick={() => setMode('url')} className={`inline-flex items-center gap-2 rounded-lg px-3 py-2 text-xs font-semibold transition ${mode === 'url' ? 'bg-aqua-400 text-ink-950' : 'text-slate-400 hover:text-white'}`}>
              <Link2 size={14} />{t('home.urlTab')}
            </button>
          </div>
        </div>

        {mode === 'file' ? (
          <div>
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => { e.preventDefault(); setDragging(false); selectFile(e.dataTransfer.files?.[0] || null); }}
              onClick={() => inputRef.current?.click()}
              className={`group relative flex min-h-[220px] cursor-pointer flex-col items-center justify-center rounded-2xl border-2 border-dashed px-6 py-8 text-center transition ${dragging ? 'border-aqua-300 bg-aqua-400/10' : 'border-white/15 bg-ink-950/50 hover:border-aqua-400/50 hover:bg-aqua-400/5'}`}>
              <input ref={inputRef} type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" className="hidden" onChange={(e) => selectFile(e.target.files?.[0] || null)} />
              {preview ? (
                <div className="flex flex-col items-center gap-3">
                  <img src={preview} alt={t('home.selected')} className="max-h-36 rounded-xl border border-white/15 object-contain shadow-card" />
                  <span className="text-sm font-medium text-white">{file?.name}</span>
                  <span className="chip chip-verified"><ImagePlus size={12} />{t('home.selected')}</span>
                </div>
              ) : (
                <>
                  <span className="mb-4 rounded-2xl border border-aqua-400/25 bg-aqua-400/10 p-4 text-aqua-300 transition group-hover:scale-105">
                    <UploadCloud size={30} />
                  </span>
                  <p className="text-base font-semibold text-white">{t('home.drag')}</p>
                  <p className="muted mt-1">{t('home.dragHint')}</p>
                </>
              )}
            </div>
            {file && (
              <button onClick={(e) => { e.stopPropagation(); setFile(null); if (inputRef.current) inputRef.current.value = ''; }}
                className="mt-3 inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-signal-rose">
                <Trash2 size={13} />{t('home.remove')}
              </button>
            )}
          </div>
        ) : (
          <div className="rounded-2xl border border-white/12 bg-ink-950/50 p-6">
            <label className="label" htmlFor="image-url">{t('home.urlLabel')}</label>
            <div className="flex flex-col gap-3 sm:flex-row">
              <div className="relative flex-1">
                <Globe2 size={16} className="absolute left-3 top-3.5 text-slate-500" />
                <input id="image-url" value={imageUrl} onChange={(e) => setImageUrl(e.target.value)} placeholder={t('home.urlPlaceholder')} className="input pl-10" />
              </div>
              <div className="flex h-11 w-16 shrink-0 items-center justify-center rounded-lg border border-white/10 bg-ink-900 text-slate-500">
                <Link2 size={16} />
              </div>
            </div>
            <p className="muted mt-3 flex items-center gap-2 text-xs"><ShieldCheck size={14} className="text-aqua-300" />{t('home.urlHint')}</p>
          </div>
        )}

        <div className="mt-6 grid gap-5 lg:grid-cols-2">
          <div>
            <label className="label" htmlFor="keywords">{t('home.keywordsLabel')}</label>
            <input id="keywords" value={keywords} onChange={(e) => setKeywords(e.target.value)} placeholder={t('home.keywordsPlaceholder')} className="input" maxLength={500} />
            <p className="muted mt-2 text-xs">{t('home.keywordsHelp')}</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            <div>
              <label className="label" htmlFor="retention">{t('home.retention')}</label>
              <select id="retention" value={retentionHours} onChange={(e) => setRetentionHours(Number(e.target.value))} className="input">
                {[1, 6, 12, 24, 48, 72, 168].map((hours) => <option key={hours} value={hours}>{hours} h</option>)}
              </select>
            </div>
            <div className="flex flex-col justify-end gap-2 text-xs text-slate-400">
              <label className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" checked={allowExternal} onChange={(e) => setAllowExternal(e.target.checked)} className="h-4 w-4 rounded border-white/20 bg-ink-950 accent-aqua-400" />
                {t('home.allowExternal')}
              </label>
              <label className="flex cursor-pointer items-center gap-2">
                <input type="checkbox" checked={allowGps} onChange={(e) => setAllowGps(e.target.checked)} className="h-4 w-4 rounded border-white/20 bg-ink-950 accent-aqua-400" />
                <MapPin size={13} />{t('home.allowGps')}
              </label>
            </div>
          </div>
        </div>
        <p className="muted mt-3 text-xs">{t('home.allowGpsHelp')} · {t('home.allowExternalHelp')} · {t('home.retentionHelp')}</p>

        <ErrorBox message={error} />
        <div className="mt-6 flex flex-wrap items-center gap-3">
          <button onClick={analyze} disabled={busy} className="btn-primary min-w-[210px]">
            <ScanLine size={18} />{busy ? t('home.analyzing') : t('home.analyze')}
          </button>
          <span className="text-xs text-slate-500">{config?.honesty_notice}</span>
        </div>
      </div>
    </div>
  );
}
