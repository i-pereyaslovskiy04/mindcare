import { useState, useCallback } from 'react';
import styles from './AuthModal.module.css';
import Modal from '../../../components/Modal/Modal';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import SocialRegistrationFlow, { SOCIAL_STEP } from './SocialRegistrationFlow';
import ForgotPasswordModal from '../forgot-password/ForgotPasswordModal';
import { safeMessageTone } from '../lib/authEntry';

const TABS = ['login', 'register'];

/**
 * Явные режимы модалки.
 *   entry          — обычный вход: вкладки «Вход | Регистрация» и их формы;
 *   socialLoading  — регистрация через провайдера: подготовка (preview либо
 *                    автоматическая отправка кода);
 *   socialEmail    — шаг «Почта для регистрации» (SocialEmailStep, VK ID);
 *   socialOtp      — шаг «Подтверждение регистрации» (RegistrationOtpStep).
 * В social-режимах вкладок нет, а LoginForm и RegisterForm не монтируются:
 * это продолжение уже начатой регистрации, а не выбор способа входа. Режим
 * social-регистрации не связан с состоянием вкладки «Регистрация».
 * (Восстановление пароля — отдельная ForgotPasswordModal, как и раньше.)
 */
export const AUTH_MODAL_MODE = Object.freeze({
  ENTRY: 'entry',
  SOCIAL_LOADING: 'socialLoading',
  SOCIAL_EMAIL: 'socialEmail',
  SOCIAL_OTP: 'socialOtp',
});

const MODE_BY_SOCIAL_STEP = Object.freeze({
  [SOCIAL_STEP.LOADING]: AUTH_MODAL_MODE.SOCIAL_LOADING,
  [SOCIAL_STEP.EMAIL]: AUTH_MODAL_MODE.SOCIAL_EMAIL,
  [SOCIAL_STEP.OTP]: AUTH_MODAL_MODE.SOCIAL_OTP,
});

/**
 * Единственный UI входа и регистрации (страницы `/login` и `/register` —
 * только совместимые редиректы на `/` с этой модалкой; `/auth/callback` —
 * технический маршрут без своих форм).
 *
 * initialTab — вкладка, с которой модалка ОТКРЫВАЕТСЯ ('login' | 'register').
 * Применяется при каждом открытии (и при смене initialTab на открытой
 * модалке); дальше пользователь переключает вкладки сам.
 *
 * message / messageTone — системное сообщение над формой входа (например,
 * «Сессия истекла» или терминальная ошибка входа через Яндекс). Тон — только
 * 'info' | 'error' (иное → 'info'), не CSS-класс. info → role="status",
 * error → role="alert": ровно одно объявление для скринридера.
 *
 * social — незавершённая регистрация через провайдера из памяти приложения
 * (AuthContext.socialRegistration: { ticket, provider, emailStep }) или null.
 * Пока она есть, модалка работает в social-режиме; владелец обязан держать её
 * открытой. onSocialExit({ tab, message?, messageTone? }) — поток закончился
 * без регистрации («Начать заново» либо терминальная ошибка): владелец
 * забывает ticket и возвращает обычный режим `entry`.
 */
export default function AuthModal({
  isOpen, onClose, message, messageTone = 'info', initialTab = 'login',
  social = null, onSocialExit,
}) {
  const tone = safeMessageTone(messageTone);
  const startTab = TABS.includes(initialTab) ? initialTab : 'login';
  const inSocial = Boolean(social);
  const [activeTab, setActiveTab] = useState(startTab);
  const [forgotOpen, setForgotOpen] = useState(false);
  // Шаг регистрации: на подтверждении кода вкладки «Вход | Регистрация» не
  // показываются — это уже не выбор режима.
  const [registerStep, setRegisterStep] = useState('form');
  const [socialStep, setSocialStep] = useState(SOCIAL_STEP.LOADING);
  // Открытие, смена initialTab и вход/выход из social-режима отслеживаются во
  // время рендера (не эффектом): нужная вкладка видна с первого кадра, без
  // устаревшего состояния.
  const [opening, setOpening] = useState({ isOpen, startTab, inSocial });
  if (
    opening.isOpen !== isOpen || opening.startTab !== startTab || opening.inSocial !== inSocial
  ) {
    setOpening({ isOpen, startTab, inSocial });
    if (isOpen) setActiveTab(startTab);
    if (opening.inSocial !== inSocial) {
      // Формы обычного режима перемонтируются с первого шага — их прежние
      // шаги не должны прятать вкладки; новый social-поток начинается с начала.
      setRegisterStep('form');
      setSocialStep(SOCIAL_STEP.LOADING);
    }
  }
  const mode = inSocial ? MODE_BY_SOCIAL_STEP[socialStep] : AUTH_MODAL_MODE.ENTRY;
  const confirming = activeTab === 'register' && registerStep === 'code';

  const handleForgotPassword = useCallback(() => {
    onClose();
    setForgotOpen(true);
  }, [onClose]);

  return (
    <>
      <Modal open={isOpen} onClose={onClose} ariaLabel="Вход и регистрация">
        <div className={styles.authBody} data-mode={mode} data-testid="auth-modal-body">
          {inSocial ? (
            <SocialRegistrationFlow
              registration={social}
              onStepChange={setSocialStep}
              onExit={onSocialExit}
            />
          ) : (
            <>
              {!confirming && (
                <div
                  className={`${styles.authTabs} ${activeTab === 'register' ? styles.onRegister : ''}`}
                  role="tablist"
                  aria-label="Тип формы"
                >
                  <div className={styles.authTabsPill} aria-hidden="true" />
                  <button
                    className={`${styles.authTabBtn} ${activeTab === 'login' ? styles.active : ''}`}
                    onClick={() => setActiveTab('login')}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'login'}
                    aria-controls="panel-login"
                    id="tab-login"
                  >
                    Вход
                  </button>
                  <button
                    className={`${styles.authTabBtn} ${activeTab === 'register' ? styles.active : ''}`}
                    onClick={() => setActiveTab('register')}
                    type="button"
                    role="tab"
                    aria-selected={activeTab === 'register'}
                    aria-controls="panel-register"
                    id="tab-register"
                  >
                    Регистрация
                  </button>
                </div>
              )}

              <div className={styles.authPanels}>
                <div
                  id="panel-login"
                  role="tabpanel"
                  aria-labelledby="tab-login"
                  hidden={activeTab !== 'login'}
                >
                  {message && (
                    <div
                      className={tone === 'error' ? styles.errorMessage : styles.infoMessage}
                      role={tone === 'error' ? 'alert' : 'status'}
                    >
                      {message}
                    </div>
                  )}
                  <LoginForm onSuccess={onClose} onForgotPassword={handleForgotPassword} />
                </div>
                <div
                  id="panel-register"
                  role={confirming ? undefined : 'tabpanel'}
                  aria-labelledby={confirming ? undefined : 'tab-register'}
                  hidden={activeTab !== 'register'}
                >
                  <RegisterForm onSuccess={onClose} onStepChange={setRegisterStep} />
                </div>
              </div>
            </>
          )}
        </div>
      </Modal>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </>
  );
}
