import { useRef, useCallback, useImperativeHandle } from 'react';
import styles from './CodeInput.module.css';

const LENGTH = 6;

/**
 * Шесть ячеек одноразового кода (массив из 6 строк по одной цифре).
 *
 * - disabled — во время проверки кода ячейки не редактируются;
 * - error — подсветка ячеек и aria-invalid; describedBy — id текста ошибки
 *   (связывается с ячейками только при error);
 * - ref — { focus() }: фокус на первую ячейку (открытие шага, после неверного
 *   кода);
 * - вставка и автозаполнение кода телефоном (iOS/Android кладут весь код в
 *   поле one-time-code) раскладывают цифры по ячейкам; полный код — всегда с
 *   первой ячейки. Нецифровые символы отбрасываются.
 */
export default function CodeInput({
  value, onChange, error, disabled = false, describedBy, ref,
}) {
  const refs = useRef([]);

  useImperativeHandle(ref, () => ({
    focus: () => refs.current[0]?.focus(),
  }), []);

  const fill = useCallback((idx, digits) => {
    const start = digits.length >= LENGTH ? 0 : idx;
    const next = [...value];
    digits.slice(0, LENGTH - start).split('').forEach((ch, i) => {
      next[start + i] = ch;
    });
    onChange(next);
    refs.current[Math.min(start + digits.length, LENGTH - 1)]?.focus();
  }, [value, onChange]);

  const handleChange = useCallback((idx, e) => {
    const digits = e.target.value.replace(/\D/g, '');
    const prev = value[idx];
    let ch = digits;
    if (digits.length === 2 && prev) {
      // Ввод поверх цифры в ячейке: новая — та, что не совпадает с прежней.
      ch = digits[0] === prev ? digits[1] : digits[0];
    } else if (digits.length > 1) {
      fill(idx, digits);
      return;
    }
    const next = [...value];
    next[idx] = ch;
    onChange(next);
    if (ch && idx < LENGTH - 1) refs.current[idx + 1]?.focus();
  }, [value, onChange, fill]);

  const handleKeyDown = useCallback((idx, e) => {
    if (e.key === 'Backspace') {
      if (!value[idx] && idx > 0) {
        e.preventDefault();
        const next = [...value];
        next[idx - 1] = '';
        onChange(next);
        refs.current[idx - 1]?.focus();
      }
    }
    if (e.key === 'ArrowLeft' && idx > 0) {
      e.preventDefault();
      refs.current[idx - 1]?.focus();
    }
    if (e.key === 'ArrowRight' && idx < LENGTH - 1) {
      e.preventDefault();
      refs.current[idx + 1]?.focus();
    }
  }, [value, onChange]);

  const handlePaste = useCallback((idx, e) => {
    e.preventDefault();
    const text = e.clipboardData.getData('text').replace(/\D/g, '');
    if (!text) return;
    fill(idx, text);
  }, [fill]);

  const invalid = Boolean(error);
  return (
    <div className={styles.otp} role="group" aria-label="Код подтверждения">
      {value.map((digit, idx) => (
        <input
          key={idx}
          ref={el => { refs.current[idx] = el; }}
          className={`${styles.otpBox} ${digit ? styles.otpFilled : ''} ${invalid ? styles.otpError : ''}`}
          type="text"
          inputMode="numeric"
          pattern="[0-9]*"
          value={digit}
          disabled={disabled}
          onChange={e => handleChange(idx, e)}
          onKeyDown={e => handleKeyDown(idx, e)}
          onPaste={e => handlePaste(idx, e)}
          // Набор поверх выделенной цифры заменяет её.
          onFocus={e => e.target.select()}
          autoComplete={idx === 0 ? 'one-time-code' : 'off'}
          aria-label={`Цифра ${idx + 1}`}
          aria-invalid={invalid ? 'true' : undefined}
          aria-describedby={invalid && describedBy ? describedBy : undefined}
        />
      ))}
    </div>
  );
}
