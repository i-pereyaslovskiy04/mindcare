import { useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import Modal from '../../../components/Modal/Modal';
import { usePsychologistAppointments } from '../../../features/psychologist/hooks/usePsychologistAppointments';
import { confirmAppointment, declineAppointment } from '../../../api/appointments.api';
import GroupSessionsPanel from './GroupSessionsPanel';
import ScheduleTab from './ScheduleTab';
import styles from './AppointmentsPage.module.css';

// Moscow is UTC+3
function fmtDatetime(iso) {
  if (!iso) return '—';
  const msk = new Date(new Date(iso).getTime() + 3 * 60 * 60 * 1000);
  return msk.toLocaleString('ru-RU', {
    day: 'numeric', month: 'long', hour: '2-digit', minute: '2-digit',
  });
}

const STATUS_LABEL = {
  pending_confirmation: 'Ожидает подтверждения',
  confirmed:            'Подтверждена',
  cancelled:            'Отменена студентом',
  declined:             'Отклонена',
  completed:            'Завершена',
  no_show:              'Не явился',
};
const STATUS_TONE = {
  pending_confirmation: 'warning',
  confirmed:            'success',
  cancelled:            'error',
  declined:             'error',
  completed:            'neutral',
  no_show:              'warning',
};

const MODALITY_LABEL = { online: 'Онлайн', in_person: 'Очно' };

const STATUS_FILTERS = [
  { value: '',                    label: 'Все' },
  { value: 'pending_confirmation', label: 'Ожидают' },
  { value: 'confirmed',           label: 'Подтверждённые' },
  { value: 'completed',           label: 'Завершённые' },
  { value: 'cancelled',           label: 'Отменённые' },
];

export default function PsychologistAppointmentsPage() {
  const { items, total, loading, error, page, setPage, statusFilter, setFilter, refetch } =
    usePsychologistAppointments();

  const [tab, setTab] = useState('individual');
  const [confirming, setConfirming] = useState(null);
  const [declineModal, setDeclineModal] = useState(null);
  const [declineReason, setDeclineReason] = useState('');
  const [declining, setDeclining] = useState(false);
  const [actionError, setActionError] = useState(null);

  const totalPages = Math.max(1, Math.ceil(total / 20));

  async function handleConfirm(uuid) {
    setConfirming(uuid);
    setActionError(null);
    try {
      await confirmAppointment(uuid);
      refetch();
    } catch (e) {
      setActionError(e.message || 'Ошибка подтверждения');
    } finally {
      setConfirming(null);
    }
  }

  function openDecline(uuid) {
    setDeclineReason('');
    setDeclineModal(uuid);
  }

  async function handleDecline() {
    if (!declineModal) return;
    setDeclining(true);
    setActionError(null);
    try {
      await declineAppointment(declineModal, { reason: declineReason });
      setDeclineModal(null);
      refetch();
    } catch (e) {
      setActionError(e.message || 'Ошибка отклонения');
    } finally {
      setDeclining(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Кабинет психолога</div>
          <h1 className={styles.pageTitle}><em>Сессии</em></h1>
          <p className={styles.pageSub}>Индивидуальные записи, групповые занятия и моё расписание.</p>
        </div>
      </div>

      {/* Tabs: individual / group */}
      <div className={styles.tabs} role="tablist">
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'individual'}
          className={tab === 'individual' ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab('individual')}
        >
          Индивидуальные
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'group'}
          className={tab === 'group' ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab('group')}
        >
          Групповые
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={tab === 'schedule'}
          className={tab === 'schedule' ? `${styles.tab} ${styles.tabActive}` : styles.tab}
          onClick={() => setTab('schedule')}
        >
          Моё расписание
        </button>
      </div>

      {tab === 'group' && <GroupSessionsPanel />}

      {tab === 'schedule' && <ScheduleTab />}

      {tab === 'individual' && (
      <>
      {/* Status filter chips */}
      <div className={styles.filters}>
        {STATUS_FILTERS.map(f => (
          <button
            key={f.value}
            type="button"
            aria-pressed={statusFilter === f.value}
            className={statusFilter === f.value ? `${styles.filterChip} ${styles.filterChipActive}` : styles.filterChip}
            onClick={() => setFilter(f.value)}
          >
            {f.label}
          </button>
        ))}
      </div>

      {actionError && <div className={styles.actionError}>{actionError}</div>}

      {loading && (
        <div className={styles.stateBox}>
          <span className={styles.loadingText}>Загрузка…</span>
        </div>
      )}

      {!loading && error && (
        <div className={styles.stateBox}>
          <Icon name="bell" size={28} />
          <div className={styles.stateTitle}>Не удалось загрузить данные</div>
          <Button variant="secondary" onClick={refetch}>Повторить</Button>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className={styles.stateBox}>
          <Icon name="calendar" size={36} />
          <div className={styles.stateTitle}>Нет записей</div>
          <div className={styles.stateSub}>
            {statusFilter ? 'Нет записей с выбранным статусом.' : 'К вам пока никто не записался.'}
          </div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          <div className={styles.list}>
            {items.map(appt => (
              <div key={appt.uuid} className={styles.card}>
                <div className={styles.cardHead}>
                  <div className={styles.cardStudent}>
                    <span className={styles.studentName}>
                      {appt.student?.full_name || '—'}
                    </span>
                    <span className={styles.studentEmail}>{appt.student?.email || ''}</span>
                  </div>
                  <Badge tone={STATUS_TONE[appt.status] || 'neutral'}>
                    {STATUS_LABEL[appt.status] || appt.status}
                  </Badge>
                </div>

                <div className={styles.cardMeta}>
                  <span className={styles.metaItem}>
                    <Icon name="calendar" size={13} />
                    {fmtDatetime(appt.starts_at)}
                  </span>
                  <span className={styles.metaItem}>
                    <Icon name="bell" size={13} />
                    {MODALITY_LABEL[appt.modality] || appt.modality}
                    {appt.duration_minutes ? ` · ${appt.duration_minutes} мин` : ''}
                  </span>
                </div>

                {appt.topic && (
                  <div className={styles.cardTopic}>Тема: {appt.topic}</div>
                )}
                {appt.cancellation_reason && (
                  <div className={styles.cardReason}>Причина отмены: {appt.cancellation_reason}</div>
                )}
                {appt.decline_reason && (
                  <div className={styles.cardReason}>Причина отклонения: {appt.decline_reason}</div>
                )}

                {appt.status === 'pending_confirmation' && (
                  <div className={styles.cardActions}>
                    <Button
                      type="button"
                      variant="primary"
                      size="sm"
                      disabled={confirming === appt.uuid}
                      onClick={() => handleConfirm(appt.uuid)}
                    >
                      {confirming === appt.uuid ? 'Подтверждаем…' : 'Подтвердить'}
                    </Button>
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={() => openDecline(appt.uuid)}
                    >
                      Отклонить
                    </Button>
                  </div>
                )}
              </div>
            ))}
          </div>

          {totalPages > 1 && (
            <div className={styles.pagination}>
              <Button
                type="button"
                variant="icon"
                size="sm"
                aria-label="Предыдущая страница"
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                <Icon name="chevron-left" size={16} />
              </Button>
              <span className={styles.pageInfo}>{page} / {totalPages}</span>
              <Button
                type="button"
                variant="icon"
                size="sm"
                aria-label="Следующая страница"
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <Icon name="chevron-right" size={16} />
              </Button>
            </div>
          )}
          <div className={styles.totalHint}>Всего записей: {total}</div>
        </>
      )}
      </>
      )}

      {/* Decline modal */}
      <Modal
        open={!!declineModal}
        onClose={() => setDeclineModal(null)}
        ariaLabel="Отклонить запись"
        size="sm"
      >
        <div className={styles.modalBody}>
        <h2 className={styles.modalTitle}>Отклонить запись</h2>
        <p className={styles.modalSub}>Укажите причину (необязательно):</p>
        <textarea
          className={styles.reasonInput}
          rows={3}
          placeholder="Причина отклонения…"
          value={declineReason}
          onChange={e => setDeclineReason(e.target.value)}
        />
        <div className={styles.modalActions}>
          <Button
            type="button"
            variant="secondary"
            onClick={() => setDeclineModal(null)}
          >
            Отмена
          </Button>
          <Button
            type="button"
            variant="primary"
            disabled={declining}
            onClick={handleDecline}
          >
            {declining ? 'Отклоняем…' : 'Отклонить'}
          </Button>
        </div>
        </div>
      </Modal>
    </div>
  );
}
