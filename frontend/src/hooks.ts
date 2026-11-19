import { useCallback, useEffect, useState } from 'react';
import { getInvestigation } from './api';
import type { Investigation } from './types';

export function useInvestigationData(id: string | undefined) {
  const [data, setData] = useState<Investigation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    if (!id) return;
    try {
      const response = await getInvestigation(id);
      setData(response.investigation);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, [id]);

  useEffect(() => {
    setLoading(true);
    setData(null);
    void reload();
  }, [reload]);

  const status = data?.status;
  useEffect(() => {
    if (!id || !status || (status !== 'queued' && status !== 'processing')) return;
    const timer = window.setInterval(() => { void reload(); }, 1300);
    return () => window.clearInterval(timer);
  }, [id, status, reload]);

  return { data, error, loading, reload };
}
