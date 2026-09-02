/**
 * ImpersonationBanner — плашка режима «Зайти под именем» (ADR-025).
 *
 * Показывается на ЛЮБОЙ странице (включая публичные), пока текущая сессия
 * создана администратором от имени другого пользователя. Видимость — по
 * серверной правде из /api/auth/me (user.impersonating). Кнопка возвращает
 * в профиль администратора (client-side, по сохранённому админскому токену).
 */
import { useState } from 'react';
import { useAuth } from '../AuthContext';
import Button from '../../../components/UI/Button/Button';
import Icon from '../../../components/Icon/Icon';
import styles from './ImpersonationBanner.module.css';

export default function ImpersonationBanner() {
  const { isImpersonating, impersonatorName, user, stopImpersonation } = useAuth();
  const [leaving, setLeaving] = useState(false);

  if (!isImpersonating) return null;

  const handleReturn = async () => {
    setLeaving(true);
    try {
      await stopImpersonation();
    } finally {
      setLeaving(false);
    }
  };

  return (
    <div className={styles.banner} role="status" aria-live="polite">
      <span className={styles.text}>
        <Icon name="eye" size={16} aria-hidden />
        <span>
          Вы вошли под именем <strong>{user?.name}</strong>
          {impersonatorName ? ` (администратор ${impersonatorName})` : ''}.
        </span>
      </span>
      <Button
        variant="secondary"
        size="sm"
        onClick={handleReturn}
        disabled={leaving}
        className={styles.returnBtn}
      >
        <Icon name="undo" size={15} aria-hidden />
        Вернуться в профиль администратора
      </Button>
    </div>
  );
}
