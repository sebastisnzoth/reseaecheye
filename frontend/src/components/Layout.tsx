import { Fingerprint, Github, Globe2, LockKeyhole, ScanSearch } from 'lucide-react';
import { NavLink, useLocation } from 'react-router-dom';
import type { ReactNode } from 'react';
import { useI18n } from '../i18n';
import type { Lang } from '../types';

const languages: { id: Lang; label: string }[] = [
  { id: 'es', label: 'ES' }, { id: 'pt', label: 'PT-BR' }, { id: 'en', label: 'EN' },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { lang, setLang, t } = useI18n();
  const location = useLocation();
  const navClass = ({ isActive }: { isActive: boolean }) =>
    `rounded-lg px-3 py-2 text-sm font-medium transition ${isActive ? 'bg-aqua-400/12 text-aqua-300' : 'text-slate-400 hover:bg-white/5 hover:text-slate-200'}`;

  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-30 border-b border-white/8 bg-ink-950/80 backdrop-blur-xl">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <NavLink to="/" className="group flex items-center gap-3">
            <span className="relative flex h-10 w-10 items-center justify-center rounded-xl border border-aqua-400/30 bg-aqua-400/10 text-aqua-300 shadow-glow">
              <ScanSearch size={21} />
              <span className="absolute -right-1 -top-1 h-2.5 w-2.5 animate-pulseSoft rounded-full bg-aqua-300" />
            </span>
            <span className="leading-tight">
              <span className="block text-base font-bold tracking-tight text-white">ImageTrace <span className="text-aqua-300">OSINT</span></span>
              <span className="hidden text-[11px] text-slate-500 sm:block">{t('app.tagline')}</span>
            </span>
          </NavLink>
          <nav className="order-3 flex w-full items-center gap-1 sm:order-none sm:ml-6 sm:w-auto">
            <NavLink to="/" className={navClass}>{t('nav.home')}</NavLink>
            <NavLink to="/history" className={navClass}>{t('nav.history')}</NavLink>
            <a href="https://github.com/sebastisnzoth/reseaecheye" target="_blank" rel="noreferrer" className={navClass({ isActive: false })}>
              <span className="inline-flex items-center gap-1.5"><Github size={14} />{t('nav.docs')}</span>
            </a>
          </nav>
          <div className="ml-auto flex items-center gap-2">
            <span className="hidden items-center gap-1.5 rounded-full border border-white/10 bg-white/5 px-3 py-1.5 text-[11px] text-slate-400 md:inline-flex">
              <LockKeyhole size={12} className="text-aqua-300" />{t('header.private')}
            </span>
            <div className="flex items-center gap-1 rounded-lg border border-white/10 bg-ink-900/80 p-1">
              <Globe2 size={14} className="mx-1 text-slate-500" />
              {languages.map((item) => (
                <button key={item.id} onClick={() => setLang(item.id)} aria-label={item.label}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${lang === item.id ? 'bg-aqua-400 text-ink-950' : 'text-slate-400 hover:text-white'}`}>
                  {item.label}
                </button>
              ))}
            </div>
          </div>
        </div>
        {location.pathname !== '/' && (
          <div className="h-px bg-gradient-to-r from-transparent via-aqua-400/30 to-transparent" />
        )}
      </header>

      <main className="mx-auto w-full max-w-7xl flex-1 px-4 py-8 sm:px-6 sm:py-10">{children}</main>

      <footer className="border-t border-white/8 bg-ink-950/60">
        <div className="mx-auto flex max-w-7xl flex-wrap items-center justify-between gap-3 px-4 py-5 text-xs text-slate-500 sm:px-6">
          <span className="inline-flex items-center gap-2"><Fingerprint size={14} className="text-aqua-400" />{t('footer.note')}</span>
          <span className="mono">v1.0.0 · {new Date().getFullYear()}</span>
        </div>
      </footer>
    </div>
  );
}
