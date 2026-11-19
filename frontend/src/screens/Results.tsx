import { useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft, CalendarClock, Copy, Download, FileJson2, FileText, Filter, Link2, ListChecks, ShieldCheck, SlidersHorizontal } from 'lucide-react';
import Comparator from '../components/Comparator';
import MatchCard from '../components/MatchCard';
import { EmptyState, ErrorBox, KeyValue, Panel, Spinner, formatDate } from '../components/ui';
import { createSignedLink, downloadReport } from '../api';
import { useInvestigationData } from '../hooks';
import { useI18n } from '../i18n';
import type { Match } from '../types';

type SortKey = 'source' | 'date' | 'similarity' | 'reliability';
const reliability = (level: string) => level === 'verified_exact' ? 3 : level === 'verified_visual' ? 2 : 1;

export default function Results() {
  const { id } = useParams<{ id: string }>();
  const { t, lang } = useI18n();
  const { data, error, loading } = useInvestigationData(id);
  const [domain, setDomain] = useState('all');
  const [evidence, setEvidence] = useState('all');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [sort, setSort] = useState<SortKey>('reliability');
  const [group, setGroup] = useState(false);
  const [signed, setSigned] = useState<{ url: string; expires_in_seconds: number } | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const matches = data?.matches || [];
  const domains = useMemo(() => Array.from(new Set(matches.map((m) => m.domain || '—'))).sort(), [matches]);
  const filtered = useMemo(() => {
    const from = dateFrom ? new Date(`${dateFrom}T00:00:00`).getTime() : null;
    const to = dateTo ? new Date(`${dateTo}T23:59:59`).getTime() : null;
    const list = matches.filter((match) => {
      if (domain !== 'all' && (match.domain || '—') !== domain) return false;
      if (evidence !== 'all' && match.evidence_level !== evidence) return false;
      if (from || to) {
        const time = match.published_at ? new Date(match.published_at).getTime() : NaN;
        if (Number.isNaN(time)) return false;
        if (from && time < from) return false;
        if (to && time > to) return false;
      }
      return true;
    });
    return [...list].sort((a, b) => {
      if (sort === 'similarity') return (b.similarity ?? -1) - (a.similarity ?? -1);
      if (sort === 'date') return (b.published_at || '').localeCompare(a.published_at || '');
      if (sort === 'source') return (a.domain || '').localeCompare(b.domain || '') || (a.provider || '').localeCompare(b.provider || '');
      return reliability(b.evidence_level) - reliability(a.evidence_level) || (b.similarity ?? -1) - (a.similarity ?? -1);
    });
  }, [matches, domain, evidence, dateFrom, dateTo, sort]);

  const grouped = useMemo(() => {
    const map = new Map<string, Match[]>();
    filtered.forEach((match) => {
      const key = `${match.domain || '—'} · ${match.provider}`;
      map.set(key, [...(map.get(key) || []), match]);
    });
    return Array.from(map.entries());
  }, [filtered]);

  async function download(format: 'json' | 'pdf') {
    if (!data) return;
    setActionError(null);
    try {
      await downloadReport(`/api/investigations/${data.id}/report/${format}`, `imagetrace-${data.id.slice(0, 12)}.${format}`);
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }

  async function makeSignedLink(format: 'pdf' | 'json') {
    if (!data) return;
    setActionError(null);
    try {
      const result = await createSignedLink(data.id, format);
      setSigned({ url: result.url, expires_in_seconds: result.expires_in_seconds });
    } catch (err) { setActionError(err instanceof Error ? err.message : String(err)); }
  }

  if (loading && !data) return <Spinner label={t('common.loading')} />;
  if (error && !data) return <ErrorBox message={error} />;
  if (!data) return <EmptyState title={t('common.noData')} body={error || ''} />;

  const report = data.report;
  const first = report?.first_known_appearance;
  const verifiedCount = report?.verified_matches.length ?? matches.filter((m) => m.evidence_level === 'verified_exact').length;
  const visualCount = report?.visual_similarities.length ?? matches.filter((m) => m.evidence_level === 'verified_visual').length;
  const unverifiedCount = report?.unverified_results.length ?? matches.filter((m) => !m.evidence_level.startsWith('verified')).length;

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <Link to={`/analysis/${data.id}`} className="mb-3 inline-flex items-center gap-1.5 text-xs text-slate-400 hover:text-aqua-300"><ArrowLeft size={13} />{t('results.backToAnalysis')}</Link>
          <h1 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{t('results.title')}</h1>
          <p className="muted mt-1">{t('results.subtitle')}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button onClick={() => void download('json')} className="btn-ghost"><FileJson2 size={16} />{t('results.downloadJson')}</button>
          <button onClick={() => void download('pdf')} className="btn-primary"><Download size={16} />{t('results.downloadPdf')}</button>
        </div>
      </div>

      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div className="card p-4"><div className="text-[10px] uppercase tracking-wider text-slate-500">{t('common.verified')}</div><div className="mt-1 text-2xl font-bold text-aqua-300">{verifiedCount}</div></div>
        <div className="card p-4"><div className="text-[10px] uppercase tracking-wider text-slate-500">{t('common.visual')}</div><div className="mt-1 text-2xl font-bold text-signal-violet">{visualCount}</div></div>
        <div className="card p-4"><div className="text-[10px] uppercase tracking-wider text-slate-500">{t('common.unverified')}</div><div className="mt-1 text-2xl font-bold text-signal-amber">{unverifiedCount}</div></div>
        <div className="card p-4"><div className="text-[10px] uppercase tracking-wider text-slate-500">{t('results.firstAppearance')}</div><div className="mt-1 text-sm font-semibold text-white">{first?.status === 'source_timestamp' && first.date ? formatDate(first.date, lang) : t('results.firstUnknown')}</div></div>
      </div>

      <Panel title={t('results.filters')} icon={<Filter size={18} />}
        actions={<span className="chip chip-muted">{t('results.resultCount', { count: filtered.length })}</span>}>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <div><label className="label">{t('results.domain')}</label><select value={domain} onChange={(e) => setDomain(e.target.value)} className="input"><option value="all">{t('common.all')}</option>{domains.map((item) => <option key={item} value={item}>{item}</option>)}</select></div>
          <div><label className="label">{t('results.evidence')}</label><select value={evidence} onChange={(e) => setEvidence(e.target.value)} className="input"><option value="all">{t('common.all')}</option><option value="verified_exact">{t('common.verified')}</option><option value="verified_visual">{t('common.visual')}</option><option value="unverified">{t('common.unverified')}</option></select></div>
          <div><label className="label">{t('results.dateFrom')}</label><input type="date" value={dateFrom} onChange={(e) => setDateFrom(e.target.value)} className="input" /></div>
          <div><label className="label">{t('results.dateTo')}</label><input type="date" value={dateTo} onChange={(e) => setDateTo(e.target.value)} className="input" /></div>
          <div><label className="label">{t('results.sort')}</label><select value={sort} onChange={(e) => setSort(e.target.value as SortKey)} className="input"><option value="reliability">{t('results.sortReliability')}</option><option value="source">{t('results.sortSource')}</option><option value="date">{t('results.sortDate')}</option><option value="similarity">{t('results.sortSimilarity')}</option></select></div>
        </div>
        <label className="mt-3 flex cursor-pointer items-center gap-2 text-xs text-slate-400"><input type="checkbox" checked={group} onChange={(e) => setGroup(e.target.checked)} className="h-4 w-4 accent-aqua-400" /><SlidersHorizontal size={13} />{t('results.groupBySource')}</label>
      </Panel>

      <Panel title={t('results.gallery')} icon={<Link2 size={18} />}
        subtitle={t('results.verifiedCount', { count: verifiedCount, visual: visualCount, unverified: unverifiedCount })}>
        {filtered.length === 0 ? (
          <EmptyState title={t('results.emptyTitle')} body={t('results.emptyBody')} />
        ) : group ? (
          <div className="space-y-6">{grouped.map(([key, items]) => (
            <div key={key}><h3 className="mb-3 flex items-center gap-2 text-sm font-semibold text-aqua-300"><ListChecks size={15} />{key} <span className="chip chip-muted">{items.length}</span></h3><div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{items.map((match) => <MatchCard key={match.id} match={match} />)}</div></div>
          ))}</div>
        ) : (
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">{filtered.map((match) => <MatchCard key={match.id} match={match} />)}</div>
        )}
      </Panel>

      <Comparator investigation={data} />

      <div className="grid gap-6 lg:grid-cols-2">
        <Panel title={t('results.reportSection')} icon={<FileText size={18} />} subtitle={t('results.reportHint')}>
          <div className="grid gap-2 sm:grid-cols-2">
            <KeyValue label={t('results.firstAppearance')} value={first?.status === 'source_timestamp' && first.date ? formatDate(first.date, lang) : t('results.firstUnknown')} />
            <KeyValue label={t('results.duplicates')} value={report?.duplicates.length ?? 0} />
            <KeyValue label={t('analysis.reportReady')} value={report?.generated_at ? formatDate(report.generated_at, lang) : t('common.noData')} />
            <KeyValue label={t('common.status')} value={data.status} />
          </div>
          {first?.status === 'source_timestamp' && <div className="mt-3 rounded-xl border border-signal-amber/20 bg-signal-amber/8 p-3 text-xs text-signal-amber/90"><CalendarClock size={13} className="mr-1 inline" />{first.note || first.reason}</div>}
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => void download('json')} className="btn-ghost"><FileJson2 size={15} />JSON</button>
            <button onClick={() => void download('pdf')} className="btn-ghost"><FileText size={15} />PDF</button>
            <button onClick={() => void makeSignedLink('pdf')} className="btn-ghost"><Link2 size={15} />{t('results.signedLink')}</button>
          </div>
          <ErrorBox message={actionError} />
          {signed && (
            <div className="mt-3 rounded-xl border border-aqua-400/25 bg-aqua-400/8 p-3">
              <div className="flex items-center justify-between gap-2 text-xs text-aqua-300"><span>{t('results.signedNote')} · {signed.expires_in_seconds}s</span><button onClick={() => { void navigator.clipboard.writeText(signed.url); setCopied(true); }} className="inline-flex items-center gap-1"><Copy size={12} />{copied ? t('common.copied') : t('common.copy')}</button></div>
              <p className="mono mt-2 break-all text-slate-300">{signed.url}</p>
            </div>
          )}
          <h3 className="mb-2 mt-5 text-xs font-semibold uppercase tracking-wider text-slate-400">{t('results.conclusions')}</h3>
          <ol className="space-y-2 text-sm text-slate-300">{(report?.conclusions || []).map((item, index) => <li key={index} className="flex gap-2"><span className="font-mono text-aqua-300">{index + 1}.</span><span>{item}</span></li>)}</ol>
        </Panel>

        <div className="space-y-6">
          <Panel title={t('results.limitations')} icon={<ShieldCheck size={18} />}>
            <ul className="space-y-2 text-sm text-slate-400">{(report?.limitations || []).map((item, index) => <li key={index} className="flex gap-2"><span className="text-signal-amber">•</span><span>{item}</span></li>)}</ul>
          </Panel>
          <Panel title={t('results.duplicates')} icon={<ListChecks size={18} />}>
            {(report?.duplicates || []).length ? (
              <ul className="space-y-2">{(report?.duplicates || []).map((item, index) => (
                <li key={index} className="flex items-center justify-between gap-3 rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2 text-xs">
                  <span className="truncate text-slate-300">{item.source_url || item.provider}</span><span className="mono text-aqua-300">{item.similarity_pct ?? '—'}%</span>
                </li>
              ))}</ul>
            ) : <p className="muted">{t('analysis.noMatches')}</p>}
          </Panel>
        </div>
      </div>
    </div>
  );
}
