import { useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Button from '../../components/UI/Button/Button';
import Badge from '../../components/UI/Badge/Badge';
import { useStudents } from '../../features/supervisor/hooks/useStudents';
import AssignModal from '../../features/supervisor/components/AssignModal';
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

export default function EngagementsPage() {
  const { items, loading, error, total, page, setPage, query, setQuery, refetch } =
    useStudents();

  // modal: { mode, student } | null
  const [modal, setModal]     = useState(null);
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
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>Студент</th>
                  <th>Текущий психолог</th>
                  <th>Статус</th>
                  <th className={styles.actionsCol}>Действия</th>
                </tr>
              </thead>
              <tbody>
                {items.map(student => {
                  const eng = student.current_engagement;
                  const psy = eng?.psychologist;
                  return (
                    <tr key={student.id}>
                      {/* Student */}
                      <td>
                        <div className={styles.nameCell}>
                          <div className={styles.avatar}>
                            {student.full_name.charAt(0).toUpperCase()}
                          </div>
                          <div>
                            <div className={styles.fullName}>{student.full_name}</div>
                            <div className={styles.email}>{student.email}</div>
                          </div>
                        </div>
                      </td>

                      {/* Psychologist */}
                      <td>
                        {psy ? (
                          <div>
                            <div className={styles.fullName}>{psy.full_name}</div>
                            <div className={styles.email}>{psy.email}</div>
                          </div>
                        ) : (
                          <span className={styles.noPsy}>Не назначен</span>
                        )}
                      </td>

                      {/* Status */}
                      <td>
                        {eng ? (
                          <Badge tone={STATUS_TONES[eng.status] || 'neutral'}>
                            {STATUS_LABELS[eng.status] || eng.status}
                          </Badge>
                        ) : (
                          <Badge tone="neutral">—</Badge>
                        )}
                      </td>

                      {/* Actions */}
                      <td className={styles.actionsCell}>
                        {!eng ? (
                          <Button
                            variant="primary"
                            size="sm"
                            onClick={() => openModal('assign', student)}
                          >
                            Назначить
                          </Button>
                        ) : (
                          <div className={styles.btnGroup}>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => openModal('transfer', student)}
                            >
                              Переназначить
                            </Button>
                            <Button
                              variant="icon"
                              size="sm"
                              tone="danger"
                              onClick={() => openModal('close', student)}
                              title="Закрыть связь"
                              aria-label="Закрыть связь"
                            >
                              <Icon name="trash" size={15} />
                            </Button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          {totalPages > 1 && (
            <div className={styles.pagination}>
              <button
                className={styles.pageBtn}
                disabled={page === 1}
                onClick={() => setPage(p => p - 1)}
              >
                <Icon name="chevron-left" size={16} />
              </button>
              <span className={styles.pageInfo}>
                {page} / {totalPages}
              </span>
              <button
                className={styles.pageBtn}
                disabled={page === totalPages}
                onClick={() => setPage(p => p + 1)}
              >
                <Icon name="chevron-right" size={16} />
              </button>
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
    </div>
  );
}
