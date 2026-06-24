import { useCallback, useEffect, useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import { getPsychologistSchedule } from '../../../api/appointments.api';
import styles from './AppointmentsPage.module.css';

const DAY_LABEL = [
  'Понедельник', 'Вторник', 'Среда', 'Четверг',
  'Пятница', 'Суббота', 'Воскресенье',
];

function fmtPeriod(item) {
  return `Действует: ${item.effective_from}`
    + (item.effective_until ? ` — ${item.effective_until}` : ' — бессрочно');
}

/**
 * Read-only расписание психолога, сгруппированное по дням недели: для каждого
 * дня сначала рабочие окна, затем перерывы.
 * Schedule v3: рабочее окно не привязано к типу встречи — показываем только
 * день, время и период действия (тип/длительность здесь не отображаются).
 */
export default function ScheduleTab() {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(await getPsychologistSchedule());
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(); }, [load]);

  if (loading) {
    return (
      <div className={styles.stateBox}>
        <span className={styles.loadingText}>Загрузка…</span>
      </div>
    );
  }

  if (error) {
    return (
      <div className={styles.stateBox}>
        <Icon name="bell" size={28} />
        <div className={styles.stateTitle}>Не удалось загрузить расписание</div>
        <Button variant="secondary" onClick={load}>Повторить</Button>
      </div>
    );
  }

  const rules = data?.rules || [];
  const breaks = data?.breaks || [];

  if (rules.length === 0 && breaks.length === 0) {
    return (
      <div className={styles.stateBox}>
        <Icon name="calendar" size={36} />
        <div className={styles.stateTitle}>Расписание не задано</div>
        <div className={styles.stateSub}>
          Рабочие окна назначает супервизор.
        </div>
      </div>
    );
  }

  // Группируем рабочие окна и перерывы по дню недели; показываем только дни,
  // где есть хотя бы одно окно или перерыв. Внутри дня — окна, затем перерывы,
  // и то и другое отсортировано по времени начала.
  const byTime = (a, b) => a.start_time.localeCompare(b.start_time);

  const seenRules = new Set();
  const dedupedRules = rules.filter(r => {
    const key = [r.day_of_week, r.start_time, r.end_time,
                 r.effective_from, r.effective_until, r.auto_extend, r.is_active].join('|');
    return seenRules.has(key) ? false : (seenRules.add(key), true);
  });

  const seenBreaks = new Set();
  const dedupedBreaks = breaks.filter(b => {
    const key = [b.day_of_week, b.start_time, b.end_time,
                 b.effective_from, b.effective_until, b.title ?? ''].join('|');
    return seenBreaks.has(key) ? false : (seenBreaks.add(key), true);
  });

  const days = DAY_LABEL.map((label, dow) => ({
    dow,
    label,
    rules: dedupedRules.filter(r => r.day_of_week === dow).sort(byTime),
    breaks: dedupedBreaks.filter(b => b.day_of_week === dow).sort(byTime),
  })).filter(d => d.rules.length > 0 || d.breaks.length > 0);

  return (
    <div className={styles.list}>
      {days.map(day => (
        <div key={day.dow} className={styles.card}>
          <div className={styles.cardHead}>
            <div className={styles.cardStudent}>
              <span className={styles.studentName}>{day.label}</span>
            </div>
          </div>

          {day.rules.map(r => (
            <div key={`r-${r.id}`} className={styles.cardMeta}>
              <span className={styles.metaItem}>
                <Icon name="calendar" size={13} />
                Рабочее время: {r.start_time}–{r.end_time}
              </span>
              <span className={styles.metaItem}>{fmtPeriod(r)}</span>
              {r.auto_extend && <Badge tone="neutral">Автопродление</Badge>}
            </div>
          ))}

          {day.breaks.map(b => (
            <div key={`b-${b.id}`} className={styles.cardMeta}>
              <span className={styles.metaItem}>
                <Icon name="bell" size={13} />
                Перерыв: {b.start_time}–{b.end_time}
                {b.title ? `, ${b.title}` : ''}
              </span>
              <span className={styles.metaItem}>{fmtPeriod(b)}</span>
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
