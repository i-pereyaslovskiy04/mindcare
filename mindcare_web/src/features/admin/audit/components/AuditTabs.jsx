import { useRef } from 'react';
import styles from './AuditTabs.module.css';

export const tabButtonId = (id) => `audit-tab-${id}`;
export const tabPanelId = (id) => `audit-panel-${id}`;

/**
 * Вкладки трёх журналов.
 *
 * Feature-specific: shared Tabs в проекте нет, а ближайший аналог
 * (`pages/psychologist/Appointments/AppointmentsPage.jsx`) — inline-разметка без
 * `aria-controls` и без клавиатурной навигации, переиспользовать там нечего.
 *
 * Реализован стандартный tablist с автоматической активацией: стрелки и
 * Home/End переносят фокус и сразу переключают вкладку, невыбранные кнопки
 * выведены из Tab-обхода (roving tabIndex).
 */
export default function AuditTabs({ tabs, active, onChange, label = 'Журналы аудита' }) {
  const listRef = useRef(null);

  const focusTab = (id) => {
    onChange(id);
    requestAnimationFrame(() => {
      listRef.current?.querySelector(`#${tabButtonId(id)}`)?.focus();
    });
  };

  const handleKeyDown = (event) => {
    const index = tabs.findIndex((tab) => tab.id === active);
    if (index < 0) return;

    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault();
        focusTab(tabs[(index + 1) % tabs.length].id);
        break;
      case 'ArrowLeft':
        event.preventDefault();
        focusTab(tabs[(index - 1 + tabs.length) % tabs.length].id);
        break;
      case 'Home':
        event.preventDefault();
        focusTab(tabs[0].id);
        break;
      case 'End':
        event.preventDefault();
        focusTab(tabs[tabs.length - 1].id);
        break;
      default:
        break;
    }
  };

  return (
    <div
      ref={listRef}
      className={styles.tabs}
      role="tablist"
      aria-label={label}
      onKeyDown={handleKeyDown}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === active;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            id={tabButtonId(tab.id)}
            aria-selected={isActive}
            aria-controls={tabPanelId(tab.id)}
            tabIndex={isActive ? 0 : -1}
            className={`${styles.tab} ${isActive ? styles.tabActive : ''}`}
            onClick={() => onChange(tab.id)}
          >
            {tab.label}
          </button>
        );
      })}
    </div>
  );
}
