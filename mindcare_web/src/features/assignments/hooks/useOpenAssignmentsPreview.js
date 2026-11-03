import { useEffect, useState } from 'react';
import { getMyAssignments } from '../../../api/assignments.api';

/**
 * Первые `limit` активных заданий клиента (view=open) для главной кабинета.
 * enabled=false (impersonation: backend отвечает 403) — запросов нет.
 */
export default function useOpenAssignmentsPreview({ enabled = true, limit = 3 } = {}) {
  const [state, setState] = useState({
    items: [], hasMore: false, loading: enabled, error: false,
  });

  useEffect(() => {
    if (!enabled) {
      setState({ items: [], hasMore: false, loading: false, error: false });
      return undefined;
    }
    let alive = true;
    setState((s) => ({ ...s, loading: true, error: false }));
    getMyAssignments({ view: 'open', size: limit })
      .then((data) => {
        if (!alive) return;
        setState({
          items: Array.isArray(data?.items) ? data.items : [],
          hasMore: Boolean(data?.has_more),
          loading: false,
          error: false,
        });
      })
      .catch(() => {
        if (alive) setState({ items: [], hasMore: false, loading: false, error: true });
      });
    return () => { alive = false; };
  }, [enabled, limit]);

  return state;
}
