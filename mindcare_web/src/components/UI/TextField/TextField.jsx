import { forwardRef, useId } from 'react';
import styles from './TextField.module.css';

/**
 * Подписанное текстовое поле (shared): label связан с input через htmlFor/id,
 * подсказка и ошибка — через aria-describedby, ошибка объявляется (role="alert")
 * и помечает поле aria-invalid. Остальные props (type, value, onChange,
 * maxLength, autoComplete, inputMode, readOnly, disabled, required, …)
 * передаются в <input>. ref указывает на <input> (фокус на первом ошибочном поле).
 * Переданный aria-describedby (например, общая ошибка формы) объединяется с
 * подсказкой и ошибкой поля, а не затирается.
 * appearance="field" — общая со Select коробка (border-box, min-height 40px, padding 9px,
 * line-height 1.4); по умолчанию вид прежний.
 */
const TextField = forwardRef(function TextField(
  {
    label, hint, error, id, className, inputClassName, appearance = 'default',
    'aria-describedby': describedByExtra, ...inputProps
  },
  ref,
) {
  const autoId = useId();
  const inputId = id ?? `${autoId}-input`;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [describedByExtra, hintId, errorId].filter(Boolean).join(' ') || undefined;

  return (
    <div className={[styles.field, className].filter(Boolean).join(' ')}>
      <label
        htmlFor={inputId}
        className={[styles.label, appearance === 'field' && styles.labelField].filter(Boolean).join(' ')}
      >
        {label}
      </label>
      <input
        {...inputProps}
        ref={ref}
        id={inputId}
        className={[
          styles.input,
          appearance === 'field' && styles.inputField,
          error && styles.inputError,
          inputClassName,
        ]
          .filter(Boolean).join(' ')}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={describedBy}
      />
      {hint && <span id={hintId} className={styles.hint}>{hint}</span>}
      {error && <span id={errorId} className={styles.error} role="alert">{error}</span>}
    </div>
  );
});

export default TextField;
