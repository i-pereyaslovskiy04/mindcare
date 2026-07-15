import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAuth } from '../AuthContext';
import RegisterForm from '../ui/RegisterForm';
import styles from './RegisterPage.module.css';

export default function RegisterPage() {
  const { isAuthenticated, user } = useAuth();
  const navigate = useNavigate();

  // Already logged in → DashboardRedirect выбирает кабинет (multi-role).
  useEffect(() => {
    if (isAuthenticated && user) {
      navigate('/dashboard', { replace: true });
    }
  }, [isAuthenticated, user, navigate]);

  return (
    <div className={styles.page}>
      <div className={styles.card}>
        <div className={styles.header}>
          <div className={styles.logo}>MindCare</div>
          <p className={styles.subtitle}>Создать аккаунт</p>
        </div>

        {/* RegisterForm handles OTP steps internally. */}
        <RegisterForm onSuccess={() => { /* navigation done inside form */ }} />

        <p className={styles.footer}>
          Уже есть аккаунт?{' '}
          <Link to="/login" className={styles.link}>Войти</Link>
        </p>
      </div>
    </div>
  );
}
