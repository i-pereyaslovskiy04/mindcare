import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import useClientMeetings from '../hooks/useClientMeetings';
import {
  MODALITY_LABELS, formatMeetingWhen, meetingStatusLabel, meetingStatusTone,
} from '../lib/meetingFormat';
import AppointmentOutcomeActions from './AppointmentOutcomeActions';
import styles from './ClientMeetings.module.css';

function MeetingRow({ item, past, outcome, onAddNote }) {
  const details = [
    item.meeting_type_name || 'Индивидуальная встреча',
    MODALITY_LABELS[item.modality],
    item.via_card ? 'запись по карточке' : null,
  ].filter(Boolean).join(' · ');
  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <span className={styles.when}>{formatMeetingWhen(item.starts_at, item.ends_at)}</span>
        <Badge tone={meetingStatusTone(item, { past })}>{meetingStatusLabel(item, { past })}</Badge>
      </div>
      <p className={styles.meta}>{details}</p>
      {item.can_mark_outcome && (
        <p className={styles.hint}>Встреча прошла — отметьте итог.</p>
      )}
      {(item.can_mark_outcome || onAddNote) && (
        <div className={styles.itemFoot}>
          {item.can_mark_outcome && (
            <AppointmentOutcomeActions appointment={item} outcome={outcome} />
          )}
          {onAddNote && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => onAddNote({ uuid: item.uuid, starts_at: item.starts_at, ends_at: item.ends_at })}
            >
              Заметка
            </Button>
          )}
        </div>
      )}
    </li>
  );
}

function MeetingList({ title, list, status, past, emptyText, outcome, onAddNote }) {
  return (
    <section className={styles.group} aria-label={title}>
      <h4 className={styles.groupTitle}>{title}</h4>
      {status === 'loading' && <p className={styles.muted} role="status">Загружаем встречи…</p>}
      {status === 'error' && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.error}>Не удалось загрузить встречи.</p>
          <Button type="button" size="sm" variant="secondary" onClick={list.reset}>
            Повторить
          </Button>
        </div>
      )}
      {status === 'ready' && list.items.length === 0 && <p className={styles.muted}>{emptyText}</p>}
      {list.items.length > 0 && status !== 'error' && (
        <ul className={styles.list}>
          {list.items.map(item => (
            <MeetingRow
              key={item.uuid}
              item={item}
              past={past}
              outcome={outcome}
              onAddNote={onAddNote}
            />
          ))}
        </ul>
      )}
      {list.loadMoreError && (
        <p className={styles.error} role="alert">
          Не удалось загрузить следующие встречи. Нажмите «Показать ещё».
        </p>
      )}
      {list.hasMore && !list.error && (
        <div className={styles.more}>
          <Button type="button" variant="secondary" size="sm" onClick={list.loadMore}
            loading={list.loadingMore}>
            Показать ещё
          </Button>
        </div>
      )}
    </section>
  );
}

/**
 * «Встречи с клиентом» в карточке психолога (ADR-035): предстоящие и история
 * индивидуальных встреч этого клиента с текущим психологом, ручной итог
 * прошедшей подтверждённой встречи. Не редактор рабочей доступности.
 * onAddNote(meeting) — создать заметку к конкретной встрече (любой страницы).
 */
export default function ClientMeetings({ studentUuid, onAddNote }) {
  const {
    upcoming, history, upcomingStatus, historyStatus, status, outcome,
  } = useClientMeetings(studentUuid);

  if (status === 'unavailable') {
    return <p className={styles.muted}>Встречи недоступны: сопровождение не активно.</p>;
  }

  return (
    <div className={styles.wrap}>
      <MeetingList
        title="Предстоящие"
        list={upcoming}
        status={upcomingStatus}
        emptyText="Предстоящих встреч нет."
        outcome={outcome}
        onAddNote={onAddNote}
      />
      <MeetingList
        title="История"
        list={history}
        status={historyStatus}
        past
        emptyText="Прошедших встреч пока нет."
        outcome={outcome}
        onAddNote={onAddNote}
      />
    </div>
  );
}
