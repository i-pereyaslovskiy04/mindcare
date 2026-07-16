import { useEffect, useState, useCallback } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import LoginForm from '../ui/LoginForm';
import ForgotPasswordModal from '../forgot-password/ForgotPasswordModal';
import styles from './LoginPage.module.css';

export default function LoginPage() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();
  const [forgotOpen, setForgotOpen] = useState(false);

  // Already logged in → DashboardRedirect выбирает кабинет (multi-role).
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  const handleLoginSuccess = useCallback(() => {
    // Navigation is handled inside LoginForm after login() resolves.
  }, []);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.logo}>MindCare</div>
          <p className={styles.subtitle}>Психологическая служба ДонГУ</p>
        </div>

        <LoginForm
          onSuccess={handleLoginSuccess}
          onForgotPassword={() => setForgotOpen(true)}
        />

        <p className={styles.footer}>
          Нет аккаунта?{' '}
          <Link to="/register" className={styles.link}>Зарегистрироваться</Link>
        </p>
      </div>

      <ForgotPasswordModal open={forgotOpen} onClose={() => setForgotOpen(false)} />
    </div>
  );
}
