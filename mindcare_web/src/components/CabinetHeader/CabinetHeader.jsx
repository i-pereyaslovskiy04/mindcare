/**
 * CabinetHeader — общая шапка (topbar) всех кабинетов: student, psychologist,
 * supervisor (через CabinetLayout) и admin (через AdminLayout).
 *
 * Слева — слот `leading` (hamburger мобильного drawer'а CabinetLayout; у
 * AdminLayout его нет) и хлебные крошки. Справа строгий порядок:
 *   [CabinetSwitcher, только <=980px] → Поиск → Уведомления → Оформление → Выход.
 *
 * Brand и sidebar остаются в своих layout'ах; layout передаёт `className` с
 * собственными отступами шапки, общая высота — var(--cabinet-header-height)
 * из layout'а (общая линия под brand и topbar рисуется в .app::after layout'а).
 *
 * Поиск и уведомления — честные заглушки: поиск disabled и ничего не ищет,
 * у колокольчика нет индикатора непрочитанного. «Оформление» — одна точка
 * входа: ThemeToggle compact + существующий A11yToggle отдельной секцией панели
 * (контексты темы и режима для слабовидящих не смешиваются — шапка только
 * компонует два готовых компонента).
 */

import { Link } from 'react-router-dom';
import { useLogout } from '../../features/auth/AuthContext';
import CabinetSwitcher from '../../features/auth/CabinetSwitcher';
import ThemeToggle from '../../features/theme/ThemeToggle';
import A11yToggle from '../../features/a11y/A11yToggle';
import Icon from '../Icon/Icon';
import styles from './CabinetHeader.module.css';

const A11Y_SECTION = {
  title: 'Версия для слабовидящих',
  // Переключение версии сразу меняет оформление всей страницы и открывает
  // A11yPanel под шапкой — панель «Оформление» закрываем, фокус — на триггер.
  render: ({ close }) => <A11yToggle block onToggle={close} />,
};

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

export default function CabinetHeader({ cabinetRole, breadcrumbs, leading = null, className }) {
  const logout = useLogout();

  return (
    <header className={[styles.header, className].filter(Boolean).join(' ')}>
      <div className={styles.lead}>
        {leading}
        <Breadcrumbs items={breadcrumbs} />
      </div>

      <div className={styles.actions}>
        {/* Дублирует switcher из sidebar .userInfo, но видим только когда
            sidebar свёрнут в icon-rail/скрыт (<=980px) — одновременно виден
            только один из двух. */}
        <div className={styles.switcher}>
          <CabinetSwitcher currentRole={cabinetRole} />
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

        {/* Заглушка уведомлений: без счётчика и индикатора непрочитанного. */}
        <button
          type="button"
          className={`${styles.iconBtn} ${styles.iconBtnPlaceholder} ${styles.iconBtnOptional}`}
          aria-label="Уведомления — скоро"
          title="Уведомления — скоро"
          aria-disabled="true"
        >
          <Icon name="bell" size={16} />
        </button>

        <ThemeToggle
          compact
          label="Оформление и версия для слабовидящих"
          extraSection={A11Y_SECTION}
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
