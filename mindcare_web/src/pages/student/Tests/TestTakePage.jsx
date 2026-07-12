import { useState, useEffect, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Button from '../../../components/UI/Button/Button';
import QuestionRenderer from './components/QuestionRenderer';
import ConsentGate from './components/ConsentGate';
import {
  getTestForTake,
  getTestConsent,
  acceptTestConsent,
  submitTest,
} from '../../../api/tests.api';
import styles from './TestTakePage.module.css';

function isAnswered(type, value) {
  if (type === 'single_choice') return value != null;
  if (type === 'multiple_choice') return Array.isArray(value) && value.length > 0;
  if (type === 'scale') return value != null;
  if (type === 'free_text') return typeof value === 'string' && value.trim().length > 0;
  return false;
}

function buildAnswer(question, value) {
  const base = { question_id: question.id };
  switch (question.question_type) {
    case 'single_choice':   return { ...base, option_id: value };
    case 'multiple_choice': return { ...base, selected_options: value };
    case 'scale':           return { ...base, scale_value: value };
    case 'free_text':       return { ...base, free_text_answer: value };
    default:                return base;
  }
}

export default function TestTakePage() {
  const { uuid } = useParams();
  const navigate = useNavigate();

  const [test, setTest]       = useState(null);
  const [consent, setConsent] = useState(null);
  const [answers, setAnswers] = useState({});       // { [questionId]: value }
  const [invalid, setInvalid] = useState([]);       // question ids missing required
  const [loading, setLoading] = useState(true);
  const [error, setError]     = useState(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    setError(null);
    Promise.all([getTestConsent(), getTestForTake(uuid)])
      .then(([c, t]) => {
        if (!alive) return;
        setConsent(c);
        setTest(t);
      })
      .catch((err) => { if (alive) setError(err.message); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [uuid]);

  const onAccept = useCallback(async () => {
    const updated = await acceptTestConsent();
    setConsent(updated);
  }, []);

  const setAnswer = useCallback((qid, value) => {
    setAnswers((prev) => ({ ...prev, [qid]: value }));
    setInvalid((prev) => prev.filter((id) => id !== qid));
  }, []);

  const answeredCount = (test?.questions ?? []).filter(
    (q) => isAnswered(q.question_type, answers[q.id]),
  ).length;

  const submit = async () => {
    const missing = test.questions
      .filter((q) => q.is_required && !isAnswered(q.question_type, answers[q.id]))
      .map((q) => q.id);

    if (missing.length) {
      setInvalid(missing);
      const el = document.getElementById(`q-${missing[0]}`);
      el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    const payload = test.questions
      .filter((q) => isAnswered(q.question_type, answers[q.id]))
      .map((q) => buildAnswer(q, answers[q.id]));

    setSubmitting(true);
    setError(null);
    try {
      const result = await submitTest(uuid, payload);
      navigate(`/student/tests/results/${result.uuid}`, { replace: true });
    } catch (err) {
      setError(err.message || 'Не удалось отправить ответы');
      setSubmitting(false);
    }
  };

  if (loading) return <div className={styles.page}><p className={styles.muted}>Загрузка…</p></div>;

  if (error && !test) {
    return (
      <div className={styles.page}>
        <button className={styles.back} type="button" onClick={() => navigate('/student/tests/catalog')}>
          <Icon name="chevron-left" size={14} /> К каталогу
        </button>
        <p className={styles.error}>{error}</p>
      </div>
    );
  }

  // ФЗ-152: пока согласие не принято — показываем плашку, вопросы скрыты.
  if (consent && !consent.accepted) {
    return (
      <div className={styles.page}>
        <button className={styles.back} type="button" onClick={() => navigate('/student/tests/catalog')}>
          <Icon name="chevron-left" size={14} /> К каталогу
        </button>
        <ConsentGate consent={consent} onAccept={onAccept} />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <button className={styles.back} type="button" onClick={() => navigate('/student/tests/catalog')}>
        <Icon name="chevron-left" size={14} /> К каталогу
      </button>

      <div className={styles.labelTag}>Прохождение теста</div>
      <h1 className={styles.pageTitle}>{test.title}</h1>
      {test.description && <p className={styles.pageSub}>{test.description}</p>}

      {/* Текстовый эквивалент прогресса (ГОСТ Р 52872-2019): не только полоса */}
      <p className={styles.progress} role="status" aria-live="polite">
        Отвечено {answeredCount} из {test.questions.length} вопросов
      </p>

      <div className={styles.questions}>
        {test.questions.map((q, i) => (
          <div id={`q-${q.id}`} key={q.id}>
            <QuestionRenderer
              question={q}
              index={i}
              total={test.questions.length}
              value={answers[q.id]}
              onChange={(v) => setAnswer(q.id, v)}
              invalid={invalid.includes(q.id)}
            />
          </div>
        ))}
      </div>

      {invalid.length > 0 && (
        <p className={styles.error}>Заполните обязательные вопросы (отмечены *).</p>
      )}
      {error && <p className={styles.error}>{error}</p>}

      <div className={styles.submitRow}>
        <Button variant="primary" loading={submitting} onClick={submit}>
          Завершить и узнать результат
        </Button>
      </div>
    </div>
  );
}
