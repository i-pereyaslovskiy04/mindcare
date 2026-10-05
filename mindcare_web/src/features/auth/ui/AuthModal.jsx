import { useState, useCallback } from 'react';
import styles from './AuthModal.module.css';
import Modal from '../../../components/Modal/Modal';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import ForgotPasswordModal from '../forgot-password/ForgotPasswordModal';
import { safeMessageTone } from '../lib/authEntry';

const TABS = ['login', 'register'];

/**
 * Единственный UI входа и регистрации (страницы `/login` и `/register` —
 * только совместимые редиректы на `/` с этой модалкой).
 *
 * initialTab — вкладка, с которой модалка ОТКРЫВАЕТСЯ ('login' | 'register').
 * Применяется при каждом открытии (и при смене initialTab на открытой
 * модалке); дальше пользователь переключает вкладки сам.
 *
 * message / messageTone — системное сообщение над формой входа (например,
 * «Сессия истекла» или терминальная ошибка входа через Яндекс). Тон — только
 * 'info' | 'error' (иное → 'info'), не CSS-класс. info → role="status",
 * error → role="alert": ровно одно объявление для скринридера.
 */
export default function AuthModal({
  isOpen, onClose, message, messageTone = 'info', initialTab = 'login',
}) {
  const tone = safeMessageTone(messageTone);
  const startTab = TABS.includes(initialTab) ? initialTab : 'login';
  const [activeTab, setActiveTab] = useState(startTab);
  const [forgotOpen, setForgotOpen] = useState(false);
  // Открытие/смена initialTab отслеживаются во время рендера (не эффектом):
  // нужная вкладка видна с первого кадра открытия, без устаревшего состояния.
  const [opening, setOpening] = useState({ isOpen, startTab });
  if (opening.isOpen !== isOpen || opening.startTab !== startTab) {
    setOpening({ isOpen, startTab });
    if (isOpen) setActiveTab(startTab);
  }
  // Шаг регистрации: на подтверждении кода вкладки «Вход | Регистрация» не
  // показываются — это уже не выбор режима.
  const [registerStep, setRegisterStep] = useState('form');
  const confirming = activeTab === 'register' && registerStep === 'code';

  const handleForgotPassword = useCallback(() => {
    onClose();
    setForgotOpen(true);
  }, [onClose]);

  return (
    <>
      <Modal open={isOpen} onClose={onClose} ariaLabel="Вход и регистрация">
        <div className={styles.authBody}>
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
        </div>
      </Modal>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </>
  );
}
