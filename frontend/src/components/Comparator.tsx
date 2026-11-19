import { useEffect, useRef, useState } from 'react';
import { Columns2, GitCompareArrows, ImagePlus, Layers3, SlidersHorizontal, UploadCloud } from 'lucide-react';
import { compareImages } from '../api';
import { useI18n } from '../i18n';
import type { Comparison, Investigation } from '../types';
import { ErrorBox, KeyValue, Panel, shortHash } from './ui';

type Mode = 'side' | 'slider' | 'overlay' | 'diff';

export default function Comparator({ investigation }: { investigation: Investigation }) {
  const { t } = useI18n();
  const [comparison, setComparison] = useState<Comparison | null>(investigation.comparison);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [mode, setMode] = useState<Mode>('side');
  const [position, setPosition] = useState(50);
  const [opacity, setOpacity] = useState(50);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => { setComparison(investigation.comparison); }, [investigation.comparison]);
  useEffect(() => {
    if (!file) { setPreview(null); return; }
    const url = URL.createObjectURL(file);
    setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);

  async function runCompare() {
    if (!file) return;
    setBusy(true); setError(null);
    try {
      const result = await compareImages(investigation.id, file);
      setComparison(result);
      setMode('side');
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally { setBusy(false); }
  }

  const modes: { id: Mode; label: string; icon: typeof Columns2 }[] = [
    { id: 'side', label: t('compare.sideBySide'), icon: Columns2 },
    { id: 'slider', label: t('compare.slider'), icon: SlidersHorizontal },
    { id: 'overlay', label: t('compare.overlay'), icon: Layers3 },
    { id: 'diff', label: t('compare.diff'), icon: GitCompareArrows },
  ];
  const baseWidth = comparison?.dimensions.a[0] || 1;
  const baseHeight = comparison?.dimensions.a[1] || 1;
  const heatmap = comparison?.diff_url || investigation.diff_url;

  return (
    <Panel title={t('compare.title')} subtitle={t('compare.subtitle')} icon={<GitCompareArrows size={18} />}>
      <div className="flex flex-wrap items-center gap-3 rounded-xl border border-white/10 bg-ink-950/50 p-3">
        <input ref={inputRef} type="file" accept=".jpg,.jpeg,.png,.webp,image/jpeg,image/png,image/webp" className="hidden"
          onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button onClick={() => inputRef.current?.click()} className="btn-ghost">
          <ImagePlus size={15} />{file ? file.name : t('compare.uploadSecond')}
        </button>
        <button onClick={runCompare} disabled={!file || busy} className="btn-primary">
          <UploadCloud size={16} />{busy ? t('compare.comparing') : t('compare.compare')}
        </button>
        {comparison && <button onClick={() => { setComparison(null); setFile(null); if (inputRef.current) inputRef.current.value = ''; }} className="btn-ghost">{t('compare.reset')}</button>}
      </div>
      <ErrorBox message={error} />

      {!comparison ? (
        <p className="muted mt-5">{t('compare.noComparison')}</p>
      ) : (
        <div className="mt-5 space-y-5">
          <div className="flex flex-wrap gap-2">
            {modes.map((item) => (
              <button key={item.id} onClick={() => setMode(item.id)}
                className={`inline-flex items-center gap-1.5 rounded-lg border px-3 py-2 text-xs font-medium transition ${mode === item.id ? 'border-aqua-400/50 bg-aqua-400/12 text-aqua-300' : 'border-white/10 bg-white/5 text-slate-400 hover:text-white'}`}>
                <item.icon size={14} />{item.label}
              </button>
            ))}
          </div>

          {mode === 'side' && preview && (
            <div className="grid gap-3 sm:grid-cols-2">
              <figure><div className="flex h-56 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-ink-950"><img src={investigation.display_url} alt={t('compare.base')} className="h-full w-full object-contain" /></div><figcaption className="mt-2 text-center text-xs text-slate-400">{t('compare.base')}</figcaption></figure>
              <figure><div className="flex h-56 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-ink-950"><img src={preview} alt={t('compare.candidate')} className="h-full w-full object-contain" /></div><figcaption className="mt-2 text-center text-xs text-slate-400">{t('compare.candidate')}</figcaption></figure>
            </div>
          )}

          {mode === 'slider' && preview && (
            <div>
              <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-white/10 bg-ink-950">
                <img src={investigation.display_url} alt={t('compare.base')} className="absolute inset-0 h-full w-full object-contain" />
                <img src={preview} alt={t('compare.candidate')} className="absolute inset-0 h-full w-full object-contain" style={{ clipPath: `inset(0 ${100 - position}% 0 0)` }} />
                <div className="pointer-events-none absolute inset-y-0 w-0.5 bg-aqua-300 shadow-[0_0_12px_rgba(52,214,200,0.8)]" style={{ left: `${position}%` }} />
              </div>
              <label className="label mt-3">{t('compare.position')}</label>
              <input type="range" min={0} max={100} value={position} onChange={(e) => setPosition(Number(e.target.value))} className="w-full" />
            </div>
          )}

          {mode === 'overlay' && preview && (
            <div>
              <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-white/10 bg-ink-950">
                <img src={investigation.display_url} alt={t('compare.base')} className="absolute inset-0 h-full w-full object-contain" />
                <img src={preview} alt={t('compare.candidate')} className="absolute inset-0 h-full w-full object-contain" style={{ opacity: opacity / 100 }} />
              </div>
              <label className="label mt-3">{t('compare.opacity')} · {opacity}%</label>
              <input type="range" min={0} max={100} value={opacity} onChange={(e) => setOpacity(Number(e.target.value))} className="w-full" />
            </div>
          )}

          {mode === 'diff' && (
            <div className="grid gap-3 lg:grid-cols-2">
              <div>
                <div className="relative aspect-[4/3] w-full overflow-hidden rounded-xl border border-white/10 bg-ink-950">
                  <img src={investigation.display_url} alt={t('compare.base')} className="absolute inset-0 h-full w-full object-contain" />
                  {comparison.pixels.changed_regions.map((region, index) => (
                    <div key={index} className="pointer-events-none absolute border-2 border-aqua-300/80 bg-aqua-300/10"
                      style={{
                        left: `${(region.x / baseWidth) * 100}%`, top: `${(region.y / baseHeight) * 100}%`,
                        width: `${(region.width / baseWidth) * 100}%`, height: `${(region.height / baseHeight) * 100}%`,
                      }} />
                  ))}
                </div>
                <p className="muted mt-2 text-xs">{t('compare.regions')} ({comparison.pixels.changed_regions.length})</p>
              </div>
              <div>
                <div className="flex aspect-[4/3] w-full items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-ink-950">
                  {heatmap ? <img src={heatmap} alt="heatmap" className="h-full w-full object-contain" /> : <span className="text-xs text-slate-500">{t('common.noData')}</span>}
                </div>
                <p className="muted mt-2 text-xs">{t('compare.heatmapHint')}</p>
              </div>
            </div>
          )}

          <div>
            <h3 className="mb-3 text-sm font-semibold text-white">{t('compare.hashes')}</h3>
            <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
              <KeyValue label="SHA-256 A" value={shortHash(comparison.sha256.a, 20)} mono />
              <KeyValue label="SHA-256 B" value={shortHash(comparison.sha256.b, 20)} mono />
              <KeyValue label={t('compare.shaEqual')} value={comparison.sha256.equal ? '✓' : '✕'} />
              <KeyValue label={t('compare.distance')} value={`${comparison.phash.distance ?? '—'} / ${comparison.phash.bits}`} mono />
              <KeyValue label={t('compare.similarity')} value={`${comparison.phash.similarity_pct ?? '—'}%`} />
              <KeyValue label={t('compare.changedPct')} value={`${comparison.pixels.changed_pct}%`} />
              <KeyValue label={t('compare.sizeChange')} value={comparison.dimensions.size_change ? `${comparison.dimensions.a.join('×')} → ${comparison.dimensions.b.join('×')}` : '—'} />
              <KeyValue label={t('compare.crop')} value={`${comparison.crop_detection.status}${comparison.scale_estimate ? ` · ×${comparison.scale_estimate}` : ''}`} />
              <KeyValue label={t('compare.quantization')} value={comparison.compression.quantization_equal === null ? '—' : comparison.compression.quantization_equal ? '✓' : '✕'} />
            </div>
            <div className="mt-3 rounded-xl border border-white/8 bg-ink-950/50 p-3 text-xs leading-relaxed text-slate-400">
              <p>{comparison.phash.metric}</p>
              <p className="mt-1">{comparison.crop_detection.note}</p>
              <p className="mt-1">{comparison.compression.note}</p>
            </div>
            <p className="muted mt-3 text-xs text-signal-amber/90">{t('compare.disclaimer')}</p>
          </div>
        </div>
      )}
    </Panel>
  );
}
