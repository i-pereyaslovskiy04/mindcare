import { useState, useEffect, useCallback } from 'react';
import { getStudentTestResults, getStaffTestResult } from '../../../api/tests.api';
import styles from './StudentTestResults.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function pct(score, max) {
  if (score == null || !max) return null;
  return Math.round((score / max) * 100);
}

/** Тело результата: итог/шкалы/интерпретации (тот же состав, что ResultDetailPage). */
function ResultBody({ result }) {
  const overall = pct(result.total_score, result.max_possible);
  return (
    <div className={styles.body}>
      {result.total_score != null && (
        <div className={styles.scoreLine}>
          <span className={styles.scoreLabel}>Итоговый балл</span>
          <span className={styles.scoreVal}>
            {result.total_score}
            {result.max_possible != null && <span className={styles.scoreMax}> / {result.max_possible}</span>}
            {overall != null && <span className={styles.pct}> ({overall}%)</span>}
          </span>
        </div>
      )}
      {result.recommendations && <p className={styles.rec}>{result.recommendations}</p>}
      {result.scales?.length > 0 && (
        <ul className={styles.scales}>
          {result.scales.map((s) => (
            <li key={s.scale_name} className={styles.scale}>
              <span className={styles.scaleName}>{s.scale_name}</span>
              <span className={styles.scaleScore}>
                {s.score}{s.max_score != null && ` / ${s.max_score}`}
              </span>
              {s.label && <span className={styles.scaleTag}>{s.label}</span>}
              {s.interpretation && <p className={styles.rec}>{s.interpretation}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/**
 * Результаты психодиагностики студента для staff (Этап E). Список — metadata;
 * раскрытие строки грузит полный результат (на бэке пишется audit content-read).
 * activeRole → заголовок X-Active-Role (для multi-role staff).
 */
export default function StudentTestResults({ studentUuid, activeRole }) {
  const [items, setItems] = useState(null);
  const [error, setError] = useState(null);
  const [openUuid, setOpenUuid] = useState(null);
  const [detail, setDetail] = useState(null);
  const [detailErr, setDetailErr] = useState(null);

  useEffect(() => {
    if (!studentUuid) return undefined;
    let alive = true;
    setItems(null);
    setError(null);
    getStudentTestResults(studentUuid, activeRole)
      .then((r) => { if (alive) setItems(r.items); })
      .catch((e) => { if (alive) setError(e.message); });
    return () => { alive = false; };
  }, [studentUuid, activeRole]);

  const openDetail = useCallback(async (uuid) => {
    if (openUuid === uuid) { setOpenUuid(null); setDetail(null); return; }
    setOpenUuid(uuid);
    setDetail(null);
    setDetailErr(null);
    try {
      const d = await getStaffTestResult(uuid, activeRole);
      setDetail(d);
    } catch (e) {
      setDetailErr(e.message || 'Не удалось загрузить результат');
    }
  }, [openUuid, activeRole]);

  if (error) return <p className={styles.muted}>Не удалось загрузить результаты: {error}</p>;
  if (items == null) return <p className={styles.muted}>Загрузка…</p>;
  if (items.length === 0) return <p className={styles.muted}>Пройденных тестов нет.</p>;

  return (
    <ul className={styles.list}>
      {items.map((it) => (
        <li key={it.uuid} className={styles.item}>
          <button
            type="button"
            className={styles.row}
            onClick={() => openDetail(it.uuid)}
            aria-expanded={openUuid === it.uuid}
          >
            <span className={styles.title}>{it.test_title || 'Тест'}</span>
            <span className={styles.date}>{formatDate(it.submitted_at)}</span>
          </button>
          {openUuid === it.uuid && (
            <div className={styles.detail}>
              {detailErr && <p className={styles.muted}>{detailErr}</p>}
              {!detail && !detailErr && <p className={styles.muted}>Загрузка…</p>}
              {detail && <ResultBody result={detail} />}
            </div>
          )}
        </li>
      ))}
    </ul>
  );
}
