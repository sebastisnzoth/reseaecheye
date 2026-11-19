import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import {
  ArrowLeft, Binary, Check, Download, ExternalLink, FileJson2, FileText, Fingerprint,
  Globe2, HardDrive, Image as ImageIcon, Info, MapPin, ScanLine, Search, ShieldQuestion,
  Sparkles, Type,
} from 'lucide-react';
import { downloadReport } from '../api';
import MatchCard from '../components/MatchCard';
import { EmptyState, ErrorBox, KeyValue, Panel, ProgressBar, Spinner, StatusBadge, formatBytes, providerLabel } from '../components/ui';
import { useInvestigationData } from '../hooks';
import { useI18n } from '../i18n';

const STAGES = ['validation', 'hashes', 'metadata', 'forensics', 'ocr', 'providers', 'report', 'done'];

export default function Analysis() {
  const { id } = useParams<{ id: string }>();
  const { t, lang } = useI18n();
  const { data, error, loading, reload } = useInvestigationData(id);
  const [actionError, setActionError] = useState<string | null>(null);

  async function download(format: 'json' | 'pdf') {
    if (!data) return;
    setActionError(null);
    try {
      await downloadReport(`/api/investigations/${data.id}/report/${format}`, `imagetrace-${data.id.slice(0, 12)}.${format}`);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }

  if (loading && !data) return <Spinner label={t('common.loading')} />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!data) return <EmptyState title={t('common.noData')} body={error || ''} />;

  const stageIndex = Math.max(0, STAGES.indexOf(data.stage === 'error' ? 'report' : data.stage));
  const verified = data.matches.filter((m) => m.evidence_level === 'verified_exact');
  const visual = data.matches.filter((m) => m.evidence_level === 'verified_visual');
  const unverified = data.matches.filter((m) => !m.evidence_level.startsWith('verified'));
  const facts = data.metadata?.facts || [];
  const inferences = data.metadata?.inferences || [];
  const unknowns = data.metadata?.unknowns || [];
  const signals = data.forensics?.signals || [];

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to="/" className="mb-3 inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-aqua-300"><ArrowLeft size={13} />{t('common.back')}</Link>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{t('analysis.title')}</h1>
          <p className="muted mt-1">{t('analysis.subtitle')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => void reload()} className="btn-ghost"><ScanLine size={15} />{t('analysis.refresh')}</button>
          <Link to={`/results/${data.id}`} className="btn-primary"><Search size={16} />{t('analysis.openResults')}</Link>
        </div>
      </div>

      <Panel title={t('analysis.progress')} icon={<Binary size={18} />}
        actions={<StatusBadge status={data.status} />}>
        <div className="flex items-center justify-between text-xs text-slate-400">
          <span>{t(`status.${data.stage}`)}</span><span className="font-mono text-aqua-300">{data.progress}%</span>
        </div>
        <div className="mt-2"><ProgressBar value={data.progress} /></div>
        <div className="mt-5 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
          {STAGES.map((stage, index) => (
            <div key={stage} className={`flex items-center gap-2 rounded-xl border px-3 py-2 text-xs ${index < stageIndex ? 'border-aqua-400/25 bg-aqua-400/8 text-aqua-300' : index === stageIndex ? 'border-white/20 bg-white/8 text-white' : 'border-white/8 bg-ink-950/40 text-slate-500'}`}>
              <span className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-full border ${index <= stageIndex ? 'border-aqua-400/50 bg-aqua-400/15' : 'border-white/10'}`}>
                {index < stageIndex ? <Check size={12} /> : <span className="text-[9px]">{index + 1}</span>}
              </span>
              <span className="truncate">{t(`status.${stage}`)}</span>
            </div>
          ))}
        </div>
        {data.status === 'failed' && (
          <div className="mt-4 rounded-xl border border-signal-rose/30 bg-signal-rose/10 p-4 text-sm text-signal-rose">
            <p className="font-semibold">{t('analysis.failedTitle')}</p>
            <p className="mt-1 text-xs opacity-90">{t('analysis.failedBody')}</p>
            <p className="mono mt-2 break-all">{data.error}</p>
          </div>
        )}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-[0.9fr_1.1fr]">
        <Panel title={t('analysis.imageFacts')} icon={<ImageIcon size={18} />}>
          <div className="mb-4 flex h-56 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-ink-950">
            {data.display_url && <img src={data.display_url} alt={data.original_filename || 'imagen'} className="h-full w-full object-contain" />}
          </div>
          <p className="mb-4 truncate text-sm text-slate-300">{data.original_filename || data.source_url || data.id}</p>
          <div className="grid gap-2 sm:grid-cols-2">
            <KeyValue label={t('analysis.sha')} value={data.sha256} mono />
            <KeyValue label={t('analysis.phash')} value={data.phash || t('common.unknown')} mono />
            <KeyValue label={t('analysis.dimensions')} value={`${data.width} × ${data.height} px`} />
            <KeyValue label={t('analysis.size')} value={`${formatBytes(data.size_bytes)} · ${data.mime}`} />
          </div>
          <div className="mt-3 flex flex-wrap gap-1.5">
            <span className="chip chip-muted"><HardDrive size={11} />{data.source_kind}</span>
            <span className="chip chip-muted">{t('history.expires')}: {data.expires_at ? new Date(data.expires_at).toLocaleDateString(lang === 'pt' ? 'pt-BR' : lang === 'es' ? 'es-ES' : 'en-GB') : '—'}</span>
          </div>
        </Panel>

        <Panel title={t('analysis.metadata')} icon={<Fingerprint size={18} />} subtitle={data.metadata?.disclaimer}>
          <div className="space-y-4">
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-aqua-300">{t('analysis.facts')}</h3>
              {facts.length ? (
                <ul className="space-y-2">{facts.map((fact, index) => (
                  <li key={`${fact.field}-${index}`} className="rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2"><span className="text-xs font-semibold text-white">{fact.field}</span><span className="chip chip-verified">{t('common.fact')}</span></div>
                    <p className="mt-1 break-words text-sm text-slate-300">{fact.value}</p>
                    {fact.note && <p className="mt-1 text-[11px] leading-relaxed text-slate-500">{fact.note}</p>}
                  </li>
                ))}</ul>
              ) : <p className="muted">{t('common.noData')}</p>}
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-signal-violet">{t('analysis.inferences')}</h3>
              {inferences.length ? inferences.map((item, index) => <p key={index} className="muted mb-1 text-xs">• {item.value} — {item.note}</p>) : <p className="muted text-xs">{t('common.noData')}</p>}
            </div>
            <div>
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{t('analysis.unknowns')}</h3>
              <div className="flex flex-wrap gap-1.5">{unknowns.length ? unknowns.map((item, index) => <span key={index} className="chip chip-muted">{item}</span>) : <span className="chip chip-muted">{t('common.none')}</span>}</div>
            </div>
            {data.metadata?.gps_present && (
              <div className="rounded-xl border border-signal-amber/25 bg-signal-amber/8 p-3 text-xs text-signal-amber/90">
                <p className="flex items-center gap-2 font-semibold"><MapPin size={13} />{t('analysis.gps')}</p>
                {data.metadata.gps?.status === 'withheld' ? <p className="mt-1">{t('analysis.gpsWithheld')}</p> : <p className="mono mt-2 break-all">{JSON.stringify(data.metadata.gps)}</p>}
              </div>
            )}
            <p className="text-[11px] text-slate-500">ExifTool: {data.metadata?.exiftool_available ? '✓' : '—'} · GPS autorizado: {data.allow_gps ? '✓' : '—'}</p>
          </div>
        </Panel>
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t('analysis.forensics')} icon={<Sparkles size={18} />} subtitle={data.forensics?.disclaimer}>
          <div className="mb-4">
            <div className="flex items-end justify-between"><span className="text-xs uppercase tracking-wider text-slate-400">{t('analysis.score')}</span><span className="font-mono text-2xl text-aqua-300">{data.forensics?.score ?? '—'}<span className="text-sm text-slate-500">/100</span></span></div>
            <div className="mt-2"><ProgressBar value={data.forensics?.score || 0} /></div>
          </div>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-slate-400">{t('analysis.signals')}</h3>
          <div className="space-y-2">{signals.map((signal) => (
            <div key={signal.id} className="flex items-center justify-between gap-3 rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2">
              <div><p className="text-xs font-medium text-white">{signal.label}</p><p className="text-[11px] text-slate-500">{signal.status}</p></div>
              <span className="mono text-aqua-300">{signal.value}</span>
            </div>
          ))}</div>
          <div className="mt-4 rounded-xl border border-white/8 bg-ink-950/40 p-3 text-[11px] leading-relaxed text-slate-400">
            {(data.forensics?.compression?.signals || []).map((line, index) => <p key={index}>• {line}</p>)}
          </div>
          <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">{t('analysis.scene')}</h3>
          <div className="grid grid-cols-2 gap-2">
            <KeyValue label="Brillo μ / σ" value={`${data.scene?.brightness_mean ?? '—'} / ${data.scene?.brightness_std ?? '—'}`} />
            <KeyValue label="Altas luces / sombras" value={`${data.scene?.clipped_highlights_pct ?? '—'}% / ${data.scene?.clipped_shadows_pct ?? '—'}%`} />
            <KeyValue label="Regiones especulares" value={data.scene?.specular_candidate_regions ?? '—'} />
            <KeyValue label="Densidad de bordes" value={`${data.scene?.edge_density_pct ?? '—'}%`} />
          </div>
          {(data.scene?.notes || []).map((note, index) => <p key={index} className="mt-2 text-[11px] leading-relaxed text-slate-500">• {note}</p>)}
        </Panel>

        <Panel title={t('analysis.ocr')} icon={<Type size={18} />} subtitle={data.ocr?.disclaimer}>
          <div className="flex flex-wrap items-center gap-2">
            <span className="chip chip-muted">{data.ocr?.engine || t('common.unknown')}</span>
            <StatusBadge status={data.ocr?.status || 'empty'} />
          </div>
          {data.ocr?.status === 'ok' ? (
            <>
              <div className="mt-4 rounded-xl border border-white/8 bg-ink-950/50 p-4 font-mono text-sm leading-relaxed text-aqua-300">{data.ocr.text || data.ocr.lines.map((l) => l.text).join(' ')}</div>
              <h3 className="mb-2 mt-4 text-xs font-semibold uppercase tracking-wider text-slate-400">{t('analysis.ocrTerms')}</h3>
              <div className="flex flex-wrap gap-1.5">{data.ocr.terms.map((term) => <span key={term} className="chip chip-verified">{term}</span>)}</div>
              <p className="muted mt-3 text-xs">{data.ocr.message}</p>
            </>
          ) : (
            <p className="muted mt-4">{data.ocr?.status === 'unavailable' ? t('analysis.ocrUnavailable') : t('analysis.ocrEmpty')}</p>
          )}
          <div className="mt-5 rounded-xl border border-signal-amber/25 bg-signal-amber/8 p-3 text-[11px] leading-relaxed text-signal-amber/90"><Info size={13} className="mr-1 inline" />{data.ocr?.disclaimer}</div>
        </Panel>
      </div>

      <Panel title={t('analysis.sources')} icon={<Globe2 size={18} />}>
        <div className="grid gap-3 md:grid-cols-2">
          {data.provider_runs.map((run) => (
            <div key={run.id} className="rounded-xl border border-white/8 bg-ink-950/40 p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <span className="text-sm font-semibold text-white">{providerLabel(run.provider, t)}</span>
                <StatusBadge status={run.status} />
              </div>
              <p className="muted mt-2 text-xs">{run.message}</p>
              <p className="mt-2 text-[10px] text-slate-500">{run.result_count} · {run.duration_ms} ms · {run.checked_at}</p>
            </div>
          ))}
        </div>
      </Panel>

      <Panel title={t('analysis.matches')} icon={<Search size={18} />}
        actions={<span className="chip chip-muted">{t('results.verifiedCount', { count: verified.length, visual: visual.length, unverified: unverified.length })}</span>}>
        {data.matches.length ? (
          <>
            <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{data.matches.slice(0, 6).map((match) => <MatchCard key={match.id} match={match} />)}</div>
            {data.matches.length > 6 && <Link to={`/results/${data.id}`} className="btn-ghost mt-4">{t('analysis.openResults')} ({data.matches.length})</Link>}
          </>
        ) : <EmptyState title={t('results.emptyTitle')} body={t('analysis.noMatches')} icon={<ShieldQuestion size={22} />} />}
      </Panel>

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t('analysis.manual')} icon={<ExternalLink size={18} />} subtitle={t('analysis.manualNote')}>
          <div className="space-y-2">{(data.manual_links || []).map((link) => {
            const translated = (key?: string, fallback?: string) => {
              if (!key) return fallback || '';
              const value = t(key);
              return value === key ? (fallback || '') : value;
            };
            return (
              <a key={link.url} href={link.url} target="_blank" rel="noreferrer" className="flex items-start justify-between gap-3 rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2.5 transition hover:border-aqua-400/40">
                <span>
                  <span className="block text-sm font-medium text-slate-200">{translated(link.key, link.label)}</span>
                  <span className="mt-0.5 block text-[11px] text-slate-500">{translated(link.note_key, link.note)}</span>
                </span>
                <ExternalLink size={14} className="mt-1 shrink-0 text-aqua-300" />
              </a>
            );
          })}</div>
        </Panel>
        <Panel title={t('analysis.reportReady')} icon={<FileText size={18} />} subtitle={t('results.reportHint')}>
          <div className="flex flex-wrap gap-3">
            <button onClick={() => void download('json')} className="btn-ghost"><FileJson2 size={16} />{t('results.downloadJson')}</button>
            <button onClick={() => void download('pdf')} className="btn-primary"><Download size={16} />{t('results.downloadPdf')}</button>
          </div>
          <ErrorBox message={actionError} />
          <p className="muted mt-4 text-xs">{t('results.signedNote')}</p>
        </Panel>
      </div>
    </div>
  );
}
