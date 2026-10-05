import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { oauthRegistrationInit } from '../../../api/auth.api';
import { useAuth } from '../AuthContext';
import RegistrationOtpStep, {
  EMPTY_CODE, RESEND_COOLDOWN, useResendTimer,
} from '../ui/RegistrationOtpStep';
import authStyles from '../ui/AuthModal.module.css';
import { authEntryState } from '../lib/authEntry';
import {
  completeErrorMessage,
  fragmentMessage,
  fragmentTone,
  isRegistrationTerminal,
  parseCallbackFragment,
  registrationErrorMessage,
  scrubCallbackFragment,
} from '../lib/oauthCallback';
import styles from './OAuthCallbackPage.module.css';

/**
 * Явные состояния страницы. Шаг кода (RegistrationOtpStep) монтируется ТОЛЬКО
 * в REGISTRATION_OTP, а попасть туда можно только из REGISTRATION_INITIALIZING
 * после успешного init — то есть только для fragment `result=registration`.
 * Поток входа (`result=login`) этого состояния не достигает никогда.
 */
export const PHASE = Object.freeze({
  RESOLVING: 'resolving',                       // fragment ещё не разобран
  LOGIN_COMPLETING: 'loginCompleting',          // обмен login-ticket на сессию
  REGISTRATION_INITIALIZING: 'registrationInitializing',   // отправка кода
  REGISTRATION_OTP: 'registrationOtp',          // ввод кода
  COMPLETED: 'completed',                       // сессия есть, переход в кабинет
  // Терминальная ошибка: страница ничего не показывает и сразу (replace)
  // уводит на главную, где сообщение выводит AuthModal.
  ERROR: 'error',
});

const LOGIN_STATUS = 'Выполняем вход через Яндекс…';

// «← Начать заново» на шаге кода: главная + AuthModal «Регистрация».
const RESTART_REGISTRATION_STATE = Object.freeze({ openAuth: 'register' });

/**
 * /auth/callback — завершение входа или регистрации через внешний провайдер
 * (Stage Social Auth 3B/4). Что именно произойдёт, решил backend на callback:
 *   #result=login        — identity уже привязана → обмен ticket на сессию;
 *   #result=registration — identity новая → код уходит на email из профиля
 *                          Яндекса автоматически, затем шаг подтверждения;
 *   #error=…             — фиксированное сообщение.
 *
 * Переходы:
 *   resolving ─login──────→ loginCompleting ─ok→ completed → /dashboard
 *             ─registration→ registrationInitializing ─ok→ registrationOtp
 *                                                      ─ok→ completed → /dashboard
 *             ─error/invalid→ error;  сбой complete/init → error
 *   error → replace на `/` + AuthModal «Вход» с безопасным сообщением и тоном
 *           (router state openAuth/message/messageTone); своей карточки
 *           ошибки у callback нет
 *
 * Инварианты безопасности:
 *   1. fragment читается и СРАЗУ вычищается из адреса/истории синхронно
 *      (layout effect, до первой отрисовки) — ticket не ждёт сети;
 *   2. вход начинается только когда AuthContext закончил восстановление
 *      сохранённой сессии (иначе его неудачный /me мог бы стереть новый токен);
 *   3. один ticket — один POST /oauth/complete или один автоматический
 *      /oauth/registration/init, в том числе в React StrictMode (флаги в ref);
 *   4. ticket живёт только в памяти (ref/prop): не в DOM, логах, storage, URL и
 *      navigation state; перезагрузка его теряет;
 *   5. после успеха — только `/dashboard`; адреса из fragment не принимаются;
 *   6. терминальные ошибки показывает AuthModal на главной (router state):
 *      только фиксированные тексты из lib/oauthCallback — без текста
 *      провайдера, query, ticket, subject и email.
 */
export default function OAuthCallbackPage() {
  const { completeOAuthLogin, loading } = useAuth();
  const navigate = useNavigate();
  const [state, setState] = useState({ phase: PHASE.RESOLVING });
  const ticketRef = useRef(null);
  const resolved = useRef(false);
  const loginStarted = useRef(false);
  const initStarted = useRef(false);

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
      setState({ phase: PHASE.REGISTRATION_INITIALIZING });
    } else {
      setState({
        phase: PHASE.ERROR, message: fragmentMessage(parsed), tone: fragmentTone(parsed),
      });
    }
  }, []);

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
        phase: PHASE.ERROR, message: completeErrorMessage(err), tone: 'error',
      }));
  }, [state.phase, loading, completeOAuthLogin, navigate]);

  // 2b. Регистрация: ровно один автоматический init; шаг кода — только после успеха.
  useEffect(() => {
    if (state.phase !== PHASE.REGISTRATION_INITIALIZING || initStarted.current) return;
    initStarted.current = true;
    oauthRegistrationInit({ ticket: ticketRef.current })
      .then((data) => setState({
        phase: PHASE.REGISTRATION_OTP,
        ticket: ticketRef.current,   // в состоянии (память) — для confirm/resend
        maskedEmail: typeof data?.email_masked === 'string' ? data.email_masked : '',
      }))
      .catch((err) => {
        ticketRef.current = null;
        setState({
          phase: PHASE.ERROR, message: registrationErrorMessage(err), tone: 'error',
        });
      });
  }, [state.phase]);

  // 3. Терминальная ошибка → главная + AuthModal «Вход» с сообщением (replace:
  // «назад» не возвращает на callback). Ровно один переход.
  const left = useRef(false);
  useEffect(() => {
    if (state.phase !== PHASE.ERROR || left.current) return;
    left.current = true;
    ticketRef.current = null;
    navigate('/', {
      replace: true, state: authEntryState('login', state.message, state.tone),
    });
  }, [state, navigate]);

  const handleRegistered = useCallback(() => {
    ticketRef.current = null;
    setState({ phase: PHASE.COMPLETED });
    navigate('/dashboard', { replace: true });
  }, [navigate]);

  // «Начать заново» (регистрация): только локальный сброс — backend не
  // трогаем, старый ticket истечёт сам. Возврат — на главную с AuthModal на
  // вкладке «Регистрация» (там та же кнопка «Яндекс»).
  const handleRestart = useCallback(() => {
    ticketRef.current = null;
    navigate('/', { replace: true, state: RESTART_REGISTRATION_STATE });
  }, [navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.logo}>MindCare</div>
          <p className={styles.subtitle}>Психологическая служба ДонГУ</p>
        </div>
        <PhaseBody
          state={state}
          onRegistered={handleRegistered}
          onRestart={handleRestart}
        />
      </div>
    </div>
  );
}

function PhaseBody({ state, onRegistered, onRestart }) {
  switch (state.phase) {
    case PHASE.REGISTRATION_OTP:
      return (
        <RegistrationOtpController
          ticket={state.ticket}
          initialMaskedEmail={state.maskedEmail}
          onSuccess={onRegistered}
          onRestart={onRestart}
        />
      );
    case PHASE.REGISTRATION_INITIALIZING:
      return (
        <div className={styles.body}>
          <p className={styles.status} role="status">Отправляем код подтверждения…</p>
        </div>
      );
    case PHASE.LOGIN_COMPLETING:
    case PHASE.COMPLETED:
      return (
        <div className={styles.body}>
          <p className={styles.status} role="status">{LOGIN_STATUS}</p>
        </div>
      );
    default:   // RESOLVING / ERROR: нейтрально, без текста (ERROR — до перехода)
      return <div className={styles.body} aria-busy="true" />;
  }
}

/**
 * Шаг кода регистрации через Яндекс. Монтируется только в REGISTRATION_OTP,
 * когда код уже отправлен. Пользователь вводит только код и отмечает согласие
 * MindCare; email и имя backend взял из профиля Яндекса и держит в ticket.
 * «Отправить повторно» — тот же init тем же ticket.
 */
function RegistrationOtpController({ ticket, initialMaskedEmail, onSuccess, onRestart }) {
  const { completeOAuthRegistration, loading: authLoading } = useAuth();
  // Один confirm за раз: двойной клик, авто-подтверждение + кнопка.
  const confirming = useRef(false);

  const [maskedEmail, setMaskedEmail] = useState(initialMaskedEmail);
  const [otp, setOtp] = useState(EMPTY_CODE);
  const [otpError, setOtpError] = useState('');
  // Код уже отправлен до монтирования — отсчёт виден с первого кадра.
  const [timer, restartTimer] = useResendTimer(RESEND_COOLDOWN);
  const [consent, setConsent] = useState(false);
  const [consentError, setConsentError] = useState(false);
  const [busy, setBusy] = useState(false);
  // Ticket больше не завершит регистрацию (истёк, email занят, identity уже есть).
  const [terminal, setTerminal] = useState(false);

  const handleResend = async () => {
    setOtpError('');
    setBusy(true);
    try {
      const data = await oauthRegistrationInit({ ticket });
      if (typeof data?.email_masked === 'string') setMaskedEmail(data.email_masked);
      setOtp(EMPTY_CODE);
      restartTimer();
    } catch (err) {
      setOtpError(registrationErrorMessage(err));
      if (isRegistrationTerminal(err)) setTerminal(true);
    } finally {
      setBusy(false);
    }
  };

  const handleConfirm = async (digits) => {
    const code = digits.join('');
    if (code.length < 6 || confirming.current || !consent) return;
    confirming.current = true;
    setOtpError('');
    setBusy(true);
    try {
      await completeOAuthRegistration(ticket, code, true);
      onSuccess();
    } catch (err) {
      setOtpError(registrationErrorMessage(err));
      if (isRegistrationTerminal(err)) setTerminal(true);
      setOtp(EMPTY_CODE);
    } finally {
      confirming.current = false;
      setBusy(false);
    }
  };

  return (
    <div className={authStyles.authBody}>
      <RegistrationOtpStep
        email={maskedEmail}
        code={otp}
        onCodeChange={(next) => { setOtp(next); setOtpError(''); }}
        error={otpError}
        timer={timer}
        onResend={handleResend}
        onConfirm={handleConfirm}
        loading={busy || authLoading}
        blocked={terminal}
        consent={{
          checked: consent,
          error: consentError,
          onChange: (value) => { setConsent(value); setConsentError(!value); },
          onMissing: () => setConsentError(true),
        }}
        backLabel="← Начать заново"
        onBack={onRestart}
      />
    </div>
  );
}
