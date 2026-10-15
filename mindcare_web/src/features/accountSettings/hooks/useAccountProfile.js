import { useCallback, useEffect, useRef, useState } from 'react';
import * as authApi from '../../../api/auth.api';

const EMPTY = { full_name: '', email: '', phone: '', role: '', has_password: undefined };
const IDLE = { saving: false, error: '', success: false };

/**
 * Профиль текущего пользователя и независимые сохранения ФИО и телефона.
 * Каждое сохранение шлёт ТОЛЬКО свой ключ (`{full_name}` / `{phone}`), поэтому
 * устаревшее значение одного поля не затирает другое. ФИО и телефон не
 * логируются. `refreshUser` вызывается вне try сохранения: сбой обновления
 * шапки не должен выглядеть как сбой сохранения.
 */
export default function useAccountProfile({ refreshUser }) {
  const [profile, setProfile] = useState(EMPTY);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');
  const [nameState, setNameState] = useState(IDLE);
  const [phoneState, setPhoneState] = useState(IDLE);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setLoadError('');
      try {
        const data = await authApi.getProfile();
        if (cancelled) return;
        setProfile({
          full_name: data.full_name || '',
          email: data.email || '',
          phone: data.phone || '',
          role: data.role || '',
          has_password: data.has_password,
        });
      } catch (err) {
        if (!cancelled) setLoadError(err.message || 'Не удалось загрузить профиль');
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, []);

  const save = useCallback(async (payload, setState, apply, failure) => {
    setState({ saving: true, error: '', success: false });
    let updated;
    try {
      updated = await authApi.updateProfile(payload);
    } catch (err) {
      if (mounted.current) setState({ saving: false, error: err.message || failure, success: false });
      return false;
    }
    if (mounted.current) {
      setProfile((p) => ({ ...p, ...apply(updated) }));
      setState({ saving: false, error: '', success: true });
    }
    try {
      await refreshUser?.();
    } catch {
      // Сохранение прошло; шапка обновится при следующем запросе /me.
    }
    return true;
  }, [refreshUser]);

  const saveFullName = useCallback(
    (fullName) => save(
      { full_name: fullName },
      setNameState,
      (u) => ({ full_name: u.full_name || '' }),
      'Не удалось сохранить ФИО',
    ),
    [save],
  );

  const savePhone = useCallback(
    (phone) => save(
      { phone: phone || null },
      setPhoneState,
      (u) => ({ phone: u.phone || '' }),
      'Не удалось сохранить телефон',
    ),
    [save],
  );

  const resetNameFeedback = useCallback(() => setNameState(IDLE), []);
  const resetPhoneFeedback = useCallback(() => setPhoneState(IDLE), []);

  return {
    profile,
    loading,
    loadError,
    nameState,
    phoneState,
    saveFullName,
    savePhone,
    resetNameFeedback,
    resetPhoneFeedback,
  };
}
