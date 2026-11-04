import { memo, useId } from 'react';
import Button from '../../../components/UI/Button/Button';
import styles from './CampaignQuestionsStep.module.css';

/**
 * Один вопрос — группа радиокнопок (fieldset/legend). Feature-specific:
 * в shared UI нет группы радиокнопок; крупные зоны нажатия «Да»/«Нет» нужны
 * для прохождения с телефона.
 */
const QuestionItem = memo(function QuestionItem({ question, value, missing, onAnswer }) {
  const name = `campaign-q-${question.id}`;
  return (
    <fieldset
      id={`campaign-question-${question.id}`}
      className={[styles.question, missing && styles.questionMissing].filter(Boolean).join(' ')}
      aria-invalid={missing ? 'true' : undefined}
    >
      <legend className={styles.legend}>
        <span className={styles.number}>{question.number}.</span> {question.text}
      </legend>
      <div className={styles.options}>
        {question.options.map((option) => (
          <label
            key={option.id}
            className={[styles.option, value === option.id && styles.optionChecked]
              .filter(Boolean).join(' ')}
          >
            <input
              type="radio"
              className={styles.radio}
              name={name}
              value={option.id}
              checked={value === option.id}
              onChange={() => onAnswer(question.id, option.id)}
            />
            <span>{option.text}</span>
          </label>
        ))}
      </div>
      {missing && <p className={styles.missingText}>Выберите ответ</p>}
    </fieldset>
  );
});

/** Шаг 2: все вопросы списком, прогресс, отправка. */
export default function CampaignQuestionsStep({ campaign, form }) {
  const progressId = useId();
  const total = campaign.questions.length;
  const answered = campaign.questions
    .filter((q) => q.options.some((o) => o.id === form.draft.answers[q.id])).length;
  const missing = new Set(form.missing);

  async function handleSubmit(event) {
    event.preventDefault();
    const firstMissing = await form.submit();
    if (firstMissing != null) {
      const el = document.getElementById(`campaign-question-${firstMissing}`);
      el?.scrollIntoView?.({ block: 'center' });
      el?.querySelector('input')?.focus({ preventScroll: true });
    }
  }

  return (
    <form className={styles.form} onSubmit={handleSubmit} noValidate>
      <p className={styles.instruction}>{campaign.instruction}</p>

      <div className={styles.progress}>
        <span id={progressId}>Отвечено {answered} из {total}</span>
        <progress
          className={styles.bar}
          max={total}
          value={answered}
          aria-labelledby={progressId}
        />
      </div>

      <div className={styles.list}>
        {campaign.questions.map((q) => (
          <QuestionItem
            key={q.id}
            question={q}
            value={form.draft.answers[q.id]}
            missing={missing.has(q.id)}
            onAnswer={form.setAnswer}
          />
        ))}
      </div>

      {form.submitError && (
        <p className={styles.error} role="alert">{form.submitError}</p>
      )}

      <div className={styles.actions}>
        <Button type="button" variant="secondary" onClick={form.backToProfile}
          disabled={form.submitting}>
          Назад к анкете
        </Button>
        <Button type="submit" loading={form.submitting}>Отправить ответы</Button>
      </div>
    </form>
  );
}
