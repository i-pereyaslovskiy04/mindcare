import { useCallback, useEffect, useMemo, useState } from 'react';
import Button from '../../components/UI/Button/Button';
import Select from '../../components/UI/Select/Select';
import DateInput from '../../components/UI/DateInput/DateInput';
import {
  getMeetingTypes,
  getSupervisorPsychologists,
  getSupervisorSlots,
  supervisorBookAppointment,
} from '../../api/appointments.api';
import { getSupervisorEngagements } from '../../api/supervisor.api';
import styles from './BookingPage.module.css';

// Moscow is UTC+3
function mskTime(iso) {
  const msk = new Date(new Date(iso).getTime() + 3 * 60 * 60 * 1000);
  return msk.toISOString().substring(11, 16);
}

const MODALITY_OPTIONS = [
  { value: 'online',    label: 'Онлайн' },
  { value: 'in_person', label: 'Очно' },
];

const EMPTY_FORM = {
  student_id:      '',
  meeting_type_id: '',
  modality:        'in_person',
  date:            '',
  topic:           '',
};

export default function BookingPage() {
  const [psychologists, setPsychologists] = useState([]);
  const [meetingTypes,  setMeetingTypes]  = useState([]);
  const [psychId, setPsychId] = useState('');

  const [engagements, setEngagements] = useState([]);
  const [engLoading, setEngLoading]   = useState(false);
  const [engError, setEngError]       = useState(null);

  const [form, setForm]                   = useState(EMPTY_FORM);
  const [slots, setSlots]                 = useState([]);
  const [slotsLoading, setSlotsLoading]   = useState(false);
  const [selectedSlot, setSelectedSlot]   = useState(null);
  const [saving, setSaving]               = useState(false);
  const [error, setError]                 = useState(null);
  const [done, setDone]                   = useState(false);

  // Load psychologists + individual meeting types once
  useEffect(() => {
    (async () => {
      try {
        const data = await getSupervisorPsychologists();
        setPsychologists(data.items || data || []);
      } catch { /* ignore */ }
      try {
        const mt = await getMeetingTypes();
        const all = mt.items || mt || [];
        setMeetingTypes(all.filter(t => !t.is_group && t.is_active));
      } catch { /* ignore */ }
    })();
  }, []);

  // Load all active engagements page-by-page (backend caps size at 100).
  const loadEngagements = useCallback(async (pid) => {
    if (!pid) { setEngagements([]); setEngError(null); return; }
    setEngLoading(true);
    setEngError(null);
    try {
      const size = 100;
      let page = 1;
      let all = [];
      let total = Infinity;
      while (all.length < total) {
        // eslint-disable-next-line no-await-in-loop -- sequential pagination
        const data = await getSupervisorEngagements({
          status: 'active', page, size,
        });
        const items = Array.isArray(data) ? data : (data.items || []);
        all = all.concat(items);
        total = (data && typeof data.total === 'number')
          ? data.total
          : all.length;
        if (items.length < size) break;
        page += 1;
      }
      setEngagements(all);
    } catch (e) {
      setEngagements([]);
      setEngError(e.message || 'Не удалось загрузить назначения студентов');
    } finally {
      setEngLoading(false);
    }
  }, []);

  useEffect(() => {
    setForm(EMPTY_FORM);
    setSlots([]);
    setSelectedSlot(null);
    setError(null);
    setDone(false);
    loadEngagements(psychId);
  }, [psychId, loadEngagements]);

  const psychOptions = psychologists.map(p => ({
    value: String(p.id),
    label: p.full_name || p.email,
  }));

  // Filter students assigned to the selected psychologist using engagement.psychologist.id
  const studentOptions = useMemo(() => {
    const pid = Number(psychId);
    if (!pid) return [];
    return engagements
      .filter(e => Number(e.psychologist?.id) === pid)
      .map(e => ({
        value: String(e.client.id),
        label: e.client.full_name || e.client.email || `Студент #${e.client.id}`,
      }));
  }, [engagements, psychId]);

  const selectedMt = meetingTypes.find(m => String(m.id) === String(form.meeting_type_id));

  const formatOptions = selectedMt
    ? [
        selectedMt.allow_online    && { value: 'online',    label: 'Онлайн' },
        selectedMt.allow_in_person && { value: 'in_person', label: 'Очно' },
      ].filter(Boolean)
    : MODALITY_OPTIONS;

  function handleMtChange(v) {
    const mt = meetingTypes.find(m => String(m.id) === String(v));
    setForm(f => {
      let modality = f.modality;
      if (mt) {
        const allowed = [];
        if (mt.allow_online)    allowed.push('online');
        if (mt.allow_in_person) allowed.push('in_person');
        if (!allowed.includes(modality)) modality = allowed[0] || 'in_person';
      }
      return { ...f, meeting_type_id: v, modality };
    });
    setSelectedSlot(null);
    setSlots([]);
  }

  // Load free slots when psychologist + type + format + date are all set
  const { meeting_type_id: mtId, modality, date } = form;
  useEffect(() => {
    if (!psychId || !mtId || !modality || !date) {
      setSlots([]);
      return undefined;
    }
    let cancelled = false;
    setSlotsLoading(true);
    setSelectedSlot(null);
    getSupervisorSlots({
      psychologistId: Number(psychId),
      date,
      meetingTypeId:  Number(mtId),
      modality,
    })
      .then(data => { if (!cancelled) setSlots(data.slots || []); })
      .catch(() => { if (!cancelled) setSlots([]); })
      .finally(() => { if (!cancelled) setSlotsLoading(false); });
    return () => { cancelled = true; };
  }, [psychId, mtId, modality, date]);

  async function handleBook() {
    if (!form.student_id)      { setError('Выберите студента'); return; }
    if (!form.meeting_type_id) { setError('Выберите тип встречи'); return; }
    if (!selectedSlot)         { setError('Выберите свободный слот'); return; }
    setSaving(true);
    setError(null);
    try {
      await supervisorBookAppointment({
        student_id:      Number(form.student_id),
        psychologist_id: Number(psychId),
        meeting_type_id: Number(form.meeting_type_id),
        starts_at:       selectedSlot.starts_at,
        modality:        form.modality,
        topic:           form.topic || null,
      });
      setDone(true);
      setSelectedSlot(null);
      setSlots([]);
      setForm(f => ({ ...f, date: '', student_id: '', topic: '' }));
    } catch (e) {
      setError(e.message || 'Ошибка записи');
    } finally {
      setSaving(false);
    }
  }

  const canSubmit = !!form.student_id && !!form.meeting_type_id && !!selectedSlot && !saving;

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Супервизор</div>
          <h1 className={styles.pageTitle}>Запись <em>студентов</em></h1>
          <p className={styles.pageSub}>
            Ручная запись назначенного студента к психологу. Запись создаётся в статусе
            «ожидает подтверждения», психолог получит уведомление.
          </p>
        </div>
      </div>

      <div className={styles.form}>

        {/* Step 1: Psychologist */}
        <div className={styles.section}>
          <div className={styles.sectionLabel}>Шаг 1. Психолог</div>
          <div className={styles.fieldWrap}>
            <Select
              label="Психолог"
              placeholder="Выберите психолога"
              value={psychId}
              options={psychOptions}
              onChange={v => setPsychId(v)}
            />
          </div>
        </div>

        {/* Step 2: Student — filtered by selected psychologist */}
        {psychId && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Шаг 2. Студент</div>
            {engLoading && (
              <span className={styles.hint}>Загрузка студентов…</span>
            )}
            {!engLoading && engError && (
              <div className={styles.fieldWrap}>
                <span className={styles.saveErr}>{engError}</span>
                <Button
                  type="button"
                  variant="secondary"
                  size="sm"
                  onClick={() => loadEngagements(psychId)}
                >
                  Повторить
                </Button>
              </div>
            )}
            {!engLoading && !engError && studentOptions.length === 0 && (
              <span className={styles.hint}>
                У этого психолога нет активных назначений студентов.
              </span>
            )}
            {!engLoading && !engError && studentOptions.length > 0 && (
              <div className={styles.fieldWrap}>
                <Select
                  label="Студент"
                  placeholder="Выберите студента"
                  value={form.student_id}
                  options={studentOptions}
                  onChange={v => setForm(f => ({ ...f, student_id: v }))}
                />
              </div>
            )}
          </div>
        )}

        {/* Step 3: Meeting type + format */}
        {psychId && form.student_id && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Шаг 3. Тип встречи и формат</div>
            <div className={styles.row}>
              <div className={styles.fieldWrap}>
                <Select
                  label="Тип встречи"
                  placeholder="Выберите тип"
                  value={form.meeting_type_id}
                  options={meetingTypes.map(t => ({ value: String(t.id), label: t.name }))}
                  onChange={handleMtChange}
                />
              </div>
              <div className={styles.fieldWrap}>
                <Select
                  label="Формат"
                  value={form.modality}
                  options={formatOptions}
                  onChange={v => {
                    setForm(f => ({ ...f, modality: v }));
                    setSelectedSlot(null);
                  }}
                />
              </div>
            </div>
          </div>
        )}

        {/* Step 4: Date */}
        {psychId && form.student_id && form.meeting_type_id && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Шаг 4. Дата</div>
            <div className={styles.fieldWrap}>
              <DateInput
                label="Дата"
                value={form.date}
                onChange={v => {
                  setForm(f => ({ ...f, date: v }));
                  setSelectedSlot(null);
                }}
              />
            </div>
          </div>
        )}

        {/* Step 5: Free slots */}
        {psychId && form.student_id && form.meeting_type_id && form.date && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Шаг 5. Свободные слоты</div>
            {slotsLoading && (
              <span className={styles.hint}>Загружаем слоты…</span>
            )}
            {!slotsLoading && slots.length === 0 && (
              <span className={styles.hint}>Нет свободных слотов на эту дату.</span>
            )}
            {!slotsLoading && slots.length > 0 && (
              <div className={styles.slotGrid}>
                {slots.map(slot => {
                  const active = selectedSlot?.starts_at === slot.starts_at;
                  return (
                    <button
                      key={slot.starts_at}
                      type="button"
                      aria-pressed={active}
                      className={active
                        ? `${styles.slotBtn} ${styles.slotBtnActive}`
                        : styles.slotBtn}
                      onClick={() =>
                        setSelectedSlot(prev =>
                          prev?.starts_at === slot.starts_at ? null : slot
                        )
                      }
                    >
                      {mskTime(slot.starts_at)}
                    </button>
                  );
                })}
              </div>
            )}
          </div>
        )}

        {/* Topic — optional, shown once a student is selected */}
        {psychId && form.student_id && (
          <div className={styles.section}>
            <div className={styles.sectionLabel}>Тема (необязательно)</div>
            <div className={styles.fieldWrap}>
              <label className={styles.formLabel}>Тема встречи</label>
              <input
                className={styles.formInput}
                type="text"
                value={form.topic}
                onChange={e => setForm(f => ({ ...f, topic: e.target.value }))}
                placeholder="Например: тревожность, стресс"
              />
            </div>
          </div>
        )}

        {done && (
          <div className={styles.okMsg}>
            Студент записан. Психолог уведомлён.
          </div>
        )}
        {error && <div className={styles.saveErr}>{error}</div>}

        {psychId && form.student_id && (
          <div className={styles.actions}>
            <Button
              type="button"
              variant="primary"
              disabled={!canSubmit}
              onClick={handleBook}
            >
              {saving ? 'Записываем…' : 'Записать студента'}
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
