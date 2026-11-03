import { Link } from 'react-router-dom';
import Badge from '../../components/UI/Badge/Badge';
import Icon from '../../components/Icon/Icon';
import { usePsychologistCalendarRange } from '../../features/psychologist/hooks/usePsychologistCalendarRange';
import {
  mskTodayKey, addDaysToKey, isHomeUpcomingEvent,
} from '../../features/psychologist/calendar/calendarMappers';
import useClientsTotal from '../../features/psychologist/hooks/useClientsTotal';
import { useMessagesBadge } from '../../features/chat/hooks/useMessagesBadge';
import { NEUTRAL_GREETING } from '../../shared/lib/greeting';
import styles from '../../components/CabinetLayout/CabinetHome.module.css';

const STATUS_TONE = {
  pending_confirmation: 'warning',
  confirmed:            'success',
  cancelled:            'error',
  declined:             'error',
  completed:            'neutral',
  no_show:              'warning',
};
const STATUS_SHORT = {
  pending_confirmation: 'Ожидает',
  confirmed:            'Подтв.',
  cancelled:            'Отменена',
  declined:             'Отклонена',
  completed:            'Состоялась',
  no_show:              'Неявка',
};

const _dayShortFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', day: 'numeric', month: 'short',
});
function fmtDayShort(iso) {
  return _dayShortFmt.format(new Date(iso));
}

function HomeEventRow({ ev, showDate }) {
  return (
    <div className={styles.liRow}>
      <div className={styles.liIcon}><Icon name="calendar" size={18} /></div>
      <div className={styles.liBody}>
        <div className={styles.liTitle}>
          {ev.kind === 'group' ? ev.title : ev.subject.name}
        </div>
        <div className={styles.liDesc}>
          {showDate ? `${fmtDayShort(ev.startsAtIso)}, ` : ''}{ev.time}
          {ev.kind === 'group'
            ? ` · мест ${ev.registered}/${ev.capacity}`
            : ` · ${ev.title}`}
        </div>
      </div>
      {ev.kind === 'group'
        ? <Badge tone="neutral">Группа</Badge>
        : (
          <Badge tone={STATUS_TONE[ev.status] || 'neutral'}>
            {STATUS_SHORT[ev.status] || ev.status}
          </Badge>
        )}
    </div>
  );
}

export default function PsychologistHome() {
  const today    = new Date().toLocaleDateString('ru-RU', {
    weekday: 'long', day: 'numeric', month: 'long',
  });

  // Ближайшие встречи: диапазон [сегодня, сегодня+7] по Europe/Moscow.
  const todayKey = mskTodayKey();
  const { eventsByDay, loading: calLoading } = usePsychologistCalendarRange({
    dateFrom: todayKey,
    dateTo: addDaysToKey(todayKey, 7),
    includeGroups: true,
  });
  // Только реальные ближайшие встречи: pending/confirmed appointments + scheduled groups.
  const todayEvents = (eventsByDay[todayKey] || []).filter(isHomeUpcomingEvent);
  const upcoming = Object.keys(eventsByDay)
    .filter(k => k > todayKey)
    .sort()
    .flatMap(k => eventsByDay[k])
    .filter(isHomeUpcomingEvent)
    .slice(0, 5);
  const clientsTotal = useClientsTotal();
  const unreadDialogs = useMessagesBadge('psychologist');

  return (
    <div className={styles.page}>
      <div className={styles.labelTag}>{today}</div>
      <h1 className={styles.pageTitle}>{NEUTRAL_GREETING}</h1>
      <p className={styles.pageSub}>
        Кабинет психолога: клиенты, встречи, задания и сообщения.
      </p>

      {/* Welcome + hint */}
      <div className={`${styles.grid} ${styles.g21}`} style={{ marginBottom: 16 }}>
        <div className={styles.darkCard} data-hero-banner>
          <div className={styles.darkCardTitle}>
            Ваш рабочий<br /><em>кабинет</em>
          </div>
          <div className={styles.darkCardSub}>
            Карточки клиентов с встречами, заданиями и заметками — в разделе
            «Мои студенты».
          </div>
          <div className={styles.darkCardBtns}>
            <Link to="/psychologist/students" className={`${styles.btn} ${styles.btnLatte}`}>
              Мои студенты
            </Link>
            <Link to="/psychologist/settings" className={`${styles.btn} ${styles.btnGhostDark}`}>
              Настройки профиля
            </Link>
          </div>
        </div>

        <div className={styles.card} style={{ display: 'flex', flexDirection: 'column', gap: 12 }}>
          <div className={styles.sectionTitle}>Ближайшие встречи</div>

          {calLoading && <div className={styles.liDesc}>Загрузка…</div>}

          {!calLoading && (
            <>
              <div className={styles.liDesc} style={{ fontWeight: 600 }}>Сегодня</div>
              {todayEvents.length === 0 ? (
                <div className={styles.liDesc}>На сегодня встреч нет.</div>
              ) : (
                todayEvents.map(ev => <HomeEventRow key={ev.id} ev={ev} />)
              )}

              <div className={styles.liDesc} style={{ fontWeight: 600, marginTop: 4 }}>
                Ближайшие 7 дней
              </div>
              {upcoming.length === 0 ? (
                <div className={styles.liDesc}>Нет встреч на ближайшие дни.</div>
              ) : (
                upcoming.map(ev => <HomeEventRow key={ev.id} ev={ev} showDate />)
              )}
            </>
          )}
        </div>
      </div>

      {/* Stat cards */}
      <div className={`${styles.grid} ${styles.g3}`} style={{ marginBottom: 16 }}>
        <div className={styles.statCard} role="group" aria-label="Клиентов">
          <div className={styles.statLabel}>Клиентов</div>
          <div className={styles.statValue}>{clientsTotal ?? '—'}</div>
          <div className={styles.statDesc}>С активным сопровождением</div>
        </div>
        <div className={styles.statCard} role="group" aria-label="Встреч сегодня">
          <div className={styles.statLabel}>Встреч сегодня</div>
          <div className={styles.statValue}>{calLoading ? '—' : todayEvents.length}</div>
          <div className={styles.statDesc}>Ожидающие, подтверждённые и групповые</div>
        </div>
        <div className={styles.statCard} role="group" aria-label="Диалогов с непрочитанным">
          <div className={styles.statLabel}>Диалогов с непрочитанным</div>
          <div className={styles.statValue}>{unreadDialogs}</div>
          <div className={styles.statDesc}>Личные диалоги с клиентами</div>
        </div>
      </div>
    </div>
  );
}
