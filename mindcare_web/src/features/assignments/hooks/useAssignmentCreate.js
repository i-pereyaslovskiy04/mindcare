import { useCallback, useRef, useState } from 'react';
import { createClientAssignment } from '../../../api/assignments.api';

const TEXT_ERRORS = {
  required: 'Введите текст задания.',
  too_long: 'Текст задания слишком длинный (не больше 4000 символов).',
  invalid_characters: 'Текст содержит недопустимые символы.',
};
const CREATE_FALLBACK = 'Не удалось создать задание. Проверьте соединение и повторите попытку.';
const AUDIT_UNAVAILABLE = 'Операция не зафиксирована в журнале и не выполнена. Повторите попытку позже.';

/**
 * Выдача задания клиенту (только создание, без чтения списка — список
 * заданий не запрашивается, чтение содержимого в журнал не пишется).
 * Используется разделом «Задания» карточки клиента и быстрым действием в
 * списке студентов.
 *
 * onCreated() — после успеха; onUnavailable() — 404 (сопровождение закрыто
 * или передано, клиент отключён). Двойная отправка исключена ref-lock'ом.
 * formError: { field: 'text' | 'material' | null, message }.
 */
export default function useAssignmentCreate(studentUuid, { onCreated, onUnavailable } = {}) {
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState(null);
  const lock = useRef(false);
  const callbacks = useRef({ onCreated, onUnavailable });
  callbacks.current = { onCreated, onUnavailable };

  const create = useCallback(async ({ text, dueDate, articleUuid }) => {
    if (lock.current) return false;
    lock.current = true;
    setSubmitting(true);
    setFormError(null);
    try {
      await createClientAssignment(studentUuid, { text, dueDate, articleUuid });
      callbacks.current.onCreated?.();
      return true;
    } catch (err) {
      const code = err?.body?.code || err?.code;
      if (err?.status === 422 && code === 'assignment_material_unavailable') {
        setFormError({ field: 'material', message: 'Материал недоступен: выберите опубликованный материал.' });
      } else if (err?.status === 422) {
        const textError = (err?.body?.errors || []).find(e => e.field === 'text');
        setFormError({
          field: textError ? 'text' : null,
          message: (textError && TEXT_ERRORS[textError.code]) || 'Проверьте поля задания.',
        });
      } else if (err?.status === 404) {
        setFormError({ field: null, message: 'Сопровождение недоступно: задание не создано.' });
        callbacks.current.onUnavailable?.();
      } else if (err?.status === 503) {
        setFormError({ field: null, message: AUDIT_UNAVAILABLE });
      } else {
        setFormError({ field: null, message: CREATE_FALLBACK });
      }
      return false;
    } finally {
      lock.current = false;
      setSubmitting(false);
    }
  }, [studentUuid]);

  const clearFormError = useCallback(() => setFormError(null), []);

  return { create, submitting, formError, clearFormError };
}
