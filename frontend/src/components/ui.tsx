import { AlertTriangle, CheckCircle2, CircleHelp, Loader2 } from 'lucide-react';
import type { ReactNode } from 'react';
import { useI18n } from '../i18n';

export function formatDate(value: string | null | undefined, lang: string): string {
  if (!value) return '—';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString(lang === 'pt' ? 'pt-BR' : lang === 'es' ? 'es-ES' : 'en-GB', {
    year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit',
  });
}

export function formatBytes(value: number | null | undefined): string {
  if (!value) return '—';
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / 1024 / 1024).toFixed(2)} MB`;
}

export function shortHash(value: string | null | undefined, size = 16): string {
  if (!value) return '—';
  return value.length > size * 2 ? `${value.slice(0, size)}…${value.slice(-8)}` : value;
}

export function EvidenceBadge({ level }: { level: string }) {
  const { t } = useI18n();
  const cls = level === 'verified_exact' ? 'chip chip-verified' : level === 'verified_visual' ? 'chip chip-visual' : 'chip chip-unverified';
  const key = `evidence.${level}`;
  return <span className={cls}><CheckCircle2 size={12} />{t(key)}</span>;
}

export function StatusBadge({ status }: { status: string }) {
  const { t } = useI18n();
  const cls = status === 'ok' || status === 'done' ? 'chip chip-verified'
    : status === 'unavailable' || status === 'error' || status === 'failed' ? 'chip chip-unverified'
      : 'chip chip-muted';
  const label = t(`provider.${status}`) === `provider.${status}` ? status : t(`provider.${status}`);
  return <span className={cls}>{label}</span>;
}

export function Panel({ title, subtitle, icon, children, className = '', actions }: {
  title: string; subtitle?: string; icon?: ReactNode; children: ReactNode; className?: string; actions?: ReactNode;
}) {
  return (
    <section className={`card p-5 sm:p-6 ${className}`}>
      <div className="mb-4 flex flex-wrap items-start justify-between gap-3">
        <div className="flex items-start gap-3">
          {icon && <span className="mt-0.5 rounded-lg border border-aqua-400/25 bg-aqua-400/10 p-2 text-aqua-300">{icon}</span>}
          <div>
            <h2 className="section-title">{title}</h2>
            {subtitle && <p className="muted mt-1">{subtitle}</p>}
          </div>
        </div>
        {actions}
      </div>
      {children}
    </section>
  );
}

export function KeyValue({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-white/8 bg-ink-950/50 px-3 py-2.5">
      <div className="text-[10px] font-semibold uppercase tracking-wider text-slate-500">{label}</div>
      <div className={`mt-1 break-words text-sm text-slate-200 ${mono ? 'font-mono text-xs' : ''}`}>{value}</div>
    </div>
  );
}

export function ProgressBar({ value }: { value: number }) {
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-white/8">
      <div className="h-full rounded-full bg-gradient-to-r from-aqua-600 to-aqua-300 transition-all duration-500" style={{ width: `${Math.max(0, Math.min(100, value))}%` }} />
    </div>
  );
}

export function ErrorBox({ message }: { message: string | null }) {
  if (!message) return null;
  return (
    <div className="flex items-start gap-2 rounded-xl border border-signal-rose/30 bg-signal-rose/10 px-4 py-3 text-sm text-signal-rose">
      <AlertTriangle size={16} className="mt-0.5 shrink-0" /><span>{message}</span>
    </div>
  );
}

export function EmptyState({ title, body, icon }: { title: string; body: string; icon?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-dashed border-white/12 bg-ink-950/40 px-6 py-12 text-center">
      <div className="mb-3 rounded-full border border-white/10 bg-white/5 p-3 text-slate-400">{icon || <CircleHelp size={22} />}</div>
      <h3 className="font-semibold text-white">{title}</h3>
      <p className="muted mt-2 max-w-xl">{body}</p>
    </div>
  );
}

export function Spinner({ label }: { label?: string }) {
  return <span className="inline-flex items-center gap-2 text-sm text-slate-400"><Loader2 size={16} className="animate-spin" />{label}</span>;
}

export function providerLabel(name: string, t: (key: string) => string): string {
  const key = `provider.${name}`;
  const translated = t(key);
  return translated === key ? name : translated;
}
