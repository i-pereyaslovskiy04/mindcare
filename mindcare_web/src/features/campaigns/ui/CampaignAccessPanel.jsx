import { useId, useState } from 'react';
import {
  clearCampaignAccessCode, setCampaignAccessCode, setCampaignSchedule,
} from '../../../api/campaigns.api';
import Button from '../../../components/UI/Button/Button';
import DateTimeInput from '../../../components/UI/DateTimeInput';
import TextField from '../../../components/UI/TextField/TextField';
import { localToMskIso, mskIsoToLocal } from '../../../utils/datetime';
import styles from './CampaignAccessPanel.module.css';

/**
 * Сроки и кодовое слово ссылки кампании (ТЗ редактора методик, этап 2, §6).
 * Время — московское. Слово хранится на сервере только в виде хеша: после
 * сохранения его не показать — супервизор сообщает его участникам сам.
 * Карточка обновляется ответом backend (onChange), без оптимистичного успеха.
 */
export default function CampaignAccessPanel({ campaign, onChange }) {
  const id = useId();
  const [opensAt, setOpensAt] = useState(mskIsoToLocal(campaign.opens_at));
  const [closesAt, setClosesAt] = useState(mskIsoToLocal(campaign.closes_at));
  const [code, setCode] = useState('');
  const [busy, setBusy] = useState(null);
  const [scheduleError, setScheduleError] = useState(null);
  const [codeError, setCodeError] = useState(null);
  const [message, setMessage] = useState(null);

  async function run(name, action, setErr) {
    setBusy(name);
    setErr(null);
    setMessage(null);
    try {
      await action();
    } catch (err) {
      setErr(err?.message || 'Не удалось сохранить');
    } finally {
      setBusy(null);
    }
  }

  function saveSchedule(event) {
    event.preventDefault();
    if (opensAt && closesAt && opensAt >= closesAt) {
      setScheduleError('Начало должно быть раньше окончания');
      return;
    }
    run('schedule', async () => {
      onChange(await setCampaignSchedule(campaign.uuid, {
        opens_at: localToMskIso(opensAt), closes_at: localToMskIso(closesAt),
      }));
      setMessage(opensAt || closesAt ? 'Сроки сохранены' : 'Сроки сняты');
    }, setScheduleError);
  }

  function clearSchedule() {
    setOpensAt('');
    setClosesAt('');
    run('schedule', async () => {
      onChange(await setCampaignSchedule(campaign.uuid, { opens_at: null, closes_at: null }));
      setMessage('Сроки сняты');
    }, setScheduleError);
  }

  function saveCode(event) {
    event.preventDefault();
    const value = code.split(/\s+/).filter(Boolean).join(' ');
    if (value.length < 4 || value.length > 64) {
      setCodeError('От 4 до 64 символов');
      return;
    }
    run('code', async () => {
      onChange(await setCampaignAccessCode(campaign.uuid, value));
      setCode('');
      setMessage('Кодовое слово сохранено. Сообщите его участникам — повторно его не показать.');
    }, setCodeError);
  }

  function clearCode() {
    run('code', async () => {
      onChange(await clearCampaignAccessCode(campaign.uuid));
      setMessage('Кодовое слово снято — анкета открывается по одной ссылке');
    }, setCodeError);
  }

  return (
    <div className={styles.panel}>
      <form className={styles.block} onSubmit={saveSchedule} noValidate
        aria-labelledby={`${id}-sched`}>
        <h4 id={`${id}-sched`} className={styles.heading}>Сроки (время московское)</h4>
        <p className={styles.hint}>
          До начала участник увидит «Тестирование ещё не началось», после окончания
          ссылка перестанет принимать ответы. Пустое поле — без ограничения.
        </p>
        <div className={styles.row}>
          <DateTimeInput label="Начало" value={opensAt} onChange={setOpensAt}
            disabled={busy === 'schedule'} />
          <DateTimeInput label="Окончание" value={closesAt} onChange={setClosesAt}
            disabled={busy === 'schedule'} />
        </div>
        {scheduleError && <p className={styles.error} role="alert">{scheduleError}</p>}
        <div className={styles.actions}>
          <Button type="submit" loading={busy === 'schedule'}>Сохранить сроки</Button>
          {(campaign.opens_at || campaign.closes_at) && (
            <Button type="button" variant="ghost" onClick={clearSchedule}
              disabled={busy === 'schedule'}>
              Снять сроки
            </Button>
          )}
        </div>
      </form>

      <form className={styles.block} onSubmit={saveCode} noValidate
        aria-labelledby={`${id}-code`}>
        <h4 id={`${id}-code`} className={styles.heading}>Кодовое слово</h4>
        <p className={styles.hint}>
          {campaign.access_code_set
            ? 'Слово задано: участник вводит его перед анкетой. Можно сменить или снять.'
            : 'Необязательно. Если задать, участник вводит его перед анкетой. Регистр и лишние пробелы не важны.'}
        </p>
        <TextField
          label={campaign.access_code_set ? 'Новое кодовое слово' : 'Кодовое слово'}
          value={code}
          onChange={(e) => { setCode(e.target.value); setCodeError(null); }}
          error={codeError}
          autoComplete="off"
          maxLength={200}
          appearance="field"
        />
        <div className={styles.actions}>
          <Button type="submit" loading={busy === 'code'}>
            {campaign.access_code_set ? 'Сменить слово' : 'Задать слово'}
          </Button>
          {campaign.access_code_set && (
            <Button type="button" variant="ghost" onClick={clearCode}
              disabled={busy === 'code'}>
              Снять слово
            </Button>
          )}
        </div>
      </form>
      <div aria-live="polite" className={styles.message}>{message}</div>
    </div>
  );
}
