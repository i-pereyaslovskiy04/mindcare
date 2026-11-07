import { useId, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import TextField from '../../../components/UI/TextField/TextField';
import styles from './CampaignProfileStep.module.css';

/**
 * Кодовое слово ссылки (ТЗ редактора методик, этап 2, §6): анкета открывается
 * после верного слова. Регистр и лишние пробелы не важны (сверяет сервер).
 * notice — сообщение прежнего шага (например, слово сменилось при отправке).
 */
export default function CampaignCodeStep({ unlock, notice = null }) {
  const id = useId();
  const [code, setCode] = useState('');
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function handleSubmit(event) {
    event.preventDefault();
    if (!code.trim()) {
      setError('Введите кодовое слово');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      const ok = await unlock(code);
      if (!ok) setError('Неверное кодовое слово. Уточните его у организаторов.');
    } catch (err) {
      setError(err?.status === 429
        ? 'Слишком много попыток. Подождите несколько минут.'
        : 'Не удалось проверить слово. Проверьте соединение и попробуйте ещё раз.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <section className={styles.section} aria-labelledby={`${id}-h`}>
        <h2 id={`${id}-h`} className={styles.heading}>Кодовое слово</h2>
        {notice && <p className={styles.error} role="alert">{notice}</p>}
        <p>Организаторы сообщили кодовое слово для этого тестирования.</p>
        <TextField
          id={`${id}-code`}
          label="Кодовое слово"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          error={error}
          autoComplete="off"
          maxLength={200}
          appearance="field"
          required
        />
      </section>
      <div className={styles.actions}>
        <Button type="submit" disabled={busy}>{busy ? 'Проверка…' : 'Продолжить'}</Button>
      </div>
    </form>
  );
}
