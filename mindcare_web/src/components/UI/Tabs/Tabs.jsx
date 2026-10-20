import { useRef } from 'react';
import styles from './Tabs.module.css';

export const tabButtonId = (prefix, id) => `${prefix}-tab-${id}`;
export const tabPanelId = (prefix, id) => `${prefix}-panel-${id}`;

/**
 * Вкладки (shared; поднят из features/admin/audit/AuditTabs — см.
 * docs/UI_TECH_DEBT.md). Стандартный tablist с автоматической активацией:
 * стрелки и Home/End переносят фокус и сразу переключают вкладку, невыбранные
 * кнопки выведены из Tab-обхода (roving tabIndex).
 *
 * Props:
 *   tabs     — [{ id, label }]
 *   active   — id активной вкладки
 *   onChange — (id) => void
 *   label    — aria-label списка вкладок
 *   idPrefix — префикс id (кнопка `${p}-tab-${id}`, панель `${p}-panel-${id}`);
 *              панели рисует потребитель: role="tabpanel", id=tabPanelId(...),
 *              aria-labelledby=tabButtonId(...). Неактивные панели можно держать
 *              смонтированными с атрибутом hidden (черновики не теряются).
 *   fill     — равные колонки на всю ширину без min-width (узкие экраны)
 *   indicator — вид выбранной вкладки: 'underline' (по умолчанию: заливка + подчёркивание)
 *              или 'fill' (сегменты: выбранная — фон поверхности, рамка и тень,
 *              без акцентной заливки; в режиме для слабовидящих выбранная
 *              инвертируется и получает внутреннюю рамку)
 *
 * Активная вкладка отмечается НЕ только цветом (жирность + подчёркивание):
 * режим для слабовидящих принудительно перекрашивает все button.
 */
export default function Tabs({
  tabs,
  active,
  onChange,
  label,
  idPrefix = 'tabs',
  fill = false,
  indicator = 'underline',
  className,
}) {
  const listRef = useRef(null);

  const focusTab = (id) => {
    onChange(id);
    requestAnimationFrame(() => {
      listRef.current?.querySelector(`#${tabButtonId(idPrefix, id)}`)?.focus();
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
      className={[
        styles.tabs,
        fill && styles.fill,
        indicator === 'fill' && styles.indicatorFill,
        className,
      ].filter(Boolean).join(' ')}
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
            id={tabButtonId(idPrefix, tab.id)}
            aria-selected={isActive}
            aria-controls={tabPanelId(idPrefix, tab.id)}
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
