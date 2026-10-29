import Tabs, { tabButtonId as sharedButtonId, tabPanelId as sharedPanelId } from '../../../../components/UI/Tabs/Tabs';

const PREFIX = 'audit';

export const tabButtonId = (id) => sharedButtonId(PREFIX, id);
export const tabPanelId = (id) => sharedPanelId(PREFIX, id);

/**
 * Вкладки трёх журналов. Тонкая обёртка над shared `Tabs`: прежние id
 * (`audit-tab-*`, `audit-panel-*`), подпись по умолчанию и экспорты сохранены
 * для AuditLogsPage. Вкладки разделов страницы — на всю ширину колонки (`fill`).
 */
export default function AuditTabs({
  tabs, active, onChange, label = 'Журналы аудита', className,
}) {
  return (
    <Tabs
      tabs={tabs}
      active={active}
      onChange={onChange}
      label={label}
      idPrefix={PREFIX}
      fill
      className={className}
    />
  );
}
