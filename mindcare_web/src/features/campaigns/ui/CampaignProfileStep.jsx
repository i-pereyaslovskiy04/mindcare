import { useId } from 'react';
import Button from '../../../components/UI/Button/Button';
import Checkbox from '../../../components/UI/Checkbox/Checkbox';
import Select from '../../../components/UI/Select/Select';
import TextField from '../../../components/UI/TextField/TextField';
import { AGE_MAX, AGE_MIN } from '../lib/draft';
import styles from './CampaignProfileStep.module.css';

const GENDER_OPTIONS = [
  { value: 'female', label: 'Женский' },
  { value: 'male', label: 'Мужской' },
];

// Порядок полей — порядок фокуса на первой ошибке.
const FIELD_ORDER = ['fullName', 'facultyCode', 'specialty', 'age', 'gender', 'consent'];

/**
 * Шаг 1: анкета (ФИО, факультет, специальность, возраст, пол) и согласие на
 * обработку ПДн. «Перейти к вопросам» проверяет поля; при ошибке фокус — на
 * первом ошибочном поле.
 */
export default function CampaignProfileStep({ campaign, form }) {
  const baseId = useId();
  const ids = Object.fromEntries(FIELD_ORDER.map((f) => [f, `${baseId}-${f}`]));
  const consentTextId = `${baseId}-consent-text`;
  const consentErrorId = `${baseId}-consent-error`;
  const { draft, errors, setField } = form;
  const faculties = campaign.faculties.map((f) => ({ value: f.code, label: f.label }));

  function handleNext(event) {
    event.preventDefault();
    const found = form.goToQuestions();
    const first = FIELD_ORDER.find((f) => found[f]);
    if (!first) {
      window.scrollTo?.({ top: 0 });
      return;
    }
    // Ошибки появятся после рендера — тогда фокус на первом ошибочном поле.
    setTimeout(() => document.getElementById(ids[first])?.focus(), 0);
  }

  return (
    <form className={styles.form} onSubmit={handleNext} noValidate>
      <section className={styles.section} aria-labelledby={`${baseId}-profile`}>
        <h2 id={`${baseId}-profile`} className={styles.heading}>О себе</h2>
        <TextField
          id={ids.fullName}
          label="Фамилия, имя, отчество"
          value={draft.fullName}
          onChange={(e) => setField('fullName', e.target.value)}
          error={errors.fullName}
          autoComplete="name"
          maxLength={255}
          appearance="field"
          required
        />
        <Select
          id={ids.facultyCode}
          label="Факультет"
          placeholder="Выберите факультет"
          value={draft.facultyCode}
          options={faculties}
          onChange={(v) => setField('facultyCode', v)}
          error={errors.facultyCode}
          appearance="field"
        />
        <TextField
          id={ids.specialty}
          label="Специальность (направление подготовки)"
          value={draft.specialty}
          onChange={(e) => setField('specialty', e.target.value)}
          error={errors.specialty}
          maxLength={255}
          appearance="field"
          required
        />
        <div className={styles.row}>
          <TextField
            id={ids.age}
            label="Возраст, полных лет"
            type="number"
            inputMode="numeric"
            min={AGE_MIN}
            max={AGE_MAX}
            value={draft.age}
            onChange={(e) => setField('age', e.target.value)}
            error={errors.age}
            appearance="field"
            required
          />
          <Select
            id={ids.gender}
            label="Пол"
            placeholder="Выберите"
            value={draft.gender}
            options={GENDER_OPTIONS}
            onChange={(v) => setField('gender', v)}
            error={errors.gender}
            appearance="field"
          />
        </div>
      </section>

      <section className={styles.section} aria-labelledby={`${baseId}-consent-title`}>
        <h2 id={`${baseId}-consent-title`} className={styles.heading}>
          {campaign.consent.title}
        </h2>
        <div
          id={consentTextId}
          className={styles.consentText}
          tabIndex={0}
          role="region"
          aria-label="Текст согласия"
        >
          {campaign.consent.content}
        </div>
        <Checkbox
          id={ids.consent}
          checked={draft.consentAccepted}
          onChange={(checked) => setField('consentAccepted', checked)}
          label="Я прочитал(а) текст и даю согласие на обработку персональных данных"
          error={Boolean(errors.consent)}
          ariaDescribedBy={[consentTextId, errors.consent && consentErrorId]
            .filter(Boolean).join(' ')}
        />
        {errors.consent && (
          <p id={consentErrorId} className={styles.error} role="alert">{errors.consent}</p>
        )}
      </section>

      <div className={styles.actions}>
        <Button type="submit">Перейти к вопросам</Button>
      </div>
    </form>
  );
}
