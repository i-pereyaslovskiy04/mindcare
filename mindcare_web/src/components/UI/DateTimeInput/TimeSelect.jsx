import { useMemo } from 'react';
import Select from '../Select/Select';
import { buildTimeOptions } from '../../../utils/datetime';

/**
 * @deprecated Используйте shared `components/UI/TimePicker` — он поддерживает
 * ручной ввод + popover-грид часов/минут. TimeSelect (Select-based dropdown)
 * оставлен только для обратной совместимости и не используется в новых формах.
 *
 * Выбор времени 'HH:MM' на базе shared Select (без native <input type="time">).
 * Если текущее value не попадает в сетку шага, оно всё равно добавляется в
 * список как выбираемая опция (чтобы редактирование не теряло значение).
 *
 * Props: value, onChange, label?, placeholder?, disabled?, error?,
 *        minuteStep=15, className?, style?
 */
export default function TimeSelect({
  value = '',
  onChange,
  label,
  placeholder = 'чч:мм',
  disabled = false,
  error,
  minuteStep = 15,
  className,
  style,
}) {
  const options = useMemo(() => {
    const opts = buildTimeOptions(minuteStep);
    if (value && !opts.some((o) => o.value === value)) {
      opts.unshift({ value, label: value });
    }
    return opts;
  }, [minuteStep, value]);

  return (
    <Select
      label={label}
      placeholder={placeholder}
      value={value}
      options={options}
      onChange={onChange}
      disabled={disabled}
      error={error}
      className={className}
      style={style}
    />
  );
}
