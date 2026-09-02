import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Icon from '../../../components/Icon/Icon';
import Button from '../../../components/UI/Button/Button';
import QuestionRenderer from '../../../features/tests/ui/QuestionRenderer';
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

function formatClock(sec) {
  const m = Math.floor(sec / 60);
  const s = sec % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
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
  const [stale, setStale]     = useState(false);   // тест изменился, пока его проходили
  const [submitting, setSubmitting] = useState(false);
  const [remaining, setRemaining] = useState(null); // секунды до конца (тайм-лимит)
  const [timerOn, setTimerOn] = useState(false);
  const deadlineRef = useRef(null);
  const timedOutRef = useRef(false);
  const submitRef = useRef(null);

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

  const submit = async (timedOut = false) => {
    if (submitting) return;

    // По таймауту не требуем обязательные — отправляем то, что успели ответить.
    if (!timedOut) {
      const missing = test.questions
        .filter((q) => q.is_required && !isAnswered(q.question_type, answers[q.id]))
        .map((q) => q.id);

      if (missing.length) {
        setInvalid(missing);
        const el = document.getElementById(`q-${missing[0]}`);
        el?.scrollIntoView({ behavior: 'smooth', block: 'center' });
        return;
      }
    }

    const payload = test.questions
      .filter((q) => isAnswered(q.question_type, answers[q.id]))
      .map((q) => buildAnswer(q, answers[q.id]));

    setSubmitting(true);
    setError(null);
    try {
      const result = await submitTest(uuid, payload, timedOut);
      navigate(`/student/tests/results/${result.uuid}`, { replace: true });
    } catch (err) {
      // Тест могли отредактировать, пока страница была открыта: id вопросов
      // устарели и бэкенд их не признаёт. Сообщение об «ответе не из этого
      // теста» студенту ничего не объясняет — предлагаем перезагрузить.
      if (err?.status === 422 && /не из этого теста/i.test(err.message || '')) {
        setStale(true);
      }
      setError(err.message || 'Не удалось отправить ответы');
      setSubmitting(false);
    }
  };

  // Всегда держим ссылку на актуальный submit — таймер должен видеть свежие ответы.
  submitRef.current = submit;

  // Старт тайм-лимита: один раз, когда тест загружен и согласие принято.
  useEffect(() => {
    const limit = Number(test?.time_limit_min) || 0;
    if (timerOn || !test || !consent?.accepted || limit <= 0) return;
    deadlineRef.current = Date.now() + limit * 60000;
    setRemaining(limit * 60);
    setTimerOn(true);
  }, [test, consent, timerOn]);

  // Тик раз в секунду; по достижении 0 — один авто-submit с флагом таймаута.
  useEffect(() => {
    if (!timerOn) return undefined;
    const id = setInterval(() => {
      const rem = Math.max(0, Math.round((deadlineRef.current - Date.now()) / 1000));
      setRemaining(rem);
      if (rem <= 0) {
        clearInterval(id);
        if (!timedOutRef.current) {
          timedOutRef.current = true;
          submitRef.current?.(true);
        }
      }
    }, 1000);
    return () => clearInterval(id);
  }, [timerOn]);

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

      {remaining != null && (
        <p
          className={[styles.timer, remaining <= 60 && styles.timerLow]
            .filter(Boolean).join(' ')}
          role="timer"
          aria-live="off"
        >
          <Icon name="clock" size={14} aria-hidden="true" /> Осталось времени:{' '}
          {formatClock(remaining)}
        </p>
      )}

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
      {error && !stale && <p className={styles.error}>{error}</p>}
      {stale && (
        <p className={styles.error} role="alert">
          Тест обновился, пока вы его проходили, — ответы отправить не удалось.
          Обновите страницу и пройдите тест заново.
        </p>
      )}

      <div className={styles.submitRow}>
        {stale ? (
          <Button variant="primary" onClick={() => window.location.reload()}>
            Обновить страницу
          </Button>
        ) : (
          <Button variant="primary" loading={submitting} onClick={() => submit()}>
            Завершить и узнать результат
          </Button>
        )}
      </div>
    </div>
  );
}
