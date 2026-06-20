import { useCallback, useEffect, useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import {
  getGroupSessions,
  registerGroupSession,
  cancelGroupSessionRegistration,
} from '../../../api/appointments.api';
import styles from './GroupSessionsPage.module.css';

// Moscow is UTC+3
function fmtDatetime(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleString('ru-RU', {
    timeZone: 'Europe/Moscow',
    day: 'numeric', month: 'long', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

const FORMAT_LABEL = { online: 'Онлайн', in_person: 'Очно' };

function useGroupSessions() {
  const [items, setItems]     = useState([]);
  const [total, setTotal]     = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);
  const [page, setPage]       = useState(1);

  const load = useCallback(async (p) => {
    setLoading(true);
    setError(null);
    try {
      const data = await getGroupSessions({ page: p, size: 20 });
      setItems(data.items || []);
      setTotal(data.total || 0);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { load(page); }, [page, load]);

  return { items, total, loading, error, page, setPage, refetch: () => load(page) };
}

export default function StudentGroupSessionsPage() {
  const { items, total, loading, error, page, setPage, refetch } = useGroupSessions();
  const [busy, setBusy] = useState(null); // uuid of session being acted on

  const totalPages = Math.max(1, Math.ceil(total / 20));

  async function handleRegister(gs) {
    setBusy(gs.uuid);
    try {
      await registerGroupSession(gs.uuid);
      refetch();
    } catch (e) {
      alert(e.message || 'Ошибка записи');
    } finally {
      setBusy(null);
    }
  }

  async function handleCancel(gs) {
    setBusy(gs.uuid);
    try {
      await cancelGroupSessionRegistration(gs.uuid);
      refetch();
    } catch (e) {
      alert(e.message || 'Ошибка отмены');
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Студент</div>
          <h1 className={styles.pageTitle}>Групповые <em>занятия</em></h1>
          <p className={styles.pageSub}>Запись на открытые групповые сессии.</p>
        </div>
      </div>

      {loading && <div className={styles.hint}>Загрузка…</div>}

      {!loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.stateTitle}>Ошибка загрузки</div>
          <div className={styles.stateSub}>{error}</div>
          <Button variant="secondary" type="button" onClick={refetch}>
            Повторить
          </Button>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className={styles.stateBox}>
          <Icon name="calendar" size={36} />
          <div className={styles.stateTitle}>Нет предстоящих занятий</div>
          <div className={styles.stateSub}>
            Следите за расписанием — занятия появятся здесь.
          </div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className={styles.list}>
            {items.map(gs => {
              const isBusy = busy === gs.uuid;
              const spotsLeft = gs.capacity - gs.registered_count;
              const canRegister = gs.booking_enabled && !gs.is_registered && spotsLeft > 0;
              const canCancel = gs.is_registered;

              return (
                <div key={gs.uuid} className={styles.card}>
                  <div className={styles.cardTop}>
                    <div className={styles.cardTitle}>
                      {gs.title || gs.meeting_type_name || 'Групповое занятие'}
                    </div>
                    <div className={styles.cardBadges}>
                      {gs.is_registered && (
                        <Badge tone="success">Вы записаны</Badge>
                      )}
                      {!gs.booking_enabled && (
                        <Badge tone="neutral">Запись закрыта</Badge>
                      )}
                      {gs.booking_enabled && spotsLeft === 0 && !gs.is_registered && (
                        <Badge tone="error">Мест нет</Badge>
                      )}
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
                    {gs.psychologist_name && (
                      <span className={styles.metaItem}>
                        <Icon name="bell" size={13} />
                        {gs.psychologist_name}
                      </span>
                    )}
                  </div>

                  <div className={styles.cardActions}>
                    {canRegister && (
                      <Button
                        type="button"
                        variant="primary"
                        size="sm"
                        disabled={isBusy}
                        onClick={() => handleRegister(gs)}
                      >
                        {isBusy ? '…' : 'Записаться'}
                      </Button>
                    )}
                    {canCancel && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        disabled={isBusy}
                        onClick={() => handleCancel(gs)}
                      >
                        {isBusy ? '…' : 'Отменить запись'}
                      </Button>
                    )}
                    {!gs.booking_enabled && !gs.is_registered && (
                      <span className={styles.closedHint}>
                        Запись временно закрыта
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
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
      )}
    </div>
  );
}
