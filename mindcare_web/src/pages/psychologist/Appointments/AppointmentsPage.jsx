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

// Все даты/время показываем в московском времени через Intl (не ручной +3).
const _dayDateFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', weekday: 'long', day: 'numeric', month: 'long',
});
const _timeFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', hour: '2-digit', minute: '2-digit',
});

// «Понедельник, 24 июня»
function fmtDayDate(iso) {
  if (!iso) return '—';
  const s = _dayDateFmt.format(new Date(iso));
  return s.charAt(0).toUpperCase() + s.slice(1);
}

// «10:00»
function fmtTime(iso) {
  if (!iso) return '';
  return _timeFmt.format(new Date(iso));
}

// «10:00–10:50» (или просто начало, если ends_at нет)
function fmtTimeRange(starts, ends) {
  const start = fmtTime(starts);
  if (!ends) return start;
  return `${start}–${fmtTime(ends)}`;
}

// Субъект записи: зарегистрированный студент, карточка незарегистрированного
// студента, либо ничего. ПДн карточки не логируем.
function subjectOf(appt) {
  if (appt.student) {
    return {
      name: appt.student.full_name || '—',
      contact: appt.student.email || '',
      isCard: false,
    };
  }
  if (appt.unregistered_student_card) {
    const card = appt.unregistered_student_card;
    return {
      name: card.full_name || '—',
      contact: card.phone || card.email || '',
      isCard: true,
    };
  }
  return { name: 'Клиент не указан', contact: '', isCard: false };
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

  // Defensive: backend сортирует по starts_at ASC, но гарантируем порядок и в UI
  // (только отображение текущей страницы — не трогаем пагинацию).
  const sortedItems = [...items].sort(
    (a, b) => new Date(a.starts_at) - new Date(b.starts_at)
  );

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
            {sortedItems.map(appt => {
              const subj = subjectOf(appt);
              const durationMin =
                appt.duration_minutes || appt.meeting_type_duration_minutes;
              return (
              <div key={appt.uuid} className={styles.card}>
                <div className={styles.cardHead}>
                  <div className={styles.cardStudent}>
                    <span className={styles.studentName}>{subj.name}</span>
                    {subj.contact && (
                      <span className={styles.studentEmail}>{subj.contact}</span>
                    )}
                  </div>
                  <div className={styles.cardBadges}>
                    {subj.isCard && <Badge tone="neutral">Карточка</Badge>}
                    <Badge tone={STATUS_TONE[appt.status] || 'neutral'}>
                      {STATUS_LABEL[appt.status] || appt.status}
                    </Badge>
                  </div>
                </div>

                <div className={styles.cardMeta}>
                  <span className={styles.metaItem}>
                    <Icon name="calendar" size={13} />
                    {fmtDayDate(appt.starts_at)} · {fmtTimeRange(appt.starts_at, appt.ends_at)}
                  </span>
                  <span className={styles.metaItem}>
                    <Icon name="bell" size={13} />
                    {appt.meeting_type_name || 'Индивидуальная встреча'}
                    {' · '}
                    {MODALITY_LABEL[appt.modality] || appt.modality}
                    {durationMin ? ` · ${durationMin} мин` : ''}
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
              );
            })}
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
