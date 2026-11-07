import { useId, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import useCampaignStatistics from '../hooks/useCampaignStatistics';
import styles from './CampaignStatistics.module.css';

const pct = (value) => `${String(value).replace('.', ',')}%`;

function formatDay(iso) {
  const [y, m, d] = iso.split('-').map(Number);
  return new Date(Date.UTC(y, m - 1, d)).toLocaleDateString('ru-RU', {
    timeZone: 'UTC', day: 'numeric', month: 'short',
  });
}

/** Распределение баллов шкалы: столбцы одной серии, значения подписаны. */
function Histogram({ scale }) {
  const max = Math.max(1, ...scale.bins.map((b) => b.count));
  return (
    <figure className={styles.histogram}>
      <figcaption className={styles.caption}>{scale.label}</figcaption>
      <div className={styles.bars} role="img"
        aria-label={`${scale.label}: ${scale.bins.map((b) => `${b.score} баллов — ${b.count}`).join('; ')}`}>
        {scale.bins.map((b) => (
          <div key={b.score} className={styles.col} title={`${b.score} баллов: ${b.count}`}>
            <span className={styles.colValue}>{b.count || ''}</span>
            <span className={styles.colBar} style={{ height: `${(b.count / max) * 100}%` }} />
            <span className={styles.colScore}>{b.score}</span>
          </div>
        ))}
      </div>
    </figure>
  );
}

/**
 * Статистика кампании без ФИО: прохождения по дням, ответы по вопросам (число
 * и доля по вариантам), распределение баллов шкал. Если участников меньше
 * порога — распределения не показываются (защита от узнавания).
 */
export default function CampaignStatistics({ campaignUuid, filters }) {
  const id = useId();
  const { data, loading, error, refetch } = useCampaignStatistics(campaignUuid, filters, true);
  const [query, setQuery] = useState('');

  if (error) {
    return (
      <div className={styles.wrap}>
        <p className={styles.error} role="alert">{error}</p>
        <Button type="button" variant="secondary" onClick={refetch}>Повторить</Button>
      </div>
    );
  }
  if (!data) return <p className={styles.muted} role="status">Загрузка статистики…</p>;

  const q = query.trim().toLowerCase();
  const questions = data.questions.filter((item) => !q
    || String(item.number) === q || item.text.toLowerCase().includes(q));

  return (
    <div className={styles.wrap} aria-busy={loading}>
      <section aria-labelledby={`${id}-days`}>
        <h4 id={`${id}-days`} className={styles.heading}>Прохождения по дням</h4>
        {data.by_day.length ? (
          <table className={styles.table}>
            <thead><tr><th scope="col">Дата</th><th scope="col">Прошли</th></tr></thead>
            <tbody>
              {data.by_day.map((d) => (
                <tr key={d.date}><th scope="row">{formatDay(d.date)}</th><td>{d.count}</td></tr>
              ))}
            </tbody>
          </table>
        ) : <p className={styles.muted}>Нет прохождений.</p>}
      </section>

      {data.too_few ? (
        <p className={styles.notice}>
          Участников в выбранной группе: {data.total}. Распределения ответов и баллов
          показываются от {data.min_group} человек, чтобы по ним нельзя было узнать
          конкретного участника.
        </p>
      ) : (
        <>
          <section aria-labelledby={`${id}-scales`}>
            <h4 id={`${id}-scales`} className={styles.heading}>Распределение баллов по шкалам</h4>
            <div className={styles.histograms}>
              {data.scales.map((s) => <Histogram key={s.scale} scale={s} />)}
            </div>
          </section>

          <section aria-labelledby={`${id}-questions`}>
            <h4 id={`${id}-questions`} className={styles.heading}>Ответы по вопросам</h4>
            <label className={styles.searchLabel} htmlFor={`${id}-q`}>Найти вопрос (номер или текст)</label>
            <input id={`${id}-q`} className={styles.search} type="search" value={query}
              onChange={(e) => setQuery(e.target.value)} />
            <ol className={styles.questions}>
              {questions.map((item) => (
                <li key={item.number} className={styles.question}>
                  <p className={styles.qText}>
                    <span className={styles.qNum}>{item.number}.</span> {item.text}
                    <span className={styles.muted}> · ответили {item.answered}</span>
                  </p>
                  <table className={styles.options}>
                    <tbody>
                      {item.options.map((o) => (
                        <tr key={o.text} title={`${o.text}: ${o.count} (${pct(o.percent)})`}>
                          <th scope="row">{o.text}</th>
                          <td className={styles.barCell}>
                            <span className={styles.bar} style={{ width: `${o.percent}%` }} />
                          </td>
                          <td className={styles.num}>{o.count}</td>
                          <td className={styles.num}>{pct(o.percent)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </li>
              ))}
            </ol>
            {!questions.length && <p className={styles.muted}>Вопросы не найдены.</p>}
          </section>
        </>
      )}
    </div>
  );
}
