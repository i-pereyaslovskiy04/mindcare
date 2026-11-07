import { useCallback, useEffect, useRef, useState } from 'react';
import { getPublicCampaign, unlockPublicCampaign } from '../../../api/campaigns.api';

/**
 * Анкета кампании по токену ссылки (без входа). Контракт: { data, loading,
 * error, refetch, accessCode, unlock, forgetCode }.
 *
 * error — { status, message, code, opensAt }: 404 — ссылка недействительна
 * или опрос завершён; 409 campaign_not_started — ещё не началось (opensAt).
 * Кодовое слово (если задано): GET отдаёт «замок», unlock(code) открывает
 * анкету и запоминает слово в памяти вкладки (не в storage) — для повторной
 * загрузки и отправки. Неверное слово — unlock возвращает false.
 * Запоздалый ответ прежнего токена отбрасывается.
 */
export default function usePublicCampaign(token) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [accessCode, setAccessCode] = useState(null);
  const generation = useRef(0);
  const codeRef = useRef(null);

  const fail = (err) => {
    setData(null);
    setError({
      status: err?.status ?? null,
      message: err?.message || '',
      code: err?.code || null,
      opensAt: err?.body?.opens_at || null,
    });
  };

  const load = useCallback(() => {
    const current = ++generation.current;
    setLoading(true);
    setError(null);
    const request = codeRef.current
      ? unlockPublicCampaign(token, codeRef.current)
      : getPublicCampaign(token);
    return request
      .then((response) => {
        if (current !== generation.current) return;
        setData(response);
      })
      .catch((err) => {
        if (current !== generation.current) return;
        if (err?.status === 403 && codeRef.current) {
          // слово сменили — вернуть «замок»
          codeRef.current = null;
          setAccessCode(null);
          setLoading(false);
          load();
          return;
        }
        fail(err);
      })
      .finally(() => {
        if (current === generation.current) setLoading(false);
      });
  }, [token]);

  useEffect(() => {
    codeRef.current = null;
    setAccessCode(null);
    load();
    return () => { generation.current += 1; };
  }, [load]);

  /** true — анкета открыта; false — неверное слово; иные ошибки — throw. */
  const unlock = useCallback(async (code) => {
    const current = ++generation.current;
    try {
      const response = await unlockPublicCampaign(token, code);
      if (current !== generation.current) return false;
      codeRef.current = code;
      setAccessCode(code);
      setData(response);
      return true;
    } catch (err) {
      if (err?.status === 403) return false;
      if (err?.status === 404 || err?.status === 409) {
        if (current === generation.current) fail(err);
        return false;
      }
      throw err;
    }
  }, [token]);

  /** Слово отклонено при отправке (сменилось) — снова «замок». */
  const forgetCode = useCallback(() => {
    codeRef.current = null;
    setAccessCode(null);
    load();
  }, [load]);

  return { data, loading, error, refetch: load, accessCode, unlock, forgetCode };
}
