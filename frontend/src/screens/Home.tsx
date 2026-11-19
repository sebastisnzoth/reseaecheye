import { useNavigate } from 'react-router-dom';
import {
  ArrowRight, Binary, Camera, CheckCircle2, FileSearch2, Fingerprint, GitCompareArrows,
  Globe2, Layers3, LockKeyhole, ScanLine, ShieldAlert, Sparkles, Type,
} from 'lucide-react';
import UploadPanel from '../components/UploadPanel';
import { useI18n } from '../i18n';

export default function Home() {
  const { t } = useI18n();
  const navigate = useNavigate();
  const capabilities = [
    { icon: Fingerprint, title: t('home.cap1Title'), body: t('home.cap1Body') },
    { icon: Camera, title: t('home.cap2Title'), body: t('home.cap2Body') },
    { icon: Type, title: t('home.cap3Title'), body: t('home.cap3Body') },
    { icon: Globe2, title: t('home.cap4Title'), body: t('home.cap4Body') },
    { icon: GitCompareArrows, title: t('home.cap5Title'), body: t('home.cap5Body') },
    { icon: FileSearch2, title: t('home.cap6Title'), body: t('home.cap6Body') },
  ];
  const steps = [
    { n: '01', title: t('home.step1'), body: t('home.step1Body'), icon: Layers3 },
    { n: '02', title: t('home.step2'), body: t('home.step2Body'), icon: Binary },
    { n: '03', title: t('home.step3'), body: t('home.step3Body'), icon: CheckCircle2 },
    { n: '04', title: t('home.step4'), body: t('home.step4Body'), icon: FileSearch2 },
  ];

  return (
    <div className="space-y-16">
      <section className="grid items-center gap-10 lg:grid-cols-[1.05fr_1fr]">
        <div className="relative">
          <span className="chip chip-verified"><Sparkles size={12} />{t('home.badge')}</span>
          <h1 className="mt-6 text-4xl font-bold leading-[1.08] tracking-tight text-white sm:text-5xl lg:text-6xl">
            {t('home.titleA')}<br /><span className="bg-gradient-to-r from-aqua-300 via-aqua-400 to-signal-violet bg-clip-text text-transparent">{t('home.titleB')}</span>
          </h1>
          <p className="muted mt-6 max-w-xl text-base">{t('home.subtitle')}</p>
          <div className="mt-6 rounded-xl border border-signal-amber/25 bg-signal-amber/8 px-4 py-3 text-sm leading-relaxed text-signal-amber/90">
            <span className="mr-2 inline-flex align-middle"><ShieldAlert size={16} /></span>{t('home.honesty')}
          </div>
          <div className="mt-7 flex flex-wrap gap-3">
            <a href="#upload" className="btn-primary"><ScanLine size={18} />{t('home.analyze')}<ArrowRight size={16} /></a>
            <a href="#capabilities" className="btn-ghost">{t('home.capsTitle')}</a>
          </div>
          <p className="muted mt-6 flex items-center gap-2 text-xs"><LockKeyhole size={14} className="text-aqua-300" />{t('home.privacyNote')}</p>
        </div>
        <div id="upload" className="scroll-mt-24"><UploadPanel onCreated={(id) => navigate(`/analysis/${id}`)} /></div>
      </section>

      <section id="capabilities" className="scroll-mt-24">
        <div className="mb-6 flex items-end justify-between gap-4">
          <h2 className="text-2xl font-bold tracking-tight text-white sm:text-3xl">{t('home.capsTitle')}</h2>
          <span className="hidden text-xs text-slate-500 sm:block">01 — 06</span>
        </div>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {capabilities.map((cap) => (
            <div key={cap.title} className="card card-hover p-5">
              <span className="mb-4 inline-flex rounded-xl border border-aqua-400/20 bg-aqua-400/8 p-2.5 text-aqua-300"><cap.icon size={19} /></span>
              <h3 className="font-semibold text-white">{cap.title}</h3>
              <p className="muted mt-2 text-sm">{cap.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section>
        <h2 className="mb-6 text-2xl font-bold tracking-tight text-white sm:text-3xl">{t('home.stepsTitle')}</h2>
        <div className="grid gap-4 md:grid-cols-4">
          {steps.map((step) => (
            <div key={step.n} className="relative card p-5">
              <span className="mono absolute right-4 top-4 text-slate-600">{step.n}</span>
              <span className="mb-4 inline-flex rounded-xl border border-white/10 bg-white/5 p-2.5 text-slate-300"><step.icon size={18} /></span>
              <h3 className="font-semibold text-white">{step.title}</h3>
              <p className="muted mt-2 text-sm">{step.body}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="card overflow-hidden p-6 sm:p-8">
        <div className="flex flex-col gap-4 md:flex-row md:items-start">
          <span className="rounded-xl border border-signal-violet/30 bg-signal-violet/10 p-3 text-signal-violet"><ShieldAlert size={22} /></span>
          <div>
            <h2 className="text-xl font-semibold text-white">{t('home.limitTitle')}</h2>
            <p className="muted mt-2 max-w-3xl">{t('home.limitBody')}</p>
          </div>
        </div>
      </section>
    </div>
  );
}
