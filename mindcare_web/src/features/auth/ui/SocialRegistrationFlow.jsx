import { useCallback, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { oauthRegistrationInit, oauthRegistrationPreview } from '../../../api/auth.api';
import { useAuth } from '../AuthContext';
import RegistrationOtpStep, {
  EMPTY_CODE, RESEND_COOLDOWN, useResendTimer,
} from './RegistrationOtpStep';
import SocialEmailStep from './SocialEmailStep';
import { isRegistrationTerminal, registrationErrorMessage } from '../lib/oauthCallback';
import styles from './AuthModal.module.css';

/** Шаги регистрации через провайдера; AuthModal строит по ним свой режим. */
export const SOCIAL_STEP = Object.freeze({
  LOADING: 'loading',   // preview (VK) либо автоматическая отправка кода (Яндекс)
  EMAIL: 'email',       // SocialEmailStep: выбор/подтверждение адреса
  OTP: 'otp',           // RegistrationOtpStep: ввод кода и согласие
});

/**
 * Регистрация через внешний провайдер ВНУТРИ AuthModal (Stage Social Auth 4,
 * VK-1B). Не страница и не отдельная модалка: AuthModal монтирует этот поток
 * вместо вкладок «Вход | Регистрация», пока в AuthContext есть незавершённая
 * регистрация (`registration` = { ticket, provider, emailStep }).
 *
 * Переходы:
 *   loading ─emailStep: preview ok→ email ─[пользователь]→ otp          (VK)
 *   loading ─иначе: автоматический init ok→ otp                        (Яндекс)
 *   otp ─«Изменить email» (только VK)→ email
 *   otp ─код + согласие ok→ сессия (AuthContext) → /dashboard
 *
 * Шаг кода монтируется ТОЛЬКО после успешного init, шаг email — только после
 * успешного preview либо по «Изменить email».
 *
 * Выход из потока — только через onExit({ tab, message?, messageTone? }):
 *   «Начать заново»      → { tab: 'register' };
 *   терминальная ошибка  → { tab: 'login', message, messageTone: 'error' }
 *                          (ticket истёк, identity уже привязана, сбой
 *                          preview/автоматического init).
 * Владелец (Home) в ответ забывает ticket и показывает обычную AuthModal.
 * Исправимые ошибки шага email (домен, занятый адрес, формат, лимит) остаются
 * внутри шага email.
 *
 * Инварианты:
 *   1. один preview и один автоматический init на ticket, в том числе в React
 *      StrictMode (флаги в ref); один init на действие пользователя;
 *   2. ticket — только prop/память: не в DOM, storage, URL и router state;
 *   3. raw email провайдера на клиент не приходит — только маска; адрес,
 *      введённый пользователем, живёт в поле ввода и теле запроса init;
 *   4. ответ, пришедший после выхода из потока (закрыли модалку, «Начать
 *      заново»), игнорируется.
 */
export default function SocialRegistrationFlow({ registration, onStepChange, onExit }) {
  const { ticket, provider, emailStep } = registration;
  const navigate = useNavigate();
  const [state, setState] = useState({ step: SOCIAL_STEP.LOADING, sending: !emailStep });
  const alive = useRef(false);
  const previewStarted = useRef(false);
  const initStarted = useRef(false);
  const emailSubmitting = useRef(false);
  // Свежий обработчик выхода без пересоздания колбэков и перезапуска эффектов.
  const exitRef = useRef(onExit);
  useEffect(() => { exitRef.current = onExit; }, [onExit]);

  // Первым: остальные эффекты и обработчики ответов смотрят на этот флаг.
  useEffect(() => {
    alive.current = true;
    return () => { alive.current = false; };
  }, []);

  // Layout effect: режим AuthModal меняется до отрисовки — ни одного кадра с
  // шагом, не совпадающим с режимом модалки.
  useLayoutEffect(() => { onStepChange?.(state.step); }, [state.step, onStepChange]);

  const fail = useCallback((err) => {
    if (!alive.current) return;
    exitRef.current?.({
      tab: 'login',
      message: registrationErrorMessage(err, provider),
      messageTone: 'error',
    });
  }, [provider]);

  // «Начать заново»: только локальный выход — backend не трогаем, старый
  // ticket истечёт сам. Владелец забывает ticket и открывает «Регистрацию».
  const handleRestart = useCallback(() => {
    exitRef.current?.({ tab: 'register' });
  }, []);

  // Выбор email (VK): ровно один preview; шаг email — только после его
  // успеха. Код здесь НЕ отправляется.
  useEffect(() => {
    if (state.step !== SOCIAL_STEP.LOADING || state.sending || previewStarted.current) return;
    previewStarted.current = true;
    oauthRegistrationPreview({ ticket })
      .then((data) => {
        if (!alive.current) return;
        if (data?.email_editable !== true) {
          // Адрес фиксирован провайдером — шаг email не нужен.
          setState({ step: SOCIAL_STEP.LOADING, sending: true });
          return;
        }
        setState({
          step: SOCIAL_STEP.EMAIL,
          maskedEmail: typeof data.email_masked === 'string' ? data.email_masked : null,
          emailAllowed: data.email_allowed === true,
          error: '',
          submitting: false,
        });
      })
      .catch(fail);
  }, [state, ticket, fail]);

  // Фиксированный email (Яндекс): ровно один автоматический init; шаг кода —
  // только после успеха.
  useEffect(() => {
    if (state.step !== SOCIAL_STEP.LOADING || !state.sending || initStarted.current) return;
    initStarted.current = true;
    oauthRegistrationInit({ ticket })
      .then((data) => {
        if (!alive.current) return;
        setState({
          step: SOCIAL_STEP.OTP,
          maskedEmail: typeof data?.email_masked === 'string' ? data.email_masked : '',
          emailEditable: false,
        });
      })
      .catch(fail);
  }, [state, ticket, fail]);

  // Шаг email: пользователь подтвердил показанный адрес (email === null) или
  // указал свой. Один запрос за раз.
  const handleEmailSubmit = useCallback((email) => {
    if (emailSubmitting.current) return;
    emailSubmitting.current = true;
    setState((prev) => (
      prev.step === SOCIAL_STEP.EMAIL ? { ...prev, submitting: true, error: '' } : prev
    ));
    oauthRegistrationInit({ ticket, email })
      .then((data) => {
        if (!alive.current) return;
        setState({
          step: SOCIAL_STEP.OTP,
          maskedEmail: typeof data?.email_masked === 'string' ? data.email_masked : '',
          emailEditable: true,
        });
      })
      .catch((err) => {
        if (!alive.current) return;
        if (isRegistrationTerminal(err, { emailEditable: true })) {
          fail(err);
          return;
        }
        if (email === null && err?.code === 'otp_cooldown') {
          // «Продолжить» с уже привязанным адресом сразу после отправки: код
          // на него только что ушёл — возвращаемся к вводу кода, а не к ошибке.
          setState((prev) => (
            prev.step === SOCIAL_STEP.EMAIL
              ? { step: SOCIAL_STEP.OTP, maskedEmail: prev.maskedEmail || '', emailEditable: true }
              : prev
          ));
          return;
        }
        // Исправимо: остаёмся на шаге email.
        setState((prev) => (
          prev.step === SOCIAL_STEP.EMAIL
            ? { ...prev, submitting: false, error: registrationErrorMessage(err, provider) }
            : prev
        ));
      })
      .finally(() => { emailSubmitting.current = false; });
  }, [ticket, fail, provider]);

  // «Изменить email» с шага кода (VK): назад на шаг email. Показанный адрес —
  // тот, что сейчас привязан к ticket (на него ушёл код).
  const handleChangeEmail = useCallback((maskedEmail) => {
    setState({
      step: SOCIAL_STEP.EMAIL,
      maskedEmail: maskedEmail || null,
      emailAllowed: Boolean(maskedEmail),
      error: '',
      submitting: false,
    });
  }, []);

  // Сессия уже установлена AuthContext (он же забыл ticket) — в кабинет.
  // Кабинет выбирает DashboardRedirect, как после входа по паролю.
  const handleRegistered = useCallback(() => {
    navigate('/dashboard');
  }, [navigate]);

  if (state.step === SOCIAL_STEP.OTP) {
    return (
      <RegistrationOtpController
        ticket={ticket}
        provider={provider}
        initialMaskedEmail={state.maskedEmail}
        emailEditable={state.emailEditable}
        onSuccess={handleRegistered}
        onRestart={handleRestart}
        onChangeEmail={handleChangeEmail}
        onTerminal={fail}
      />
    );
  }

  if (state.step === SOCIAL_STEP.EMAIL) {
    return (
      <SocialEmailStep
        maskedEmail={state.maskedEmail}
        emailAllowed={state.emailAllowed}
        error={state.error}
        loading={state.submitting}
        onSubmit={handleEmailSubmit}
        onRestart={handleRestart}
      />
    );
  }

  return (
    <div className={`${styles.authPanel} ${styles.active}`}>
      <p className={styles.stepDesc} role="status">
        {state.sending ? 'Отправляем код подтверждения…' : 'Готовим регистрацию…'}
      </p>
    </div>
  );
}

/**
 * Шаг кода регистрации через провайдера. Монтируется только когда код уже
 * отправлен. Пользователь вводит только код и отмечает согласие MindCare
 * (согласие провайдера его не заменяет); email и имя держит ticket на backend.
 * «Отправить повторно» — init тем же ticket без адреса: код уходит на адрес,
 * привязанный к ticket.
 *
 * emailEditable (VK): адрес можно изменить — «Изменить email» возвращает на
 * шаг email, а занятый адрес при confirm — исправимая ошибка. Иначе (Яндекс)
 * адрес фиксирован: «Начать заново».
 */
function RegistrationOtpController({
  ticket, provider, initialMaskedEmail, emailEditable, onSuccess, onRestart,
  onChangeEmail, onTerminal,
}) {
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
  // Фиксированный адрес: ticket больше не завершит регистрацию (истёк, email
  // занят, identity уже есть) — остаётся только «Начать заново».
  const [terminal, setTerminal] = useState(false);

  const handleFailure = (err) => {
    if (isRegistrationTerminal(err, { emailEditable })) {
      if (emailEditable) {
        onTerminal(err);   // ticket мёртв и адрес уже не поможет → обычная AuthModal
        return true;
      }
      setTerminal(true);
    }
    setOtpError(registrationErrorMessage(err, provider));
    return false;
  };

  const handleResend = async () => {
    setOtpError('');
    setBusy(true);
    try {
      const data = await oauthRegistrationInit({ ticket });
      if (typeof data?.email_masked === 'string') setMaskedEmail(data.email_masked);
      setOtp(EMPTY_CODE);
      restartTimer();
    } catch (err) {
      if (handleFailure(err)) return;
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
      if (handleFailure(err)) return;
      setOtp(EMPTY_CODE);
    } finally {
      confirming.current = false;
      setBusy(false);
    }
  };

  return (
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
      backLabel={emailEditable ? 'Изменить email' : 'Начать заново'}
      onBack={emailEditable ? () => onChangeEmail(maskedEmail) : onRestart}
    />
  );
}
