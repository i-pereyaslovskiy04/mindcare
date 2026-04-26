import { useRef, useCallback } from 'react';
import styles from '../styles/forgot-password.module.css';

export default function OTPInput({ value, onChange, error }) {
  const refs = useRef([]);

  const handleChange = useCallback((idx, e) => {
    const ch = e.target.value.replace(/\D/g, '').slice(-1);
    const next = [...value];
    next[idx] = ch;
    onChange(next);
    if (ch && idx < 5) refs.current[idx + 1]?.focus();
  }, [value, onChange]);

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
    if (e.key === 'ArrowRight' && idx < 5) {
      e.preventDefault();
      refs.current[idx + 1]?.focus();
    }
  }, [value, onChange]);

  const handlePaste = useCallback((idx, e) => {
    e.preventDefault();
    const text = e.clipboardData.getData('text').replace(/\D/g, '').slice(0, 6);
    if (!text) return;
    const next = [...value];
    text.split('').forEach((ch, i) => {
      if (idx + i < 6) next[idx + i] = ch;
    });
    onChange(next);
    const focusIdx = Math.min(idx + text.length, 5);
    refs.current[focusIdx]?.focus();
  }, [value, onChange]);

  return (
    <div className={styles.otp} role="group" aria-label="Код подтверждения">
      {value.map((digit, idx) => (
        <input
          key={idx}
          ref={el => { refs.current[idx] = el; }}
          className={`${styles.otpBox} ${digit ? styles.otpFilled : ''} ${error ? styles.otpError : ''}`}
          type="text"
          inputMode="numeric"
          maxLength={1}
          value={digit}
          onChange={e => handleChange(idx, e)}
          onKeyDown={e => handleKeyDown(idx, e)}
          onPaste={e => handlePaste(idx, e)}
          autoComplete={idx === 0 ? 'one-time-code' : 'off'}
          aria-label={`Цифра ${idx + 1}`}
        />
      ))}
    </div>
  );
}
