import { useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import ConfirmDialog from '../../../features/assignments/ui/ConfirmDialog';
import useMyAssignments from '../../../features/assignments/hooks/useMyAssignments';
import TaskItem from './components/TaskItem';
import styles from './TasksPage.module.css';

function StatTile({ label, value, sub }) {
  return (
    <div className={styles.statTile} role="group" aria-label={label}>
      <div className={styles.statLabel}>{label}</div>
      <div className={styles.statNum}>
        {value}
        {sub && <em>{sub}</em>}
      </div>
    </div>
  );
}

function TaskSection({
  id, title, list, emptyText, onComplete, pendingUuid, actionError, onRetry,
}) {
  const headingId = `${id}-title`;
  const firstLoad = list.loading && list.items.length === 0;

  return (
    <section className={styles.group} aria-labelledby={headingId}>
      <h2 id={headingId} className={styles.groupTitle}>
        {title}
        {!firstLoad && !list.error && <span className={styles.groupCount}>· {list.total}</span>}
      </h2>

      {firstLoad && <p className={styles.stateText} role="status">Загружаем задания…</p>}

      {list.error && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.errorText}>Не удалось загрузить задания.</p>
          <Button type="button" variant="secondary" size="sm" onClick={onRetry}>
            Повторить
          </Button>
        </div>
      )}

      {!firstLoad && !list.error && list.items.length === 0 && (
        <p className={styles.stateText}>{emptyText}</p>
      )}

      {list.items.map((task) => (
        <TaskItem
          key={task.uuid}
          task={task}
          onComplete={onComplete}
          pending={pendingUuid === task.uuid}
          error={actionError?.uuid === task.uuid ? actionError.message : null}
        />
      ))}

      {list.loadMoreError && (
        <p className={styles.errorText} role="alert">Не удалось загрузить следующие задания.</p>
      )}
      {list.hasMore && !list.error && (
        <div className={styles.loadMore}>
          <Button
            type="button"
            variant="secondary"
            onClick={list.loadMore}
            loading={list.loadingMore}
          >
            Показать ещё
          </Button>
        </div>
      )}
    </section>
  );
}

export default function TasksPage() {
  const {
    open, history, summary, refetch, complete, pendingUuid, actionError,
  } = useMyAssignments();
  const [confirmTask, setConfirmTask] = useState(null);

  async function confirmComplete() {
    if (!confirmTask) return;
    await complete(confirmTask.uuid);
    setConfirmTask(null);
  }

  // Ошибка задания, исчезнувшего из «Активных» после перезагрузки (например,
  // сопровождение закрыли), показывается над списком, а не теряется.
  const orphanError = actionError && !open.items.some(t => t.uuid === actionError.uuid)
    && !history.items.some(t => t.uuid === actionError.uuid)
    ? actionError.message : null;

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Задания от <em>психолога</em>
      </h1>
      <p className={styles.pageSub}>
        Задания между сессиями. Отметка «выполнено» сохраняется и видна вашему психологу.
      </p>

      {summary && (
        <div className={styles.stats}>
          <StatTile label="Активных заданий" value={summary.open_count} />
          <StatTile label="Выполнено" value={summary.completed_count} sub={` из ${summary.total_count}`} />
        </div>
      )}

      {orphanError && <p className={styles.errorText} role="alert">{orphanError}</p>}

      <TaskSection
        id="tasks-open"
        title="Активные"
        list={open}
        emptyText="Активных заданий нет."
        onComplete={setConfirmTask}
        pendingUuid={pendingUuid}
        actionError={actionError}
        onRetry={refetch}
      />
      <TaskSection
        id="tasks-history"
        title="История"
        list={history}
        emptyText="Выполненных и завершённых заданий пока нет."
        onComplete={setConfirmTask}
        pendingUuid={pendingUuid}
        actionError={actionError}
        onRetry={refetch}
      />

      <ConfirmDialog
        open={confirmTask !== null}
        title="Отметить задание выполненным?"
        description="Отметку нельзя будет снять. Психолог увидит, что задание выполнено."
        confirmLabel="Да, выполнено"
        loading={confirmTask !== null && pendingUuid === confirmTask.uuid}
        onConfirm={confirmComplete}
        onClose={() => setConfirmTask(null)}
      />
    </div>
  );
}
