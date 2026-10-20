import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useAuth } from './AuthContext';
import { ROLE_PRIORITY, ROLE_LABELS, normalizeRoles } from '../../shared/lib/roles';
import { getRoleHome } from '../../shared/lib/routes';
import styles from './CabinetSwitcher.module.css';

/**
 * Переключатель кабинета (ADR-018). Простой disclosure-паттерн (не menu):
 *   - trigger — обычная button (aria-expanded/aria-controls);
 *   - панель — обычный список из обычных button;
 *   - Tab работает нативно; Escape закрывает и возвращает фокус на trigger;
 *   - закрытие после выбора и по клику снаружи.
 * Переключение — только UI-hint (setActiveRole); доступ проверяет backend.
 *
 * currentRole — роль текущего кабинета (в кабинетах) либо activeRole (в профиле);
 * null → состояние «Выбрать кабинет».
 *
 * Список кабинетов — ВСЕ активные роли из roles[] (в т.ч. student →
 * «Пользователь» у staff); selectableRoles() здесь намеренно не используется:
 * он скрывает student у staff только для выбора кабинета при входе.
 *
 * При нескольких ролях trigger — заметная кнопка «Сменить кабинет» с текущей
 * ролью (а не подпись роли, визуально неотличимая от статичной метки).
 * variant: 'sidebar' — полноширинная кнопка в блоке пользователя (sidebar и
 * mobile drawer); 'compact' — копия в topbar при свёрнутом sidebar.
 */
export default function CabinetSwitcher({ currentRole = null, variant = 'sidebar' }) {
  const navigate = useNavigate();
  const { user, setActiveRole } = useAuth();
  const [open, setOpen] = useState(false);
  const [panelPos, setPanelPos] = useState({ top: 0, left: 0 });
  const rootRef = useRef(null);
  const triggerRef = useRef(null);
  const panelRef = useRef(null);
  const panelId = useId();

  const roles = ROLE_PRIORITY.filter((r) => normalizeRoles(user).includes(r));

  // Панель позиционируется через fixed viewport-координаты (не absolute
  // relative к trigger), иначе на узких viewport и в сайдбаре с
  // overflow:hidden она обрезается или уходит за правый край экрана.
  // Учитывает и правый, и нижний край viewport (открывается вверх, если
  // снизу не хватает места) — панель никогда не должна уходить за экран.
  const computePanelPosition = useCallback(() => {
    if (!triggerRef.current) return;
    const rect = triggerRef.current.getBoundingClientRect();
    const PANEL_WIDTH = 240; // соответствует max-width панели в CSS
    const MARGIN = 8;
    const panelHeight = panelRef.current?.getBoundingClientRect().height ?? 0;

    const left = Math.max(
      MARGIN,
      Math.min(rect.left, window.innerWidth - PANEL_WIDTH - MARGIN),
    );

    const spaceBelow = window.innerHeight - rect.bottom - MARGIN;
    const openUpward = panelHeight > 0
      && spaceBelow < panelHeight
      && rect.top - MARGIN >= panelHeight;
    const top = openUpward
      ? Math.max(MARGIN, rect.top - panelHeight - 6)
      : Math.min(rect.bottom + 6, Math.max(MARGIN, window.innerHeight - MARGIN - panelHeight));

    setPanelPos({ top, left });
  }, []);

  useLayoutEffect(() => {
    if (!open) return;
    computePanelPosition();
  }, [open, computePanelPosition]);

  // Resize/orientation change — координаты trigger'а изменились, пересчитываем.
  useEffect(() => {
    if (!open) return undefined;
    window.addEventListener('resize', computePanelPosition);
    window.addEventListener('orientationchange', computePanelPosition);
    return () => {
      window.removeEventListener('resize', computePanelPosition);
      window.removeEventListener('orientationchange', computePanelPosition);
    };
  }, [open, computePanelPosition]);

  // Скролл (страницы или узкого скроллируемого контейнера — сайдбар/nav)
  // делает fixed-координаты панели неактуальными относительно trigger —
  // закрываем панель, а не пересчитываем на каждый scroll-тик. capture:true
  // ловит scroll и на вложенных скроллируемых контейнерах (scroll не всплывает).
  useEffect(() => {
    if (!open) return undefined;
    const onScroll = () => setOpen(false);
    window.addEventListener('scroll', onScroll, true);
    return () => window.removeEventListener('scroll', onScroll, true);
  }, [open]);

  // Outside click закрывает панель.
  useEffect(() => {
    if (!open) return undefined;
    const onDown = (e) => {
      if (rootRef.current && !rootRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDown);
    return () => document.removeEventListener('mousedown', onDown);
  }, [open]);

  const close = (restoreFocus) => {
    setOpen(false);
    if (restoreFocus) triggerRef.current?.focus();
  };

  const onTriggerKeyDown = (e) => {
    if (e.key === 'Escape' && open) {
      e.stopPropagation();
      close(true);
    }
  };

  const onPanelKeyDown = (e) => {
    if (e.key === 'Escape') {
      e.stopPropagation();
      close(true);
    }
  };

  const choose = (role) => {
    setActiveRole(role);
    setOpen(false);
    navigate(getRoleHome(role));
  };

  // Single-role (или ролей нет) — статичный лейбл, без переключателя.
  if (roles.length <= 1) {
    const label = ROLE_LABELS[currentRole] ?? ROLE_LABELS[roles[0]] ?? '';
    return (
      <span className={styles.staticRole}>
        <span className={styles.dot} aria-hidden="true" />
        {label}
      </span>
    );
  }

  const currentLabel = currentRole ? (ROLE_LABELS[currentRole] ?? currentRole) : null;
  const actionLabel = currentLabel ? 'Сменить кабинет' : 'Выбрать кабинет';
  // Доступное имя содержит видимый текст действия (WCAG 2.5.3) и текущую роль.
  const triggerName = currentLabel
    ? `${actionLabel} (текущий: ${currentLabel})`
    : actionLabel;

  return (
    <div
      className={`${styles.root} ${variant === 'compact' ? styles.rootCompact : styles.rootSidebar}`}
      ref={rootRef}
    >
      <button
        type="button"
        ref={triggerRef}
        className={`${styles.trigger} ${variant === 'compact' ? styles.compact : styles.sidebar}`}
        aria-expanded={open}
        aria-controls={panelId}
        aria-label={triggerName}
        title={triggerName}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={onTriggerKeyDown}
      >
        <span className={styles.triggerText}>
          <span className={styles.triggerAction}>{actionLabel}</span>
          {currentLabel && (
            <span className={styles.triggerCurrent}>
              <span className={styles.dot} aria-hidden="true" />
              <span className={styles.triggerLabel}>{currentLabel}</span>
            </span>
          )}
        </span>
        <span className={styles.chevron} aria-hidden="true">▾</span>
      </button>

      {open && (
        <div
          id={panelId}
          ref={panelRef}
          className={styles.panel}
          style={{ top: panelPos.top, left: panelPos.left }}
          onKeyDown={onPanelKeyDown}
        >
          <div className={styles.panelTitle}>Перейти в кабинет</div>
          {roles.map((role) => (
            <button
              key={role}
              type="button"
              className={`${styles.option}${role === currentRole ? ` ${styles.current}` : ''}`}
              onClick={() => choose(role)}
              aria-current={role === currentRole ? 'true' : undefined}
            >
              {ROLE_LABELS[role] ?? role}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
