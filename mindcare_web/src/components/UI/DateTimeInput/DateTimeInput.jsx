import { useEffect, useRef, useState } from 'react';
import DateInput from '../DateInput/DateInput';
import TimePicker from '../TimePicker/TimePicker';
import styles from './DateTimeInput.module.css';

/**
 * Дата + время одним контролом, собранным из shared-компонентов
 * (DateInput + TimePicker). Native datetime-local/time НЕ используются.
 *
 * Value — локальное московское «настенное» время 'YYYY-MM-DDTHH:MM' либо ''.
 * Конвертация в tz-aware ISO (localToMskIso) выполняется на стороне формы перед
 * отправкой в API — компонент хранит только локальную строку.
 *
 * Эмитит полную строку только когда заданы И дата, И время; иначе '' (чтобы
 * required-валидация в форме срабатывала на неполном вводе).
 *
 * Props: value, onChange, label?, minDate?, disabled?, error?, minuteStep=15
 */
function splitValue(v) {
  if (!v || typeof v !== 'string') return { date: '', time: '' };
  if (!v.includes('T')) {
    return { date: v.length >= 10 ? v.slice(0, 10) : '', time: '' };
  }
  const [d, t] = v.split('T');
  return { date: d || '', time: (t || '').slice(0, 5) };
}

export default function DateTimeInput({
  value = '',
  onChange,
  label,
  minDate,
  disabled = false,
  error,
  minuteStep = 15,
}) {
  const [dt, setDt] = useState(() => splitValue(value));
  // Запоминаем то, что сами отдали наверх, чтобы внешний value (наш же '')
  // не затирал наполовину заполненные дату/время. Реальный внешний reset/edit
  // (значение != последнего эмита) — пересинхронизирует поля.
  const lastEmitted = useRef(value);

  useEffect(() => {
    if (value === lastEmitted.current) return;
    setDt(splitValue(value));
    lastEmitted.current = value;
  }, [value]);

  function emit(nextDate, nextTime) {
    setDt({ date: nextDate, time: nextTime });
    const combined = nextDate && nextTime ? `${nextDate}T${nextTime}` : '';
    lastEmitted.current = combined;
    onChange?.(combined);
  }

  return (
    <div className={styles.wrap}>
      {label && <span className={styles.label}>{label}</span>}
      <div className={styles.row}>
        <div className={styles.dateCol}>
          <DateInput
            value={dt.date}
            onChange={(d) => emit(d, dt.time)}
            disabled={disabled}
            min={minDate}
          />
        </div>
        <div className={styles.timeCol}>
          <TimePicker
            value={dt.time}
            onChange={(t) => emit(dt.date, t)}
            disabled={disabled}
            minuteStep={minuteStep}
          />
        </div>
      </div>
      {error && <span className={styles.error} role="alert">{error}</span>}
    </div>
  );
}
