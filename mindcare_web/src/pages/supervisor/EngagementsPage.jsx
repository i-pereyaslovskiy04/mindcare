import { useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import Badge from '../../components/UI/Badge/Badge';
import ResponsiveTable from '../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../components/UI/ActionsMenu/ActionsMenu';
import { useStudents } from '../../features/supervisor/hooks/useStudents';
import { getEngagementActions } from '../../features/supervisor/engagementActions';
import AssignModal from '../../features/supervisor/components/AssignModal';
import StudentTestResults from '../../features/tests/ui/StudentTestResults';
import UserContactsDialog from '../../features/contacts/ui/UserContactsDialog';
import {
  createEngagement,
  transferEngagement,
  closeEngagement,
} from '../../api/supervisor.api';
import styles from './EngagementsPage.module.css';

const STATUS_LABELS = {
  active:      'Активна',
  completed:   'Завершена',
  transferred: 'Переназначена',
};

const STATUS_TONES = {
  active:      'success',
  completed:   'neutral',
  transferred: 'warning',
};

/** Связь студента: текущий психолог и статус (или «Не назначен»). */
function EngagementLink({ student }) {
  const eng = student.current_engagement;
  const psy = eng?.psychologist;
  if (!eng) return <span className={styles.noPsy}>Не назначен</span>;
  return (
    <>
      {psy && (
        <span className={styles.psy}>
          <span className={styles.psyName}>{psy.full_name}</span>
          <span className={styles.psyEmail}>{psy.email}</span>
        </span>
      )}
      <Badge tone={STATUS_TONES[eng.status] || 'neutral'}>
        {STATUS_LABELS[eng.status] || eng.status}
      </Badge>
    </>
  );
}

export default function EngagementsPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, refetch } =
    useStudents();

  // modal: { mode, student } | null
  const [modal, setModal]     = useState(null);
  const [resultsFor, setResultsFor] = useState(null); // студент для просмотра результатов
  const [contactsFor, setContactsFor] = useState(null); // студент для просмотра контактов
  const [notice, setNotice]   = useState(null); // { type: 'success'|'error', text }

  function showNotice(type, text) {
    setNotice({ type, text });
    setTimeout(() => setNotice(null), 4000);
  }

  function openModal(mode, student) {
    setModal({ mode, student });
  }

  function closeModal() {
    setModal(null);
  }

  async function handleConfirm({ selectedPsyId, primaryConcern, reason }) {
    const { mode, student } = modal;

    if (mode === 'assign') {
      await createEngagement({
        client_id: student.id,
        psychologist_id: selectedPsyId,
        primary_concern: primaryConcern,
      });
      showNotice('success', `Психолог назначен студенту ${student.full_name}`);
    } else if (mode === 'transfer') {
      await transferEngagement(student.current_engagement.id, {
        new_psychologist_id: selectedPsyId,
        transfer_reason: reason,
      });
      showNotice('success', `Психолог переназначен для ${student.full_name}`);
    } else if (mode === 'close') {
      await closeEngagement(student.current_engagement.id, { reason });
      showNotice('success', `Связь с ${student.full_name} закрыта`);
    }

    closeModal();
    refetch();
  }

  const totalPages = Math.max(1, Math.ceil(total / 20));

  // Одни обработчики для всех раскладок таблицы; диалоги — ниже, по одному.
  const actionHandlers = {
    onAssign: (s) => openModal('assign', s),
    onTransfer: (s) => openModal('transfer', s),
    onClose: (s) => openModal('close', s),
    onResults: (s) => setResultsFor(s),
    onContacts: (s) => setContactsFor(s),
  };

  return (
    <div className={styles.page}>
      {/* Header */}
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Управление</div>
          <h1 className={styles.pageTitle}>Назначение психологов</h1>
        </div>
        <div className={styles.searchWrap}>
          <Icon name="search" size={16} />
          <input
            className={styles.searchInput}
            type="text"
            placeholder="Поиск по студентам…"
            value={query}
            onChange={e => setQuery(e.target.value)}
          />
        </div>
      </div>

      {/* Notice banner */}
      {notice && (
        <div className={`${styles.notice} ${styles[`notice_${notice.type}`]}`}>
          {notice.text}
        </div>
      )}

      {/* Content */}
      {loading && (
        <div className={styles.stateBox}>
          <div className={styles.spinner} />
          <span>Загрузка…</span>
        </div>
      )}

      {!loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.errorText}>{error}</div>
          <Button variant="secondary" onClick={refetch}>Повторить</Button>
        </div>
      )}

      {!loading && !error && items.length === 0 && (
        <div className={styles.stateBox}>
          <div className={styles.emptyText}>
            {query ? `Студенты по запросу «${query}» не найдены` : 'Студенты не найдены'}
          </div>
        </div>
      )}

      {!loading && !error && items.length > 0 && (
        <>
          {/* Раскладка wide / compact / mobile — shared ResponsiveTable;
              загрузка, ошибка с повтором и пусто — выше, как прежде. */}
          <ResponsiveTable
            label="Студенты и назначенные психологи"
            items={items}
            getKey={(s) => s.id}
            identity={{
              header: 'Студент',
              primary: (s) => s.full_name,
              secondary: (s) => s.email,
            }}
            status={{
              header: 'Психолог и статус',
              render: (s) => <EngagementLink student={s} />,
            }}
            actions={{
              primary: (s) => {
                const { primary } = getEngagementActions(s, actionHandlers);
                return (
                  <Button
                    variant={primary.variant || 'secondary'}
                    size="sm"
                    onClick={primary.onSelect}
                    aria-label={primary.ariaLabel}
                  >
                    {primary.label}
                  </Button>
                );
              },
              menu: (s) => (
                <ActionsMenu
                  triggerLabel={`Другие действия: ${s.full_name}`}
                  items={getEngagementActions(s, actionHandlers).menu}
                />
              ),
            }}
          />

          {/* Pagination */}
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
              <span className={styles.pageInfo}>
                {page} / {totalPages}
              </span>
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

          <div className={styles.totalHint}>
            Всего студентов: {total}
          </div>
        </>
      )}

      {/* Modal */}
      {modal && (
        <AssignModal
          mode={modal.mode}
          student={modal.student}
          onConfirm={handleConfirm}
          onClose={closeModal}
        />
      )}

      {/* Контакты студента (ADR-032): значений в таблице нет, чтение фиксируется в журнале */}
      {contactsFor && (
        <UserContactsDialog
          userUuid={contactsFor.uuid}
          name={contactsFor.full_name}
          onClose={() => setContactsFor(null)}
        />
      )}

      {/* Результаты психодиагностики студента (Этап E) */}
      {resultsFor && (
        <div
          className={styles.resultsBackdrop}
          role="dialog"
          aria-modal="true"
          aria-label={`Результаты тестов: ${resultsFor.full_name}`}
          onClick={() => setResultsFor(null)}
        >
          <div className={styles.resultsModal} onClick={(e) => e.stopPropagation()}>
            <div className={styles.resultsHead}>
              <h3 className={styles.resultsTitle}>
                Результаты тестов · {resultsFor.full_name}
              </h3>
              <Button
                variant="icon"
                size="sm"
                aria-label="Закрыть"
                onClick={() => setResultsFor(null)}
              >
                <Icon name="x" size={16} />
              </Button>
            </div>
            <StudentTestResults studentUuid={resultsFor.uuid} activeRole="supervisor" />
          </div>
        </div>
      )}
    </div>
  );
}
