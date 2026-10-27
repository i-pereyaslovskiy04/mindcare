import { useCallback, useEffect, useId, useMemo, useRef, useState } from 'react';
import { dateKey } from './utils/calendarUtils';
import { useMyAppointments } from '../../../features/appointments/hooks/useMyAppointments';
import { useAvailableSlots } from '../../../features/appointments/hooks/useAvailableSlots';
import {
  bookAppointment,
  cancelAppointment,
  getStudentMeetingTypes,
} from '../../../api/appointments.api';
import CalendarHeader from './components/CalendarHeader';
import CalendarGrid from './components/CalendarGrid';
import CalendarDayPopup from './components/CalendarDayPopup';
import UpcomingList from './components/UpcomingList';
import SessionHistory from './components/SessionHistory';
import DateInput from '../../../components/UI/DateInput/DateInput';
import Select from '../../../components/UI/Select/Select';
import Button from '../../../components/UI/Button/Button';
import styles from './CalendarPage.module.css';

const _today = new Date();
const todayKey = dateKey(_today.getFullYear(), _today.getMonth(), _today.getDate());

// Moscow is UTC+3
function toMsk(utcDate) {
  return new Date(utcDate.getTime() + 3 * 60 * 60 * 1000);
}
function mskDateStr(utcDate) {
  return toMsk(utcDate).toISOString().substring(0, 10);
}
function mskTimeStr(utcDate) {
  return toMsk(utcDate).toISOString().substring(11, 16);
}

const STATUS_LABEL = {
  pending_confirmation: 'Ожидает подтверждения',
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

function toSession(appt) {
  const start = new Date(appt.starts_at);
  const end   = appt.ends_at ? new Date(appt.ends_at) : null;
  const date  = mskDateStr(start);
  const time  = end
    ? `${mskTimeStr(start)}–${mskTimeStr(end)}`
    : mskTimeStr(start);
  // Прошедшая — итоговый статус или уже наступивший starts_at при ЛЮБОМ
  // статусе (в т.ч. pending_confirmation): такая запись уходит в историю,
  // отменить её нельзя (backend отменяет только до дня встречи).
  const isPast =
    ['completed', 'no_show', 'cancelled', 'declined'].includes(appt.status) ||
    start < new Date();
  return {
    id:          appt.uuid,
    uuid:        appt.uuid,
    date,
    time,
    title:       appt.meeting_type_name || 'Индивидуальная встреча',
    psychologist: appt.psychologist?.full_name || '',
    type:        appt.modality === 'in_person' ? 'audio' : 'video',
    status:      isPast ? 'past' : 'upcoming',
    rawStatus:   appt.status,
    statusLabel: STATUS_LABEL[appt.status] || appt.status,
    statusTone:  STATUS_TONE[appt.status]  || 'neutral',
    desc:        appt.topic || '',
    canCancel:   ['pending_confirmation', 'confirmed'].includes(appt.status) && !isPast,
  };
}

const MODALITY_OPTIONS = [
  { label: 'Онлайн', value: 'online' },
  { label: 'Очно',   value: 'in_person' },
];

// Только типы, которые реально попадают в календарь (сессии из API).
// Задания и записи дневника здесь не показываются: интеграции календаря с
// ними нет, прежние mock-события убраны.
const LEGEND_ITEMS = [
  { label: 'Сессия',            color: 'var(--espresso)' },
  { label: 'Прошедшая встреча', color: 'var(--latte)'    },
];

export default function CalendarPage() {
  const [year, setYear]   = useState(_today.getFullYear());
  const [month, setMonth] = useState(_today.getMonth());
  // Окно «События дня»: { key, pos } | null.
  const [popup, setPopup] = useState(null);

  // Booking form. bookDate ('YYYY-MM-DD' | '') — единственный источник
  // выбранной даты: его меняют и нажатие дня календаря, и DateInput формы,
  // а календарь подсвечивает этот день в отображаемом месяце.
  const todayStr = _today.toISOString().substring(0, 10);
  const [meetingTypes, setMeetingTypes] = useState([]);
  const [mtId, setMtId]                 = useState('');
  const [bookDate, setBookDate]         = useState('');
  const [modality, setModality]         = useState('online');
  const [selectedSlot, setSelectedSlot] = useState(null);
  const [booking, setBooking]           = useState(false);
  const [bookError, setBookError]       = useState(null);
  const [bookSuccess, setBookSuccess]   = useState(false);

  const calendarBoxRef = useRef(null);
  const popupId = useId();
  const dateLabelId = useId();

  // Real appointments
  const { items: appointments, loading, refetch } = useMyAppointments({ size: 100 });

  // Bookable individual meeting types (student picks one before slots)
  useEffect(() => {
    getStudentMeetingTypes()
      .then(data => setMeetingTypes(Array.isArray(data) ? data : (data.items || [])))
      .catch(() => { /* ignore — booking still partially usable */ });
  }, []);

  const selectedMt = meetingTypes.find(m => String(m.id) === String(mtId)) || null;
  const allowsBoth = !!(selectedMt?.allow_online && selectedMt?.allow_in_person);

  // Slots require meeting type + format + date (schedule v2)
  const { slots, loading: slotsLoading, error: slotsError } = useAvailableSlots({
    date: bookDate,
    meetingTypeId: mtId,
    modality,
  });

  // Picking a type fixes the format to the single allowed one (or keeps it if both)
  function onTypeChange(v) {
    setMtId(v);
    const mt = meetingTypes.find(m => String(m.id) === String(v));
    if (mt) {
      const allowed = [];
      if (mt.allow_online) allowed.push('online');
      if (mt.allow_in_person) allowed.push('in_person');
      setModality(prev => (allowed.includes(prev) ? prev : (allowed[0] || 'online')));
    }
    setSelectedSlot(null);
  }

  // Reset slot when type / date / format changes
  useEffect(() => { setSelectedSlot(null); }, [bookDate, mtId, modality]);
  // Clear success after 4s
  useEffect(() => {
    if (!bookSuccess) return;
    const t = setTimeout(() => setBookSuccess(false), 4000);
    return () => clearTimeout(t);
  }, [bookSuccess]);

  // Derive session objects
  const sessions = useMemo(() => appointments.map(toSession), [appointments]);

  // Calendar dot map: date → { status: 'upcoming' | 'past' }
  const sessionMap = useMemo(() => {
    const map = {};
    sessions.forEach(s => { map[s.date] = { status: s.status }; });
    return map;
  }, [sessions]);

  // Events map: date → [{ type, title, time, desc }] — только сессии из API.
  const eventsMap = useMemo(() => {
    const map = {};
    sessions.forEach(s => {
      if (!map[s.date]) map[s.date] = [];
      map[s.date].push({ date: s.date, type: s.status === 'past' ? 'past' : 'session', title: s.title, time: s.time, desc: s.desc });
    });
    return map;
  }, [sessions]);

  const upcoming = useMemo(
    () => sessions.filter(s => s.status === 'upcoming').sort((a, b) => a.date.localeCompare(b.date)),
    [sessions],
  );
  const past = useMemo(
    () => sessions.filter(s => s.status === 'past').sort((a, b) => b.date.localeCompare(a.date)),
    [sessions],
  );

  const popupKey = popup?.key ?? null;

  // «✕» и Escape возвращают фокус на кнопку дня (она остаётся в DOM).
  // Закрытие окна не сбрасывает выбранную дату формы.
  const closePopup = useCallback(({ restoreFocus = false } = {}) => {
    if (restoreFocus && popupKey) {
      calendarBoxRef.current
        ?.querySelector(`button[data-date="${popupKey}"]`)
        ?.focus();
    }
    setPopup(null);
  }, [popupKey]);

  // Смена месяца закрывает окно: иначе оно показывало бы события дня из
  // прежнего месяца на старых координатах.
  function prev() {
    closePopup();
    if (month === 0) { setYear(y => y - 1); setMonth(11); }
    else setMonth(m => m - 1);
  }
  function next() {
    closePopup();
    if (month === 11) { setYear(y => y + 1); setMonth(0); }
    else setMonth(m => m + 1);
  }
  // Нажатие дня открывает окно (повторное — закрывает) и подставляет дату
  // в форму записи. Прошедшие дни окно открывают (история встреч), но в форму
  // не попадают: DateInput не даёт выбрать дату раньше сегодняшней.
  function handleDayClick(key, pos) {
    if (popupKey === key) {
      setPopup(null);
      return;
    }
    setPopup({ key, pos });
    if (key >= todayKey) setBookDate(key);
  }
  // Ручной выбор даты в форме: окно прежнего дня закрывается, подсветка
  // календаря следует за bookDate.
  function handleBookDateChange(value) {
    setBookDate(value);
    setPopup(null);
  }

  async function handleBook() {
    if (!selectedSlot) return;
    setBooking(true);
    setBookError(null);
    try {
      await bookAppointment({
        meeting_type_id: Number(mtId),
        starts_at: selectedSlot.starts_at,
        modality,
      });
      setBookSuccess(true);
      setSelectedSlot(null);
      setBookDate('');
      refetch();
    } catch (e) {
      setBookError(e.message || 'Ошибка записи');
    } finally {
      setBooking(false);
    }
  }

  async function handleCancel(uuid) {
    try {
      await cancelAppointment(uuid);
      refetch();
    } catch {
      // silently ignore — user sees updated list on next load
    }
  }

  return (
    <div className={styles.page}>
      {/* Порядок DOM = порядок на телефоне: календарь → форма записи →
          списки. На desktop grid-areas ставят форму в правую колонку. */}
      <section className={styles.calendarBox} ref={calendarBoxRef} onClick={e => e.stopPropagation()}>
        <CalendarHeader year={year} month={month} onPrev={prev} onNext={next} />
        <CalendarGrid
          year={year}
          month={month}
          sessionMap={sessionMap}
          todayKey={todayKey}
          selectedKey={popupKey ?? (bookDate || null)}
          openKey={popupKey}
          onDayClick={handleDayClick}
          onDismiss={closePopup}
          containerRef={calendarBoxRef}
          eventsMap={eventsMap}
          popupId={popupId}
        />
        <div className={styles.legend}>
          {LEGEND_ITEMS.map(item => (
            <span key={item.label} className={styles.legendItem}>
              <span className={styles.legendDot} style={{ background: item.color }} aria-hidden="true" />
              {item.label}
            </span>
          ))}
        </div>
        {popup?.pos && (
          <CalendarDayPopup
            id={popupId}
            events={eventsMap[popup.key] || []}
            onClose={closePopup}
            top={popup.pos.top}
            left={popup.pos.left}
            arrowLeft={popup.pos.arrowLeft}
          />
        )}
      </section>

      <div className={styles.right}>
        <section className={styles.bookingBox}>
          <h3 className={styles.bookingTitle}>Записаться на сессию</h3>

          <div className={styles.field}>
            <Select
              label="Тип встречи"
              placeholder="Выберите тип встречи"
              value={mtId}
              options={meetingTypes.map(mt => ({
                value: String(mt.id), label: mt.name,
              }))}
              onChange={onTypeChange}
            />
          </div>

          {selectedMt && (
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Формат</label>
              {allowsBoth ? (
                <div className={styles.chips}>
                  {MODALITY_OPTIONS.map(opt => (
                    <button
                      key={opt.value}
                      type="button"
                      aria-pressed={modality === opt.value}
                      className={modality === opt.value ? `${styles.chip} ${styles.chipActive}` : styles.chip}
                      onClick={() => { setModality(opt.value); setSelectedSlot(null); }}
                    >
                      {opt.label}
                    </button>
                  ))}
                </div>
              ) : (
                <span className={styles.slotHint}>
                  {modality === 'online' ? 'Онлайн' : 'Очно'} - единственный доступный формат
                </span>
              )}
            </div>
          )}

          <div className={styles.field}>
            <label id={dateLabelId} className={styles.fieldLabel}>Дата</label>
            <DateInput
              labelledBy={dateLabelId}
              value={bookDate}
              onChange={handleBookDateChange}
              placeholder="Выберите дату"
              min={todayStr}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.fieldLabel}>Доступные слоты</label>
            {!mtId && (
              <span className={styles.slotHint}>Сначала выберите тип встречи</span>
            )}
            {mtId && !bookDate && (
              <span className={styles.slotHint}>Выберите дату, чтобы увидеть слоты</span>
            )}
            {mtId && bookDate && slotsLoading && (
              <span className={styles.slotHint}>Загружаем слоты…</span>
            )}
            {mtId && bookDate && !slotsLoading && slotsError && (
              <span className={styles.slotHint}>Нет назначенного психолога или ошибка загрузки</span>
            )}
            {mtId && bookDate && !slotsLoading && !slotsError && slots.length === 0 && (
              <span className={styles.slotHint}>Нет свободных слотов на эту дату</span>
            )}
            {slots.length > 0 && (
              <div className={styles.slots}>
                {slots.map(slot => {
                  const mskTime = toMsk(new Date(slot.starts_at)).toISOString().substring(11, 16);
                  const isActive = selectedSlot?.starts_at === slot.starts_at;
                  return (
                    <button
                      key={slot.starts_at}
                      type="button"
                      aria-pressed={isActive}
                      className={isActive ? `${styles.slot} ${styles.slotActive}` : styles.slot}
                      onClick={() => setSelectedSlot(prev =>
                        prev?.starts_at === slot.starts_at ? null : slot
                      )}
                    >
                      {mskTime}
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {bookError && <div className={styles.bookError}>{bookError}</div>}
          {bookSuccess && <div className={styles.bookSuccess}>Запись создана! Ожидайте подтверждения психолога.</div>}

          <Button
            variant="primary"
            disabled={!mtId || !selectedSlot || booking}
            style={{ width: '100%', marginTop: 4 }}
            onClick={handleBook}
          >
            {booking ? 'Отправляем…' : 'Записаться'}
          </Button>
        </section>
      </div>

      <div className={styles.lists}>
        {loading && <div className={styles.loadingHint}>Загрузка сессий…</div>}
        {!loading && <UpcomingList sessions={upcoming} onCancel={handleCancel} />}
        {!loading && <SessionHistory sessions={past} />}
      </div>
    </div>
  );
}
