import { useEffect } from 'react';
import { HashRouter, Navigate, Route, Routes, useLocation } from 'react-router-dom';
import Layout from './components/Layout';
import { I18nProvider, useI18n } from './i18n';
import Analysis from './screens/Analysis';
import History from './screens/History';
import Home from './screens/Home';
import Results from './screens/Results';
import { EmptyState } from './components/ui';

function ScrollReset() {
  const { pathname } = useLocation();
  useEffect(() => { window.scrollTo({ top: 0, behavior: 'smooth' }); }, [pathname]);
  return null;
}

function NotFound() {
  const { t } = useI18n();
  return <EmptyState title="404" body={t('common.noData')} />;
}

export default function App() {
  return (
    <I18nProvider>
      <HashRouter>
        <ScrollReset />
        <Layout>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/analysis/:id" element={<Analysis />} />
            <Route path="/results/:id" element={<Results />} />
            <Route path="/history" element={<History />} />
            <Route path="/404" element={<NotFound />} />
            <Route path="*" element={<Navigate to="/404" replace />} />
          </Routes>
        </Layout>
      </HashRouter>
    </I18nProvider>
  );
}
