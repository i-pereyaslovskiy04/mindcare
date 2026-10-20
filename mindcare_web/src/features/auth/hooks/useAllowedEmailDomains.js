import { useCallback, useEffect, useRef, useState } from 'react';
import { emailDomainNamesOf, getPublicEmailDomains } from '../../../api/domains.api';

const LOAD_ERROR_MESSAGE = 'Не удалось загрузить список разрешённых доменов';

/**
 * Активные домены регистрации по email — только для подсказки формы.
 * Контракт: { data, loading, error, refetch }.
 *
 * data — string[] из ответа backend (на клиенте ничего не зашито): пусто, пока
 * список не получен, если backend ответил пустым списком или запрос упал — тогда
 * подсказка просто не показывается, а форма работает независимо. Решение о
 * допуске принимает backend; этот список его не заменяет.
 *
 * Гонки: «побеждает последний запрос». Каждый запрос получает номер; ответ или
 * ошибка применяются, только если за это время не стартовал более новый запрос
 * и хук не размонтирован. Запоздавший ответ старого запроса (в том числе после
 * refetch) не перезапишет более свежий список и не выставит ошибку поверх него.
 */
export default function useAllowedEmailDomains() {
  const [data, setData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const latestRequest = useRef(0);

  const refetch = useCallback(() => {
    const requestId = latestRequest.current + 1;
    latestRequest.current = requestId;
    const isLatest = () => latestRequest.current === requestId;

    setLoading(true);
    setError(null);
    return getPublicEmailDomains()
      .then((response) => {
        if (isLatest()) setData(emailDomainNamesOf(response));
      })
      .catch((err) => {
        if (!isLatest()) return;
        setData([]);
        setError(err?.message || LOAD_ERROR_MESSAGE);
      })
      .finally(() => {
        if (isLatest()) setLoading(false);
      });
  }, []);

  useEffect(() => {
    refetch();
    // Размонтирование (и повторный запуск эффекта в StrictMode) обесценивает
    // запросы «в полёте»: их ответы больше не применяются.
    return () => { latestRequest.current += 1; };
  }, [refetch]);

  return { data, loading, error, refetch };
}
