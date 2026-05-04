import { useState, useCallback } from 'react';
import styles from './AuthModal.module.css';
import Modal from '../../../components/Modal/Modal';
import LoginForm from './LoginForm';
import RegisterForm from './RegisterForm';
import ForgotPasswordModal from '../forgot-password/ForgotPasswordModal';

export default function AuthModal({ isOpen, onClose }) {
  const [activeTab, setActiveTab] = useState('login');
  const [forgotOpen, setForgotOpen] = useState(false);

  const handleForgotPassword = useCallback(() => {
    onClose();
    setForgotOpen(true);
  }, [onClose]);

  return (
    <>
      <Modal open={isOpen} onClose={onClose} ariaLabel="Вход и регистрация">
        <div className={styles.authBody}>
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

          <div className={styles.authPanels}>
            <div
              id="panel-login"
              role="tabpanel"
              aria-labelledby="tab-login"
              hidden={activeTab !== 'login'}
            >
              <LoginForm onSuccess={onClose} onForgotPassword={handleForgotPassword} />
            </div>
            <div
              id="panel-register"
              role="tabpanel"
              aria-labelledby="tab-register"
              hidden={activeTab !== 'register'}
            >
              <RegisterForm onSuccess={onClose} />
            </div>
          </div>
        </div>
      </Modal>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </>
  );
}
