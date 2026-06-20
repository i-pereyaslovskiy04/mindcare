import { useCallback, useEffect, useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import { getPsychologistGroupSessions } from '../../../api/appointments.api';
import styles from './AppointmentsPage.module.css';

// Moscow is UTC+3
function fmtDatetime(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  });
}

const STATUS_LABEL = {
  scheduled: 'Запланировано',
  completed: 'Завершено',
  cancelled: 'Отменено',
};
const STATUS_TONE = { scheduled: 'success', completed: 'neutral', cancelled: 'error' };
const FORMAT_LABEL = { online: 'Онлайн', in_person: 'Очно' };

const SIZE = 20;

export default function GroupSessionsPanel() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getPsychologistGroupSessions({ page: p, size: SIZE });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(page); }, [page, load]);

  const totalPages = Math.max(1, Math.ceil(total / SIZE));

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
        <div className={styles.stateTitle}>Не удалось загрузить данные</div>
        <Button variant="secondary" onClick={() => load(page)}>Повторить</Button>
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div className={styles.stateBox}>
        <Icon name="users" size={36} />
        <div className={styles.stateTitle}>Нет групповых занятий</div>
        <div className={styles.stateSub}>
          Назначенные вам групповые занятия появятся здесь.
        </div>
      </div>
    );
  }

  return (
    <>
      <div className={styles.list}>
        {items.map(gs => (
          <div key={gs.uuid} className={styles.card}>
            <div className={styles.cardHead}>
              <div className={styles.cardStudent}>
                <span className={styles.studentName}>
                  {gs.title || gs.meeting_type_name || 'Групповое занятие'}
                </span>
                {gs.meeting_type_name && gs.title && (
                  <span className={styles.studentEmail}>{gs.meeting_type_name}</span>
                )}
              </div>
              <div className={styles.cardBadges}>
                <Badge tone={STATUS_TONE[gs.status] || 'neutral'}>
                  {STATUS_LABEL[gs.status] || gs.status}
                </Badge>
                {gs.booking_enabled
                  ? <Badge tone="success">Запись открыта</Badge>
                  : <Badge tone="neutral">Запись закрыта</Badge>}
              </div>
            </div>

            {gs.description && (
              <div className={styles.cardDesc}>{gs.description}</div>
            )}

            <div className={styles.cardMeta}>
              <span className={styles.metaItem}>
                <Icon name="calendar" size={13} />
                {fmtDatetime(gs.starts_at)}
                {gs.ends_at ? ` — ${fmtDatetime(gs.ends_at)}` : ''}
              </span>
              <span className={styles.metaItem}>
                <Icon name="users" size={13} />
                {gs.registered_count} / {gs.capacity} мест
              </span>
              <span className={styles.metaItem}>
                {FORMAT_LABEL[gs.format] || gs.format}
              </span>
            </div>
          </div>
        ))}
      </div>

      {totalPages > 1 && (
        <div className={styles.pagination}>
          <Button
            type="button" variant="icon" size="sm"
            aria-label="Предыдущая страница"
            disabled={page === 1}
            onClick={() => setPage(p => p - 1)}
          >
            <Icon name="chevron-left" size={16} />
          </Button>
          <span className={styles.pageInfo}>{page} / {totalPages}</span>
          <Button
            type="button" variant="icon" size="sm"
            aria-label="Следующая страница"
            disabled={page === totalPages}
            onClick={() => setPage(p => p + 1)}
          >
            <Icon name="chevron-right" size={16} />
          </Button>
        </div>
      )}
      <div className={styles.totalHint}>Всего занятий: {total}</div>
    </>
  );
}
