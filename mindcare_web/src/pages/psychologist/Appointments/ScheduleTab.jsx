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
const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

/**
 * Read-only расписание психолога: активные рабочие окна + перерывы.
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

  return (
    <div className={styles.list}>
      {rules.map(r => (
        <div key={r.id} className={styles.card}>
          <div className={styles.cardHead}>
            <div className={styles.cardStudent}>
              <span className={styles.studentName}>{DAY_LABEL[r.day_of_week]}</span>
              <span className={styles.studentEmail}>Рабочее окно</span>
            </div>
            {r.auto_extend && <Badge tone="neutral">Автопродление</Badge>}
          </div>

          <div className={styles.cardMeta}>
            <span className={styles.metaItem}>
              <Icon name="calendar" size={13} />
              {r.start_time}–{r.end_time}
            </span>
            <span className={styles.metaItem}>
              Действует: {r.effective_from}
              {r.effective_until ? ` — ${r.effective_until}` : ' — бессрочно'}
            </span>
          </div>
        </div>
      ))}

      {breaks.length > 0 && (
        <div className={styles.card}>
          <div className={styles.cardHead}>
            <div className={styles.cardStudent}>
              <span className={styles.studentName}>Перерывы</span>
            </div>
          </div>
          <div className={styles.cardMeta}>
            {breaks.map(b => (
              <span key={b.id} className={styles.metaItem}>
                {DAY_SHORT[b.day_of_week]} {b.start_time}–{b.end_time}
                {b.title ? ` (${b.title})` : ''}
              </span>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
