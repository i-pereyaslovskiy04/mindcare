import { useState } from 'react';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import styles from './ConsentGate.module.css';

/**
 * Плашка согласия ФЗ-152 перед прохождением тестов.
 * Показывается, когда consent.accepted === false. Текст политики — plain text
 * с бэкенда, рендерится через white-space (без dangerouslySetInnerHTML — не HTML).
 *
 * onAccept() — async; вызывает acceptTestConsent на бэкенде.
 */
export default function ConsentGate({ consent, onAccept }) {
  const [checked, setChecked] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState(null);

  const accept = async () => {
    setSubmitting(true);
    setError(null);
    try {
      await onAccept();
    } catch (err) {
      setError(err.message || 'Не удалось сохранить согласие');
      setSubmitting(false);
    }
  };

  return (
    <div className={styles.wrap}>
      <div className={styles.labelTag}>Защита персональных данных · ФЗ-152</div>
      <h1 className={styles.title}>{consent.title}</h1>

      <div className={styles.policy}>{consent.content}</div>

      <Checkbox
        checked={checked}
        onChange={setChecked}
        label="Я ознакомлен(а) с условиями и даю согласие на обработку персональных данных"
      />

      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.actions}>
        <Button variant="primary" disabled={!checked} loading={submitting} onClick={accept}>
          Принять и продолжить
        </Button>
      </div>
    </div>
  );
}
