import { useState, useMemo } from 'react';
import Button from '../../../../components/UI/Button/Button';
import QuestionRenderer from '../../../tests/ui/QuestionRenderer';
import { previewScore } from '../../../../api/tests.api';
import {
  toPreviewQuestions, toPreviewAnswers, toBackendQuestion, toBackendInterp,
  isQuestionComplete,
} from '../lib/testShape';
import styles from './TestPreviewModal.module.css';

/**
 * Предпросмотр методики глазами студента + пробный подсчёт.
 *
 * До него единственным способом увидеть тест как студент была публикация в
 * живой каталог: student-эндпоинты закрыты require_role("student"), а выдача
 * для прохождения ещё и фильтрует is_active=true, так что черновик не
 * открывался даже с настоящего студенческого аккаунта.
 *
 * Рендерим тем же QuestionRenderer, что и TestTakePage, — иначе предпросмотр
 * со временем разойдётся с реальным прохождением. Баллы вариантов здесь не
 * показываются: студент их не видит (service._strip_take).
 *
 * Подсчёт считает бэкенд (POST /api/admin/tests/preview-score), ничего не
 * сохраняя: дублировать scoring в JS означало бы два источника правды.
 */
export default function TestPreviewModal({
  title, description, scoring, questions, interpretations, onClose,
  previewFn = previewScore,
}) {
  const previewQuestions = useMemo(() => toPreviewQuestions(questions), [questions]);
  const skipped = questions.length - previewQuestions.length;

  const [answers, setAnswers] = useState({});
  const [result, setResult]   = useState(null);
  const [scoringNow, setScoringNow] = useState(false);
  const [error, setError]     = useState('');

  const setAnswer = (qid, value) => {
    setAnswers((prev) => ({ ...prev, [qid]: value }));
    setResult(null);
  };

  async function runScore() {
    if (scoringNow) return;
    setScoringNow(true);
    setError('');
    try {
      const data = await previewFn({
        scoring,
        questions: questions.filter(isQuestionComplete).map(toBackendQuestion),
        interpretations: interpretations.filter((it) => it.label.trim()).map(toBackendInterp),
        answers: toPreviewAnswers(previewQuestions, answers),
      });
      setResult(data);
    } catch (err) {
      setError(err.message || 'Не удалось посчитать результат');
    } finally {
      setScoringNow(false);
    }
  }

  return (
    <div className={styles.overlay} onClick={onClose}>
      <div
        className={styles.dialog}
        role="dialog"
        aria-modal="true"
        aria-label="Предпросмотр теста"
        onClick={(e) => e.stopPropagation()}
      >
        <div className={styles.head}>
          <div>
            <span className={styles.badge}>Предпросмотр — так тест видит студент</span>
            <h2 className={styles.title}>{title || 'Без названия'}</h2>
            {description && <p className={styles.sub}>{description}</p>}
          </div>
          <Button variant="secondary" size="sm" onClick={onClose}>Закрыть</Button>
        </div>

        <div className={styles.body}>
          {previewQuestions.length === 0 ? (
            <p className={styles.muted}>
              Пока нечего показать: заполните текст вопроса и варианты ответа.
            </p>
          ) : (
            <>
              {skipped > 0 && (
                <p className={styles.note}>
                  Незаполненных вопросов пропущено: {skipped}. В предпросмотр
                  попадают только вопросы с текстом и заполненными вариантами.
                </p>
              )}
              {previewQuestions.map((q, i) => (
                <QuestionRenderer
                  key={q.id}
                  question={q}
                  index={i}
                  total={previewQuestions.length}
                  value={answers[q.id]}
                  onChange={(v) => setAnswer(q.id, v)}
                />
              ))}
            </>
          )}
        </div>

        {previewQuestions.length > 0 && (
          <div className={styles.footer}>
            <p className={styles.disclaimer}>
              Пробный прогон: ответы и результат никуда не сохраняются.
            </p>
            {error && <p className={styles.error}>{error}</p>}

            {result && (
              <div className={styles.result} role="status" aria-live="polite">
                {result.total_score != null && (
                  <p className={styles.score}>
                    Балл: <b>{result.total_score}</b>
                    {result.max_possible != null && <> из {result.max_possible}</>}
                  </p>
                )}
                {result.recommendations && (
                  <p className={styles.interp}>{result.recommendations}</p>
                )}
                {result.scales.length > 0 && (
                  <ul className={styles.scales}>
                    {result.scales.map((s) => (
                      <li key={s.scale_name}>
                        <b>{s.scale_name}</b>: {s.score}
                        {s.max_score != null && <> из {s.max_score}</>}
                        {s.label && <> — {s.label}</>}
                      </li>
                    ))}
                  </ul>
                )}
                {result.total_score == null && result.scales.length === 0 && (
                  <p className={styles.muted}>Подсчёт не дал результата.</p>
                )}
                {result.total_score != null && !result.recommendations && (
                  <p className={styles.warn}>
                    Для этого балла нет подходящего порога — студент увидит
                    результат без расшифровки.
                  </p>
                )}
              </div>
            )}

            <Button variant="primary" loading={scoringNow} onClick={runScore}>
              Посчитать результат
            </Button>
          </div>
        )}
      </div>
    </div>
  );
}
