import { useCallback, useEffect, useRef, useState } from 'react';
import { getStaffTestResult, getStaffTestResultAnswers } from '../../../api/tests.api';
import { isAccessLost } from './useStaffTestResults';

const EMPTY = { uuid: null, data: null, error: null, loading: false };

export const AUDIT_UNAVAILABLE =
  'Просмотр не удалось зафиксировать в журнале, поэтому данные не показаны. Повторите попытку позже.';
const DETAIL_FALLBACK = 'Не удалось загрузить результат. Повторите попытку.';
const ANSWERS_FALLBACK = 'Не удалось загрузить ответы. Повторите попытку.';

function messageFor(err, fallback) {
  return err?.status === 503 ? AUDIT_UNAVAILABLE : fallback;
}

/**
 * Раскрытый результат и его ответы (staff).
 *
 * Два поколения: openGen — открытие/закрытие результата, смена клиента или
 * роли; answersGen — загрузка/скрытие ответов. Ответ запроса принимается,
 * только если его поколения не изменились, поэтому запоздалый ответ прежнего
 * результата, клиента или роли не попадает в текущий. Деталь и ответы
 * хранятся вместе с uuid результата — наружу отдаются только для открытого.
 *
 * 403/404 детали или ответов — доступа больше нет: раскрытие и уже
 * загруженное содержимое очищаются, onAccessLost(err) сообщает списку.
 * 503 — чтение не зафиксировано в журнале: содержимого нет, только сообщение.
 */
export default function useStaffResultView(studentUuid, activeRole, { onAccessLost } = {}) {
  const [openUuid, setOpenUuid] = useState(null);
  const [detail, setDetail] = useState(EMPTY);
  const [answers, setAnswers] = useState(EMPTY);
  const openGen = useRef(0);
  const answersGen = useRef(0);
  const answersBusy = useRef(false);
  const onLostRef = useRef(onAccessLost);
  onLostRef.current = onAccessLost;

  const clear = useCallback(() => {
    openGen.current += 1;
    answersGen.current += 1;
    answersBusy.current = false;
    setOpenUuid(null);
    setDetail(EMPTY);
    setAnswers(EMPTY);
  }, []);

  // Смена клиента или роли (и размонтирование) — всё раскрытое очищается.
  useEffect(() => clear, [studentUuid, activeRole, clear]);

  const accessLost = useCallback((err) => {
    clear();
    onLostRef.current?.(err);
  }, [clear]);

  const toggle = useCallback((uuid) => {
    if (openUuid === uuid) {
      clear();
      return;
    }
    const gen = ++openGen.current;
    answersGen.current += 1;
    answersBusy.current = false;
    setOpenUuid(uuid);
    setDetail({ ...EMPTY, uuid, loading: true });
    setAnswers(EMPTY);
    getStaffTestResult(uuid, activeRole).then(
      (data) => {
        if (gen !== openGen.current) return;
        setDetail({ uuid, data, error: null, loading: false });
      },
      (err) => {
        if (gen !== openGen.current) return;
        if (isAccessLost(err)) { accessLost(err); return; }
        setDetail({ uuid, data: null, loading: false, error: messageFor(err, DETAIL_FALLBACK) });
      },
    );
  }, [openUuid, activeRole, clear, accessLost]);

  const loadAnswers = useCallback(() => {
    const uuid = openUuid;
    if (!uuid || answersBusy.current) return;
    const open = openGen.current;
    const gen = ++answersGen.current;
    const current = () => open === openGen.current && gen === answersGen.current;
    answersBusy.current = true;
    setAnswers({ ...EMPTY, uuid, loading: true });
    getStaffTestResultAnswers(uuid, activeRole).then(
      (data) => {
        if (!current()) return;
        answersBusy.current = false;
        setAnswers({ uuid, data, error: null, loading: false });
      },
      (err) => {
        if (!current()) return;
        answersBusy.current = false;
        if (isAccessLost(err)) { accessLost(err); return; }
        setAnswers({ uuid, data: null, loading: false, error: messageFor(err, ANSWERS_FALLBACK) });
      },
    );
  }, [openUuid, activeRole, accessLost]);

  const hideAnswers = useCallback(() => {
    answersGen.current += 1;      // летящий запрос ответов не вернёт их обратно
    answersBusy.current = false;
    setAnswers(EMPTY);
  }, []);

  return {
    openUuid,
    toggle,
    close: clear,
    detail: detail.uuid === openUuid ? detail : EMPTY,
    answers: answers.uuid === openUuid ? answers : EMPTY,
    loadAnswers,
    hideAnswers,
  };
}
