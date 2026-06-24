import { useCallback, useEffect, useMemo, useState } from 'react';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import Select from '../../components/UI/Select/Select';
import MultiSelect from '../../components/UI/MultiSelect/MultiSelect';
import Toggle from '../../components/UI/Toggle/Toggle';
import DateInput from '../../components/UI/DateInput/DateInput';
import TimePicker from '../../components/UI/TimePicker';
import Modal from '../../components/Modal/Modal';
import {
  getSupervisorPsychologists,
  getScheduleRules,
  getScheduleBreaks,
  createSchedule,
  updateSchedule,
  getScheduleImpact,
  deleteSchedule,
  restoreSchedule,
  extendSchedule,
  createScheduleException,
  getScheduleExceptions,
} from '../../api/appointments.api';
import styles from './SchedulePage.module.css';

const DAYS = [
  { value: '0', label: 'Понедельник' },
  { value: '1', label: 'Вторник' },
  { value: '2', label: 'Среда' },
  { value: '3', label: 'Четверг' },
  { value: '4', label: 'Пятница' },
  { value: '5', label: 'Суббота' },
  { value: '6', label: 'Воскресенье' },
];
const DAY_SHORT = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

const EXCEPTION_TYPES = [
  { value: 'day_off',            label: 'Выходной (весь день)' },
  { value: 'unavailable',        label: 'Блокировка (недоступность)' },
  { value: 'extra_availability', label: 'Доп. окно (доступность)' },
];
const EXCEPTION_TYPE_LABEL = Object.fromEntries(
  EXCEPTION_TYPES.map(t => [t.value, t.label])
);
const EXCEPTION_TYPE_TONE = {
  day_off: 'neutral',
  unavailable: 'warning',
  extra_availability: 'success',
};

const PERIOD_OPTIONS = [
  { value: '',          label: 'Не указан' },
  { value: 'morning',   label: 'Утро' },
  { value: 'afternoon', label: 'День' },
  { value: 'evening',   label: 'Вечер' },
];
const PERIOD_LABEL = Object.fromEntries(
  PERIOD_OPTIONS.filter(o => o.value).map(o => [o.value, o.label])
);

const EMPTY_SCHEDULE = {
  days_of_week: [],
  start_time: '09:00',
  end_time: '17:00',
  effective_from: '',
  effective_until: '',
  auto_extend: false,
  period: '',
};

const EMPTY_EXC = {
  exception_date: '',
  exception_type: 'day_off',
  start_time: '',
  end_time: '',
  reason: '',
};

/** Группировка плоских rules + breaks в серии по series_id. */
function buildSeries(rules, breaks) {
  const map = new Map();
  const keyFor = (sid, fallback) => sid || `legacy-${fallback}`;

  for (const r of rules) {
    const key = keyFor(r.series_id, `rule-${r.id}`);
    if (!map.has(key)) {
      map.set(key, {
        key,
        series_id: r.series_id,
        legacy_rule_id: r.series_id ? null : r.id,
        start_time: r.start_time,
        end_time: r.end_time,
        period: r.period,
        effective_from: r.effective_from,
        effective_until: r.effective_until,
        auto_extend: r.auto_extend,
        is_active: r.is_active,
        days: [],
        breaks: [],
      });
    }
    map.get(key).days.push(r.day_of_week);
  }

  for (const b of breaks) {
    if (!b.series_id || !map.has(b.series_id)) continue;
    const s = map.get(b.series_id);
    const dedupeKey = `${b.start_time}-${b.end_time}-${b.title || ''}`;
    if (!s.breaks.some(x => x._k === dedupeKey)) {
      s.breaks.push({
        _k: dedupeKey,
        start_time: b.start_time,
        end_time: b.end_time,
        title: b.title,
      });
    }
  }

  return Array.from(map.values()).map(s => ({
    ...s,
    days: [...new Set(s.days)].sort((a, b) => a - b),
  }));
}

export default function SchedulePage() {
  const [psychologists, setPsychologists] = useState([]);
  const [psychId, setPsychId] = useState('');

  const [rules, setRules]   = useState([]);
  const [breaks, setBreaks] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  // Schedule (series) modal
  const [schedModal, setSchedModal] = useState(false);
  const [schedForm, setSchedForm]   = useState(EMPTY_SCHEDULE);
  const [schedBreaks, setSchedBreaks] = useState([]);
  const [savingSched, setSavingSched] = useState(false);
  const [schedErr, setSchedErr] = useState(null);
  const [editingSeriesId, setEditingSeriesId] = useState(null);
  const [editImpact, setEditImpact] = useState(0);

  // One-off changes (exceptions)
  const [exceptions, setExceptions] = useState([]);

  // Exception modal
  const [excModal, setExcModal] = useState(false);
  const [excForm, setExcForm]   = useState(EMPTY_EXC);
  const [savingExc, setSavingExc] = useState(false);
  const [excErr, setExcErr] = useState(null);
  const [excDone, setExcDone] = useState(false);

  // Load psychologists once
  useEffect(() => {
    (async () => {
      try {
        const data = await getSupervisorPsychologists();
        setPsychologists(data.items || data || []);
      } catch { /* ignore */ }
    })();
  }, []);

  const loadSchedule = useCallback(async (pid) => {
    if (!pid) { setRules([]); setBreaks([]); setExceptions([]); return; }
    setLoading(true);
    setError(null);
    try {
      const [r, b, ex] = await Promise.all([
        getScheduleRules({ psychologistId: pid, includeInactive: true }),
        getScheduleBreaks({ psychologistId: pid }),
        getScheduleExceptions({ psychologistId: pid }),
      ]);
      setRules(r.items || r || []);
      setBreaks(b.items || b || []);
      setExceptions(ex.items || ex || []);
    } catch (e) {
      setError(e.message || 'Ошибка загрузки');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadSchedule(psychId); }, [psychId, loadSchedule]);

  const psychOptions = psychologists.map(p => ({
    value: String(p.id),
    label: p.full_name || p.email,
  }));

  const series = useMemo(() => buildSeries(rules, breaks), [rules, breaks]);

  // ── Schedule series create ────────────────────────────────────────────────

  function openSched() {
    setEditingSeriesId(null);
    setEditImpact(0);
    setSchedForm(EMPTY_SCHEDULE);
    setSchedBreaks([]);
    setSchedErr(null);
    setSchedModal(true);
  }

  async function openEditSched(s) {
    setEditingSeriesId(s.series_id);
    setEditImpact(0);
    setSchedForm({
      days_of_week: s.days.map(String),
      start_time: s.start_time,
      end_time: s.end_time,
      effective_from: s.effective_from || '',
      effective_until: s.effective_until || '',
      auto_extend: !!s.auto_extend,
      period: s.period || '',
    });
    setSchedBreaks(
      (s.breaks || []).map(b => ({
        start_time: b.start_time,
        end_time: b.end_time,
        title: b.title || '',
      }))
    );
    setSchedErr(null);
    setSchedModal(true);
    // Предупреждение о будущих записях (не блокирует сохранение).
    try {
      const impact = await getScheduleImpact(s.series_id);
      setEditImpact(impact.future_appointments || 0);
    } catch { /* impact optional */ }
  }

  function addBreak() {
    setSchedBreaks(b => [...b, { start_time: '13:00', end_time: '14:00', title: '' }]);
  }
  function updateBreak(idx, field, value) {
    setSchedBreaks(b => b.map((br, i) => (i === idx ? { ...br, [field]: value } : br)));
  }
  function removeBreak(idx) {
    setSchedBreaks(b => b.filter((_, i) => i !== idx));
  }

  async function saveSched() {
    if (!psychId) { setSchedErr('Сначала выберите психолога'); return; }
    if (schedForm.days_of_week.length === 0) {
      setSchedErr('Выберите хотя бы один день недели'); return;
    }
    if (schedForm.start_time >= schedForm.end_time) {
      setSchedErr('Время начала должно быть раньше времени окончания'); return;
    }
    if (!schedForm.effective_from) {
      setSchedErr('Укажите дату начала действия'); return;
    }
    if (schedForm.auto_extend && !schedForm.effective_until) {
      setSchedErr('Для автопродления укажите дату «действует по»'); return;
    }
    for (const br of schedBreaks) {
      if (br.start_time >= br.end_time) {
        setSchedErr('У перерыва время начала должно быть раньше окончания'); return;
      }
    }
    setSavingSched(true);
    setSchedErr(null);
    const common = {
      days_of_week: schedForm.days_of_week.map(Number),
      start_time: schedForm.start_time,
      end_time: schedForm.end_time,
      effective_from: schedForm.effective_from,
      effective_until: schedForm.effective_until || null,
      auto_extend: schedForm.auto_extend,
      period: schedForm.period || null,
      breaks: schedBreaks.map(br => ({
        start_time: br.start_time,
        end_time: br.end_time,
        title: br.title || null,
      })),
    };
    try {
      if (editingSeriesId) {
        await updateSchedule(editingSeriesId, common);
      } else {
        await createSchedule({ psychologist_id: Number(psychId), ...common });
      }
      setSchedModal(false);
      loadSchedule(psychId);
    } catch (e) {
      setSchedErr(e.message || 'Ошибка сохранения');
    } finally {
      setSavingSched(false);
    }
  }

  // ── Series actions ────────────────────────────────────────────────────────

  async function handleExtend(s) {
    try {
      await extendSchedule(s.series_id, 1);
      loadSchedule(psychId);
    } catch (e) {
      alert(e.message || 'Не удалось продлить');
    }
  }

  async function handleDeactivate(s) {
    let count = 0;
    try {
      const impact = await getScheduleImpact(s.series_id);
      count = impact.future_appointments || 0;
    } catch { /* impact optional */ }
    const msg = count > 0
      ? `В периоде серии есть будущих записей: ${count}. Они НЕ будут удалены и продолжат занимать слоты. Деактивировать расписание?`
      : 'Деактивировать это расписание? Записи не удаляются.';
    if (!window.confirm(msg)) return;
    try {
      await deleteSchedule(s.series_id);
      loadSchedule(psychId);
    } catch (e) {
      alert(e.message || 'Не удалось деактивировать');
    }
  }

  async function handleRestore(s) {
    try {
      await restoreSchedule(s.series_id);
      loadSchedule(psychId);
    } catch (e) {
      alert(e.message || 'Не удалось восстановить');
    }
  }

  // ── One-off changes (exceptions) ──────────────────────────────────────────

  function openExc() {
    setExcForm(EMPTY_EXC);
    setExcErr(null);
    setExcDone(false);
    setExcModal(true);
  }

  const excNeedsTime = excForm.exception_type !== 'day_off';

  async function saveExc() {
    if (!psychId) { setExcErr('Сначала выберите психолога'); return; }
    if (!excForm.exception_date) { setExcErr('Укажите дату'); return; }
    if (excNeedsTime && (!excForm.start_time || !excForm.end_time)) {
      setExcErr('Для этого типа укажите время начала и окончания'); return;
    }
    if (excNeedsTime && excForm.start_time >= excForm.end_time) {
      setExcErr('Время начала должно быть раньше окончания'); return;
    }
    setSavingExc(true);
    setExcErr(null);
    try {
      await createScheduleException({
        psychologist_id: Number(psychId),
        exception_date: excForm.exception_date,
        exception_type: excForm.exception_type,
        start_time: excNeedsTime ? excForm.start_time : null,
        end_time: excNeedsTime ? excForm.end_time : null,
        reason: excForm.reason || null,
      });
      setExcDone(true);
      setExcForm(EMPTY_EXC);
      loadSchedule(psychId);
    } catch (e) {
      setExcErr(e.message || 'Ошибка сохранения');
    } finally {
      setSavingExc(false);
    }
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <div className={styles.labelTag}>Супервизор</div>
          <h1 className={styles.pageTitle}>Расписание <em>психологов</em></h1>
          <p className={styles.pageSub}>
            Рабочие окна сериями, перерывы и разовые изменения.
          </p>
        </div>
        <div className={styles.headerActions}>
          <Button type="button" variant="secondary" disabled={!psychId} onClick={openExc}>
            Разовое изменение
          </Button>
          <Button type="button" variant="primary" disabled={!psychId} onClick={openSched}>
            <Icon name="plus" size={14} /> Расписание
          </Button>
        </div>
      </div>

      <div className={styles.psychPicker}>
        <Select
          label="Психолог"
          placeholder="Выберите психолога"
          value={psychId}
          options={psychOptions}
          onChange={setPsychId}
        />
      </div>

      {!psychId && (
        <div className={styles.empty}>
          Выберите психолога, чтобы увидеть его расписание.
        </div>
      )}

      {psychId && loading && <div className={styles.empty}>Загрузка…</div>}
      {psychId && !loading && error && (
        <div className={styles.empty}>Ошибка загрузки: {error}</div>
      )}
      {psychId && !loading && !error && series.length === 0 && (
        <div className={styles.empty}>
          Нет расписания. Создайте первое расписание (серию).
        </div>
      )}

      {psychId && !loading && !error && series.length > 0 && (
        <div className={styles.seriesList}>
          {series.map(s => (
            <div
              key={s.key}
              className={s.is_active ? styles.seriesCard : `${styles.seriesCard} ${styles.seriesCardOff}`}
            >
              <div className={styles.seriesHead}>
                <div className={styles.seriesTitle}>
                  Рабочее окно
                </div>
                <div className={styles.seriesBadges}>
                  {s.auto_extend && <Badge tone="neutral">Автопродление</Badge>}
                  {s.is_active
                    ? <Badge tone="success">Активно</Badge>
                    : <Badge tone="neutral">Деактивировано</Badge>}
                </div>
              </div>

              <div className={styles.dayChips}>
                {s.days.map(d => (
                  <Badge key={d} tone="neutral">{DAY_SHORT[d]}</Badge>
                ))}
                <span className={styles.seriesTime}>
                  {s.start_time}–{s.end_time}
                </span>
              </div>

              <div className={styles.seriesMeta}>
                Действует: {s.effective_from}
                {s.effective_until ? ` — ${s.effective_until}` : ' — бессрочно'}
              </div>

              {s.period && PERIOD_LABEL[s.period] && (
                <div className={styles.seriesMeta}>
                  Период: {PERIOD_LABEL[s.period]}
                </div>
              )}

              {s.breaks.length > 0 && (
                <div className={styles.breaksLine}>
                  Перерывы:{' '}
                  {s.breaks.map((b, i) => (
                    <span key={b._k}>
                      {i > 0 ? ', ' : ''}
                      {b.start_time}–{b.end_time}
                      {b.title ? ` (${b.title})` : ''}
                    </span>
                  ))}
                </div>
              )}

              <div className={styles.seriesActions}>
                {s.series_id && (
                  <Button type="button" variant="ghost" size="sm" onClick={() => openEditSched(s)}>
                    Редактировать
                  </Button>
                )}
                {s.series_id && s.is_active && (
                  <>
                    <Button type="button" variant="ghost" size="sm" onClick={() => handleExtend(s)}>
                      Продлить на месяц
                    </Button>
                    <Button type="button" variant="ghost" size="sm" tone="danger" onClick={() => handleDeactivate(s)}>
                      Деактивировать
                    </Button>
                  </>
                )}
                {s.series_id && !s.is_active && (
                  <Button type="button" variant="secondary" size="sm" onClick={() => handleRestore(s)}>
                    Восстановить
                  </Button>
                )}
                {!s.series_id && (
                  <span className={styles.legacyHint}>Старое правило (без серии)</span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* One-off changes (exceptions) */}
      {psychId && !loading && !error && (
        <div className={styles.excSection}>
          <h2 className={styles.excSectionTitle}>Разовые изменения</h2>
          {exceptions.length === 0 ? (
            <div className={styles.empty}>
              Разовых изменений нет.
            </div>
          ) : (
            <div className={styles.excList}>
              {exceptions.map(ex => (
                <div key={ex.id} className={styles.excRow}>
                  <span className={styles.excDate}>{ex.exception_date}</span>
                  <Badge tone={EXCEPTION_TYPE_TONE[ex.exception_type] || 'neutral'}>
                    {EXCEPTION_TYPE_LABEL[ex.exception_type] || ex.exception_type}
                  </Badge>
                  {ex.start_time && ex.end_time && (
                    <span className={styles.excTime}>
                      {ex.start_time}–{ex.end_time}
                    </span>
                  )}
                  {ex.reason && <span className={styles.excReason}>{ex.reason}</span>}
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Schedule (series) modal */}
      <Modal open={schedModal} onClose={() => setSchedModal(false)} ariaLabel={editingSeriesId ? 'Редактирование расписания' : 'Новое расписание'} size="md">
        <div className={styles.modalBody}>
          <h2 className={styles.modalTitle}>
            {editingSeriesId ? 'Редактирование расписания' : 'Новое расписание'}
          </h2>
          <p className={styles.pageSub}>
            Рабочие окна психолога. Тип встречи выбирается при записи —
            здесь его указывать не нужно.
          </p>

          {editingSeriesId && editImpact > 0 && (
            <div className={styles.editNote}>
              В периоде серии есть будущих записей: {editImpact}. Они не будут
              удалены или перенесены.
            </div>
          )}

          <div className={styles.formField}>
            <span className={styles.formLabel}>Дни недели</span>
            <MultiSelect
              options={DAYS}
              value={schedForm.days_of_week}
              onChange={v => setSchedForm(f => ({ ...f, days_of_week: v }))}
              placeholder="Выберите дни"
            />
          </div>

          <div className={styles.formRow}>
            <div className={styles.formField}>
              <TimePicker
                label="Начало"
                value={schedForm.start_time}
                onChange={v => setSchedForm(f => ({ ...f, start_time: v }))}
              />
            </div>
            <div className={styles.formField}>
              <TimePicker
                label="Окончание"
                value={schedForm.end_time}
                onChange={v => setSchedForm(f => ({ ...f, end_time: v }))}
              />
            </div>
          </div>

          <div className={styles.formRow}>
            <div className={styles.formField}>
              <DateInput
                label="Действует с"
                value={schedForm.effective_from}
                onChange={v => setSchedForm(f => ({ ...f, effective_from: v }))}
              />
            </div>
            <div className={styles.formField}>
              <DateInput
                label="Действует по"
                value={schedForm.effective_until}
                onChange={v => setSchedForm(f => ({ ...f, effective_until: v }))}
              />
            </div>
          </div>

          <div className={styles.toggleRow}>
            <Toggle
              id="auto-extend"
              checked={schedForm.auto_extend}
              onChange={(checked) => setSchedForm(f => ({ ...f, auto_extend: checked }))}
              label="Ежемесячное автопродление"
            />
            <label htmlFor="auto-extend" className={styles.toggleLabel}>
              Ежемесячное автопродление (требует «действует по»)
            </label>
          </div>

          <div className={styles.formField}>
            <Select
              label="Период (необязательно)"
              value={schedForm.period}
              options={PERIOD_OPTIONS}
              onChange={v => setSchedForm(f => ({ ...f, period: v }))}
            />
          </div>

          <div className={styles.breaksEditor}>
            <div className={styles.breaksEditorHead}>
              <span className={styles.formLabel}>Повторяющиеся перерывы</span>
              <Button type="button" variant="ghost" size="sm" onClick={addBreak}>
                <Icon name="plus" size={13} /> Добавить
              </Button>
            </div>
            {schedBreaks.length === 0 && (
              <span className={styles.breaksHint}>Перерывов нет (например, обед 13:00–14:00).</span>
            )}
            {schedBreaks.map((br, idx) => (
              <div key={idx} className={styles.breakRow}>
                <TimePicker
                  value={br.start_time}
                  onChange={v => updateBreak(idx, 'start_time', v)}
                />
                <TimePicker
                  value={br.end_time}
                  onChange={v => updateBreak(idx, 'end_time', v)}
                />
                <input
                  className={styles.formInput}
                  type="text"
                  placeholder="Название (напр. Обед)"
                  value={br.title}
                  onChange={e => updateBreak(idx, 'title', e.target.value)}
                />
                <Button
                  type="button" variant="icon" size="sm" tone="danger"
                  aria-label="Удалить перерыв"
                  onClick={() => removeBreak(idx)}
                >
                  <Icon name="trash" size={14} />
                </Button>
              </div>
            ))}
          </div>

          {schedErr && <div className={styles.saveErr}>{schedErr}</div>}

          <div className={styles.modalActions}>
            <Button type="button" variant="secondary" onClick={() => setSchedModal(false)}>
              Отмена
            </Button>
            <Button type="button" variant="primary" disabled={savingSched} onClick={saveSched}>
              {savingSched
                ? 'Сохраняем…'
                : editingSeriesId ? 'Сохранить изменения' : 'Создать расписание'}
            </Button>
          </div>
        </div>
      </Modal>

      {/* One-off change modal */}
      <Modal open={excModal} onClose={() => setExcModal(false)} ariaLabel="Разовое изменение" size="md">
        <div className={styles.modalBody}>
          <h2 className={styles.modalTitle}>Разовое изменение</h2>
          <p className={styles.pageSub}>Блокировка, выходной или дополнительное окно на конкретную дату.</p>

          <div className={styles.formField}>
            <DateInput
              label="Дата"
              value={excForm.exception_date}
              onChange={v => setExcForm(f => ({ ...f, exception_date: v }))}
            />
          </div>

          <div className={styles.formField}>
            <Select
              label="Тип изменения"
              value={excForm.exception_type}
              options={EXCEPTION_TYPES}
              onChange={v => setExcForm(f => ({ ...f, exception_type: v }))}
            />
          </div>

          {excNeedsTime && (
            <div className={styles.formRow}>
              <div className={styles.formField}>
                <TimePicker
                  label="Начало"
                  value={excForm.start_time}
                  onChange={v => setExcForm(f => ({ ...f, start_time: v }))}
                />
              </div>
              <div className={styles.formField}>
                <TimePicker
                  label="Окончание"
                  value={excForm.end_time}
                  onChange={v => setExcForm(f => ({ ...f, end_time: v }))}
                />
              </div>
            </div>
          )}

          <div className={styles.formField}>
            <label className={styles.formLabel}>Причина (необязательно)</label>
            <input
              className={styles.formInput}
              type="text"
              value={excForm.reason}
              onChange={e => setExcForm(f => ({ ...f, reason: e.target.value }))}
              placeholder="Например: отпуск"
            />
          </div>

          {excDone && <div className={styles.okMsg}>Изменение добавлено.</div>}
          {excErr && <div className={styles.saveErr}>{excErr}</div>}

          <div className={styles.modalActions}>
            <Button type="button" variant="secondary" onClick={() => setExcModal(false)}>
              Закрыть
            </Button>
            <Button type="button" variant="primary" disabled={savingExc} onClick={saveExc}>
              {savingExc ? 'Сохраняем…' : 'Добавить'}
            </Button>
          </div>
        </div>
      </Modal>

    </div>
  );
}
