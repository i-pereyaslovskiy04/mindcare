/**
 * CabinetHeader — общая шапка (topbar) всех кабинетов: student, psychologist,
 * supervisor (через CabinetLayout) и admin (через AdminLayout).
 *
 * Слева — hamburger мобильного drawer'а (только <=600px, если layout передал
 * onMenuOpen) и хлебные крошки. Справа строгий порядок:
 *   [CabinetSwitcher, только 601–980px] → Поиск → [Уведомления] → Оформление → Выход.
 * Уведомления (колокольчик) — только в кабинетах student и psychologist.
 * На <=600px CabinetSwitcher в шапке скрыт: тот же переключатель есть в блоке
 * пользователя внутри drawer'а, а место в шапке нужно колокольчику,
 * «Оформлению» и выходу.
 *
 * Brand и sidebar остаются в своих layout'ах; layout передаёт `className` с
 * собственными отступами шапки, общая высота — var(--cabinet-header-height)
 * из layout'а (общая линия под brand и topbar рисуется в .app::after layout'а).
 *
 * Поиск — честная заглушка: disabled и ничего не ищет. Колокольчик — слой над
 * системной беседой «Психология ДонГУ» (features/bell/SystemBell): badge —
 * реальное число непрочитанных, панель — до 5 новых сообщений; у supervisor и
 * admin его нет (там рабочие события — счётчики очередей в меню). «Оформление» — одна точка
 * входа: ThemeToggle compact + существующий A11yToggle отдельной секцией панели
 * (контексты темы и режима для слабовидящих не смешиваются — шапка только
 * компонует два готовых компонента).
 */

import { Link } from 'react-router-dom';
import { useLogout } from '../../features/auth/AuthContext';
import CabinetSwitcher from '../../features/auth/CabinetSwitcher';
import ThemeToggle from '../../features/theme/ThemeToggle';
import {
  A11Y_APPEARANCE_SECTION, APPEARANCE_LABEL,
} from '../../features/a11y/appearanceSection';
import SystemBell from '../../features/bell/ui/SystemBell';
import { hasBell } from '../../features/bell/lib/bellView';
import Icon from '../Icon/Icon';
import styles from './CabinetHeader.module.css';

function Breadcrumbs({ items }) {
  return (
    <nav className={styles.crumbs} aria-label="Навигационная цепочка">
      <ol className={styles.crumbList}>
        {items.map((crumb, i) => {
          const isLast = i === items.length - 1;
          // Промежуточные уровни прячутся на узких экранах (<=600px, см. CSS).
          const isMiddle = i > 0 && !isLast;
          return (
            <li key={crumb.to ?? crumb.label} className={isMiddle ? styles.crumbMiddle : undefined}>
              {/* Разделитель — текст « / » с пробелами, как в прежних крошках
                  (пробелы получают тот же letter-spacing). */}
              {i > 0 && <span aria-hidden="true">{' / '}</span>}
              {crumb.to ? (
                <Link to={crumb.to} className={styles.crumbLink}>{crumb.label}</Link>
              ) : (
                <span className={styles.crumbCurrent} aria-current="page">{crumb.label}</span>
              )}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

/**
 * onMenuOpen / menuOpen / menuId / menuButtonRef — hamburger мобильного drawer'а
 * (CabinetDrawer layout'а): aria-expanded/aria-controls и ref для возврата фокуса.
 */
export default function CabinetHeader({
  cabinetRole,
  breadcrumbs,
  className,
  onMenuOpen,
  menuOpen = false,
  menuId,
  menuButtonRef,
}) {
  const logout = useLogout();

  return (
    <header className={[styles.header, className].filter(Boolean).join(' ')}>
      <div className={styles.lead}>
        {onMenuOpen && (
          <button
            ref={menuButtonRef}
            className={styles.menuBtn}
            type="button"
            aria-label="Открыть меню"
            aria-haspopup="dialog"
            aria-expanded={menuOpen}
            aria-controls={menuOpen ? menuId : undefined}
            onClick={onMenuOpen}
          >
            <span aria-hidden="true">☰</span>
          </button>
        )}
        <Breadcrumbs items={breadcrumbs} />
      </div>

      <div className={styles.actions}>
        {/* Дублирует switcher из sidebar .userInfo, но видим только когда
            sidebar свёрнут в icon-rail (601–980px); на <=600px он в drawer. */}
        <div className={styles.switcher}>
          <CabinetSwitcher currentRole={cabinetRole} variant="compact" />
        </div>

        {/* Заглушка будущего глобального поиска: поле выключено, формы нет. */}
        <div className={styles.search} title="Поиск будет доступен позже">
          <Icon name="search" size={14} />
          <input
            type="search"
            disabled
            placeholder="Поиск по материалам, записям…"
            aria-label="Поиск — будет доступен позже"
          />
        </div>

        {/* Колокольчик — только student/psychologist; на мобильной ширине
            не скрывается. */}
        {hasBell(cabinetRole) && (
          <SystemBell cabinetRole={cabinetRole} triggerClassName={styles.iconBtn} />
        )}

        <ThemeToggle
          compact
          label={APPEARANCE_LABEL}
          extraSection={A11Y_APPEARANCE_SECTION}
        />

        <button
          type="button"
          className={styles.iconBtn}
          aria-label="Выйти"
          title="Выйти"
          onClick={logout}
        >
          <Icon name="logout" size={16} />
        </button>
      </div>
    </header>
  );
}
