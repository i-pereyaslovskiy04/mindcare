import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import { authEntryState } from '../lib/authEntry';
import {
  completeErrorMessage,
  fragmentMessage,
  fragmentTone,
  loginStatusMessage,
  parseCallbackFragment,
  recallOAuthProvider,
  scrubCallbackFragment,
} from '../lib/oauthCallback';
import styles from './OAuthCallbackPage.module.css';

/**
 * Явные состояния технического маршрута. Экранов регистрации здесь нет: ни
 * шаг email (SocialEmailStep), ни шаг кода (RegistrationOtpStep) на
 * `/auth/callback` не монтируются — они живут в AuthModal на главной.
 */
export const PHASE = Object.freeze({
  RESOLVING: 'resolving',                       // fragment ещё не разобран
  LOGIN_COMPLETING: 'loginCompleting',          // обмен login-ticket на сессию
  // Ticket регистрации передаётся в память приложения (AuthContext), затем
  // replace на главную, где регистрацию продолжает AuthModal.
  REGISTRATION_HANDOFF: 'registrationHandoff',
  COMPLETED: 'completed',                       // сессия есть, переход в кабинет
  // Терминальная ошибка: replace на главную, сообщение выводит AuthModal.
  ERROR: 'error',
});

/**
 * /auth/callback — ТЕХНИЧЕСКИЙ маршрут возврата от внешнего провайдера
 * (Stage Social Auth 3B/4, VK-1B). Своих форм и карточки у него нет:
 * канонический контейнер авторизации — главная `/` + AuthModal.
 *
 *   #result=login                    — identity уже привязана → обмен ticket на
 *                                      сессию → /dashboard (ни email, ни кода);
 *   #result=registration[&step=email]— identity новая → ticket регистрации
 *                                      передаётся в AuthContext (только память)
 *                                      → replace на `/` → AuthModal показывает
 *                                      шаг email (VK) и/или шаг кода;
 *   #error=…                         — replace на `/` + AuthModal «Вход» с
 *                                      фиксированным сообщением.
 *
 * Переходы:
 *   resolving ─login→ loginCompleting ─ok→ completed → /dashboard
 *             ─registration→ registrationHandoff → `/` (AuthModal)
 *             ─иначе→ error → `/` (AuthModal «Вход» + сообщение)
 *
 * Инварианты безопасности:
 *   1. fragment читается и СРАЗУ вычищается из адреса/истории синхронно
 *      (layout effect, до первой отрисовки) — ticket не ждёт сети;
 *   2. вход начинается только когда AuthContext закончил восстановление
 *      сохранённой сессии (иначе его неудачный /me мог бы стереть новый токен);
 *   3. один ticket — один POST /oauth/complete либо одна передача в
 *      AuthContext и один переход, в том числе в React StrictMode (флаги в ref);
 *   4. ticket регистрации уходит на главную ТОЛЬКО через память приложения
 *      (AuthContext.beginSocialRegistration): не через URL, router state,
 *      localStorage или sessionStorage. Перезагрузка его теряет;
 *   5. после успеха входа — только `/dashboard`; адреса из fragment не
 *      принимаются;
 *   6. терминальные ошибки показывает AuthModal на главной (router state):
 *      только фиксированные тексты из lib/oauthCallback.
 */
export default function OAuthCallbackPage() {
  const { completeOAuthLogin, beginSocialRegistration, loading } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({ phase: PHASE.RESOLVING });
  // Через кого начинали вход (имя из sessionStorage, его пишет кнопка) — только для текстов.
  const [provider] = useState(recallOAuthProvider);
  const ticketRef = useRef(null);
  const resolved = useRef(false);
  const loginStarted = useRef(false);
  const left = useRef(false);

  // 1. Разбор и немедленная очистка fragment — до отрисовки.
  useLayoutEffect(() => {
    if (resolved.current) return;
    resolved.current = true;
    const parsed = parseCallbackFragment(window.location.hash);
    scrubCallbackFragment();
    if (parsed.kind === 'login') {
      ticketRef.current = parsed.ticket;
      setState({ phase: PHASE.LOGIN_COMPLETING });
    } else if (parsed.kind === 'registration') {
      ticketRef.current = parsed.ticket;
      setState({ phase: PHASE.REGISTRATION_HANDOFF, emailStep: parsed.emailStep });
    } else {
      setState({
        phase: PHASE.ERROR,
        message: fragmentMessage(parsed, provider),
        tone: fragmentTone(parsed),
      });
    }
  }, [provider]);

  // 2a. Вход: ровно один complete, после восстановления сессии AuthContext.
  useEffect(() => {
    if (state.phase !== PHASE.LOGIN_COMPLETING || loading || loginStarted.current) return;
    loginStarted.current = true;
    const ticket = ticketRef.current;
    ticketRef.current = null;   // ticket больше не держим
    completeOAuthLogin(ticket)
      .then(() => {
        setState({ phase: PHASE.COMPLETED });
        navigate('/dashboard', { replace: true });
      })
      .catch((err) => setState({
        phase: PHASE.ERROR, message: completeErrorMessage(err, provider), tone: 'error',
      }));
  }, [state.phase, loading, completeOAuthLogin, navigate, provider]);

  // 2b. Регистрация: ticket — в память приложения, страница — на главную
  // (replace: «назад» не возвращает на callback). В router state ничего нет.
  // Ровно одна передача и один переход.
  useEffect(() => {
    if (state.phase !== PHASE.REGISTRATION_HANDOFF || left.current) return;
    left.current = true;
    const ticket = ticketRef.current;
    ticketRef.current = null;   // здесь ticket больше не держим
    beginSocialRegistration({ ticket, provider, emailStep: state.emailStep });
    navigate('/', { replace: true });
  }, [state, beginSocialRegistration, navigate, provider]);

  // 3. Терминальная ошибка → главная + AuthModal «Вход» с сообщением (replace).
  // Ровно один переход.
  useEffect(() => {
    if (state.phase !== PHASE.ERROR || left.current) return;
    left.current = true;
    ticketRef.current = null;
    navigate('/', {
      replace: true, state: authEntryState('login', state.message, state.tone),
    });
  }, [state, navigate]);

  const signingIn = state.phase === PHASE.LOGIN_COMPLETING || state.phase === PHASE.COMPLETED;

  // Только нейтральный статус на время обмена ticket входа; в остальных фазах
  // страница пуста — она тут же уходит на главную.
  return (
    <div className={styles.page} aria-busy={signingIn ? undefined : 'true'}>
      {signingIn && (
        <p className={styles.status} role="status">{loginStatusMessage(provider)}</p>
      )}
    </div>
  );
}
