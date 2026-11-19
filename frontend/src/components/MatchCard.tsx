import { CalendarDays, ExternalLink, ImageOff, Info, Link2, ShieldQuestion } from 'lucide-react';
import { useI18n } from '../i18n';
import type { Match } from '../types';
import { EvidenceBadge, formatDate } from './ui';

function isInternal(url: string | null): boolean {
  return !!url && (url.startsWith('/') || url.startsWith('internal://'));
}

export default function MatchCard({ match }: { match: Match }) {
  const { t, lang } = useI18n();
  const matchLabel = t(`match.${match.match_type}`) === `match.${match.match_type}` ? match.match_type : t(`match.${match.match_type}`);
  const source = match.source_url;
  const canLink = !!source && !source.startsWith('internal://');
  return (
    <article className="card card-hover overflow-hidden">
      <div className="relative flex h-40 items-center justify-center border-b border-white/8 bg-ink-950/70">
        {match.thumbnail_url_signed ? (
          <img src={match.thumbnail_url_signed} alt={match.title || ''} loading="lazy" className="h-full w-full object-contain" />
        ) : (
          <div className="flex flex-col items-center gap-2 text-slate-600">
            <ImageOff size={26} /><span className="text-[11px]">{t('common.noData')}</span>
          </div>
        )}
        <div className="absolute left-3 top-3"><EvidenceBadge level={match.evidence_level} /></div>
      </div>
      <div className="space-y-3 p-4">
        <div>
          <h3 className="line-clamp-2 text-sm font-semibold text-white">{match.title || providerName(match.provider, t)}</h3>
          <p className="mt-1 flex items-center gap-1.5 text-xs text-slate-400"><Link2 size={12} />{match.domain || t('common.unknown')} · {providerName(match.provider, t)}</p>
        </div>
        <div className="grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-lg border border-white/8 bg-ink-950/50 px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('common.date')}</div>
            <div className="mt-1 flex items-center gap-1 text-slate-300"><CalendarDays size={12} />{match.published_at ? formatDate(match.published_at, lang) : t('match.noDate')}</div>
          </div>
          <div className="rounded-lg border border-white/8 bg-ink-950/50 px-2.5 py-2">
            <div className="text-[10px] uppercase tracking-wider text-slate-500">{t('common.similarity')}</div>
            <div className="mt-1 font-mono text-aqua-300">{match.similarity !== null ? `${match.similarity}%` : '—'}<span className="ml-1 text-[10px] text-slate-500">δ {match.phash_distance ?? '—'}</span></div>
          </div>
        </div>
        <div className="flex flex-wrap gap-1.5">
          <span className="chip chip-muted">{matchLabel}</span>
          {match.sha256_match && <span className="chip chip-verified">SHA-256 =</span>}
          {match.license && <span className="chip chip-muted">{match.license}</span>}
        </div>
        <details className="group rounded-xl border border-white/8 bg-ink-950/40 px-3 py-2 text-xs text-slate-400">
          <summary className="flex cursor-pointer list-none items-center gap-1.5 font-medium text-slate-300"><Info size={12} />{t('match.metric')}</summary>
          <p className="mt-2 leading-relaxed">{match.metric_explanation || t('match.metric')}</p>
          {match.published_at_note && <p className="mt-2 leading-relaxed text-signal-amber/90">{match.published_at_note}</p>}
          {match.notes && <p className="mt-2 leading-relaxed">{match.notes}</p>}
        </details>
        {canLink ? (
          <a href={source as string} target={isInternal(source) ? undefined : '_blank'} rel="noreferrer" className="btn-ghost w-full">
            <ExternalLink size={14} />{t('match.checkSource')}
          </a>
        ) : (
          <span className="inline-flex w-full items-center justify-center gap-2 rounded-xl border border-white/8 px-4 py-2.5 text-xs text-slate-500">
            <ShieldQuestion size={14} />{source || t('common.unknown')}
          </span>
        )}
      </div>
    </article>
  );
}

function providerName(name: string, t: (key: string) => string): string {
  const key = `provider.${name}`;
  const translated = t(key);
  return translated === key ? name : translated;
}
