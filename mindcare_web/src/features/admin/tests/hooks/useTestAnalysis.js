import { useState, useEffect, useRef } from 'react';
import { analyzeTest } from '../../../../api/tests.api';
import {
  SCORED_TYPES, toBackendQuestion, toBackendInterp, isQuestionComplete,
} from '../lib/testShape';

const DEBOUNCE_MS = 600;

/**
 * Анализ дерева теста на бэкенде: достижимый диапазон баллов и проблемы порогов.
 *
 * Считает бэкенд, а не фронт, намеренно: подсчёт живёт в app/tests/scoring.py,
 * и дублировать его в JS означало бы два источника правды — предупреждения
 * разошлись бы с реальным результатом студента.
 *
 * Запрос дебаунсится и не уходит, пока в дереве нет ни одного готового
 * скорящегося вопроса: иначе автор ловил бы предупреждения, ещё набирая первый.
 *
 * analyzeFn — какой backend-эндпоинт считает (admin `/admin/tests/analyze` по
 * умолчанию; psychologist передаёt `analyzeMyTest` → `/psychologist/tests/analyze`
 * — тот же service.analyze_test на бэке, другой роут ради ownership-изоляции).
 *
 * @returns { data, loading, error } — data: { score_bounds, issues } | null
 */
export function useTestAnalysis({ scoring, questions, interpretations, analyzeFn = analyzeTest }) {
  const [data, setData]       = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError]     = useState(null);

  // Сериализуем до useEffect: массивы пересоздаются на каждый рендер формы.
  const ready = questions.filter(
    (q) => SCORED_TYPES.includes(q.question_type) && isQuestionComplete(q),
  );
  const payload = ready.length
    ? JSON.stringify({
      scoring,
      questions: questions.filter(isQuestionComplete).map(toBackendQuestion),
      interpretations: interpretations
        .filter((it) => it.label.trim())
        .map(toBackendInterp),
    })
    : null;

  const seqRef = useRef(0);

  useEffect(() => {
    if (!payload) { setData(null); setError(null); return undefined; }

    const seq = ++seqRef.current;
    setLoading(true);
    const timer = setTimeout(() => {
      analyzeFn(JSON.parse(payload))
        .then((result) => { if (seq === seqRef.current) { setData(result); setError(null); } })
        .catch((err) => { if (seq === seqRef.current) setError(err.message); })
        .finally(() => { if (seq === seqRef.current) setLoading(false); });
    }, DEBOUNCE_MS);

    return () => { clearTimeout(timer); };
    // eslint-disable-next-line react-hooks/exhaustive-deps -- analyzeFn стабилен по контракту вызова (module-level функция)
  }, [payload]);

  return { data, loading, error };
}
