import Button from '../../../components/UI/Button/Button';
import Badge from '../../../components/UI/Badge/Badge';
import Icon from '../../../components/Icon/Icon';
import {
  MONTH_NAMES, DOW, buildMonthGrid, dateKeyFromParts, mskTodayKey,
} from '../../../features/psychologist/calendar/calendarMappers';
import styles from './PsychologistCalendar.module.css';

const STATUS_LABEL = {
  pending_confirmation: 'Ожидает',
  confirmed:            'Подтверждена',
  cancelled:            'Отменена',
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

function dotClass(ev) {
  if (ev.kind === 'group') return styles.dotGroup;
  if (ev.status === 'pending_confirmation') return styles.dotPending;
  if (ev.status === 'confirmed') return styles.dotConfirmed;
  return styles.dotMuted;
}

export default function PsychologistCalendar({
  year,
  month,
  eventsByDay = {},
  loading = false,
  onPrev,
  onNext,
  selectedDay,
  onSelectDay,
}) {
  const cells = buildMonthGrid(year, month);
  const todayKey = mskTodayKey();
  const selectedEvents = selectedDay ? (eventsByDay[selectedDay] || []) : [];

  return (
    <div className={styles.calendar}>
      <div className={styles.header}>
        <Button
          type="button" variant="icon" size="sm"
          aria-label="Предыдущий месяц" onClick={onPrev}
        >
          <Icon name="chevron-left" size={16} />
        </Button>
        <span className={styles.monthLabel}>
          {MONTH_NAMES[month]} {year}
        </span>
        <Button
          type="button" variant="icon" size="sm"
          aria-label="Следующий месяц" onClick={onNext}
        >
          <Icon name="chevron-right" size={16} />
        </Button>
        {loading && <span className={styles.loadingHint}>Загрузка…</span>}
      </div>

      <div className={styles.dowRow}>
        {DOW.map(d => <span key={d} className={styles.dowCell}>{d}</span>)}
      </div>

      <div className={styles.grid}>
        {cells.map((cell, idx) => {
          const key = dateKeyFromParts(cell.year, cell.month, cell.day);
          const dayEvents = eventsByDay[key] || [];
          const hasEvents = dayEvents.length > 0;
          const isToday = key === todayKey;
          const isSelected = key === selectedDay;
          const cls = [
            styles.cell,
            cell.current ? '' : styles.cellOut,
            isToday ? styles.cellToday : '',
            isSelected ? styles.cellSelected : '',
            hasEvents ? styles.cellHasEvents : '',
          ].filter(Boolean).join(' ');
          return (
            <button
              key={idx}
              type="button"
              className={cls}
              disabled={!hasEvents}
              aria-label={`${cell.day} ${MONTH_NAMES[cell.month]}${hasEvents ? `, встреч: ${dayEvents.length}` : ''}`}
              onClick={() => hasEvents && onSelectDay(key)}
            >
              <span className={styles.dayNum}>{cell.day}</span>
              {hasEvents && (
                <span className={styles.dots}>
                  {dayEvents.slice(0, 4).map(ev => (
                    <span key={ev.id} className={`${styles.dot} ${dotClass(ev)}`} />
                  ))}
                </span>
              )}
              {dayEvents.length > 1 && (
                <span className={styles.count}>{dayEvents.length}</span>
              )}
            </button>
          );
        })}
      </div>

      {selectedDay && selectedEvents.length > 0 && (
        <div className={styles.dayDetail}>
          <div className={styles.dayDetailHead}>Встречи · {selectedDay}</div>
          {selectedEvents.map(ev => (
            <div key={ev.id} className={styles.detailRow}>
              <span className={styles.detailTime}>
                <Icon name="calendar" size={13} /> {ev.time}
              </span>
              <div className={styles.detailBody}>
                <div className={styles.detailTitleRow}>
                  <span className={styles.detailName}>
                    {ev.kind === 'group' ? ev.title : ev.subject.name}
                  </span>
                  {ev.kind === 'group' && <Badge tone="neutral">Группа</Badge>}
                  {ev.kind === 'appointment' && ev.subject.isCard && (
                    <Badge tone="neutral">Карточка</Badge>
                  )}
                </div>
                <div className={styles.detailMeta}>
                  {ev.kind === 'group'
                    ? `${MODALITY_LABEL[ev.modality] || ev.modality} · мест: ${ev.registered}/${ev.capacity}`
                    : `${ev.title} · ${MODALITY_LABEL[ev.modality] || ev.modality}`}
                </div>
              </div>
              {ev.kind === 'appointment' && (
                <Badge tone={STATUS_TONE[ev.status] || 'neutral'}>
                  {STATUS_LABEL[ev.status] || ev.status}
                </Badge>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
