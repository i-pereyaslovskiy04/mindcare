import { useState, useEffect } from 'react';
import { getHealth } from '../../api/health.api';
import styles from './HealthPage.module.css';

export default function HealthPage() {
  const [data, setData]     = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError]   = useState(null);

  useEffect(() => {
    getHealth()
      .then(setData)
      .catch((err) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className={styles.page}>
      <h1 className={styles.title}>System Health</h1>
      <p className={styles.hint}>Debug endpoint — not visible to end users.</p>

      {loading && <p className={styles.loading}>Checking…</p>}

      {error && (
        <div className={styles.card}>
          <span className={`${styles.dot} ${styles.dotError}`} />
          <span className={styles.status}>Error</span>
          <pre className={styles.detail}>{error}</pre>
        </div>
      )}

      {data && (
        <div className={styles.card}>
          <div className={styles.row}>
            <span className={`${styles.dot} ${data.status === 'ok' ? styles.dotOk : styles.dotError}`} />
            <span className={styles.label}>Status</span>
            <span className={styles.value}>{data.status}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Database</span>
            <span className={styles.value}>{data.db}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Tables</span>
            <span className={styles.value}>{data.tables}</span>
          </div>
          <div className={styles.row}>
            <span className={styles.label}>Alembic revision</span>
            <code className={styles.code}>{data.revision}</code>
          </div>
        </div>
      )}
    </div>
  );
}
