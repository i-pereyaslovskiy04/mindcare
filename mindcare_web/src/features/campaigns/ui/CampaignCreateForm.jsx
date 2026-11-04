import { useEffect, useState } from 'react';
import { createCampaign } from '../../../api/campaigns.api';
import Button from '../../../components/UI/Button/Button';
import Select from '../../../components/UI/Select/Select';
import TextField from '../../../components/UI/TextField/TextField';
import useCampaignTests from '../hooks/useCampaignTests';
import styles from './CampaignCreateForm.module.css';

/** Новая кампания: название и тест (только тесты для кампаний). */
export default function CampaignCreateForm({ onCreated }) {
  const tests = useCampaignTests(true);
  const [title, setTitle] = useState('');
  const [testUuid, setTestUuid] = useState('');
  const [titleError, setTitleError] = useState(null);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (!testUuid && tests.data.length) setTestUuid(tests.data[0].value);
  }, [tests.data, testUuid]);

  async function handleSubmit(event) {
    event.preventDefault();
    const cleaned = title.split(/\s+/).filter(Boolean).join(' ');
    if (cleaned.length < 2) {
      setTitleError('Укажите название, например «1 курс, учётно-финансовый»');
      return;
    }
    if (!testUuid) return;
    setSaving(true);
    setError(null);
    try {
      const campaign = await createCampaign({ title: cleaned, test_uuid: testUuid });
      setTitle('');
      onCreated?.(campaign);
    } catch (err) {
      setError(err?.message || 'Не удалось создать кампанию');
    } finally {
      setSaving(false);
    }
  }

  const noTests = !tests.loading && !tests.error && !tests.data.length;

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <h2 className={styles.heading}>Новая кампания</h2>
      <div className={styles.fields}>
        <TextField
          label="Название"
          hint="Видят участники: например, группа или курс"
          value={title}
          onChange={(e) => { setTitle(e.target.value); setTitleError(null); }}
          error={titleError}
          maxLength={255}
          appearance="field"
        />
        <Select
          label="Методика"
          value={testUuid}
          options={tests.data}
          onChange={setTestUuid}
          disabled={tests.loading || !tests.data.length}
          placeholder={tests.loading ? 'Загрузка…' : 'Нет доступных методик'}
          appearance="field"
        />
      </div>
      {noTests && (
        <p className={styles.note}>
          Нет методик для кампаний. Загрузите ИТО командой
          {' '}<code>python scripts/seed_ito_sobchik.py</code>.
        </p>
      )}
      {(error || tests.error) && (
        <p className={styles.error} role="alert">{error || tests.error}</p>
      )}
      <div className={styles.actions}>
        <Button type="submit" loading={saving} disabled={!testUuid}>Создать</Button>
      </div>
    </form>
  );
}
