import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import ButtonLink from '../../../components/UI/Button/ButtonLink';
import { useAuth } from '../AuthContext';
import {
  completeErrorMessage,
  fragmentMessage,
  parseCallbackFragment,
  scrubCallbackFragment,
} from '../lib/oauthCallback';
import styles from './OAuthCallbackPage.module.css';

/**
 * /auth/callback — завершение входа через внешний провайдер (Stage Social Auth 3B).
 *
 * Порядок — инвариант безопасности:
 *   1. синхронно (layout effect, до отрисовки) прочитать fragment и СРАЗУ
 *      убрать его из адреса/истории — ticket не ждёт окончания сети;
 *   2. только затем, когда AuthContext закончил восстановление сохранённой
 *      сессии (иначе его неудачный /me мог бы стереть новый токен), один раз
 *      обменять ticket на обычную сессию MindCare.
 *
 * Один ticket — один POST /oauth/complete, в том числе в React StrictMode:
 * повторный эффект видит уже вычищенный адрес и захваченное значение в ref.
 * Ticket не попадает ни в DOM, ни в логи, ни в storage, ни в navigation state.
 * После успеха — только `/dashboard` (кабинет выбирает DashboardRedirect);
 * адреса перехода из fragment не принимаются.
 */
export default function OAuthCallbackPage() {
  const { completeOAuthLogin, loading } = useAuth();
  const navigate = useNavigate();
  const captured = useRef(null);
  const started = useRef(false);
  const [error, setError] = useState('');

  useLayoutEffect(() => {
    if (captured.current !== null) return;
    captured.current = parseCallbackFragment(window.location.hash);
    scrubCallbackFragment();
    if (captured.current.kind !== 'login') {
      setError(fragmentMessage(captured.current));
    }
  }, []);

  useEffect(() => {
    if (loading || started.current) return;
    const current = captured.current;
    if (!current || current.kind !== 'login') return;

    started.current = true;
    const { ticket } = current;
    captured.current = { kind: 'consumed' };   // ticket больше не держим

    completeOAuthLogin(ticket)
      .then(() => navigate('/dashboard', { replace: true }))
      .catch((err) => setError(completeErrorMessage(err)));
  }, [loading, completeOAuthLogin, navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.logo}>MindCare</div>
          <p className={styles.subtitle}>Психологическая служба ДонГУ</p>
        </div>

        <div className={styles.body}>
          {error ? (
            <>
              <p className={styles.error} role="alert">{error}</p>
              <ButtonLink to="/login" className={styles.action}>
                Вернуться ко входу
              </ButtonLink>
            </>
          ) : (
            <p className={styles.status} role="status">Выполняется вход…</p>
          )}
        </div>
      </div>
    </div>
  );
}
