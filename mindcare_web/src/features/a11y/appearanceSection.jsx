import A11yToggle from './A11yToggle';

/**
 * «Оформление» — одна точка входа в шапках (CabinetHeader и Navbar главной):
 * ThemeToggle compact с этой секцией. Контексты темы и режима для
 * слабовидящих не смешиваются — шапка лишь компонует готовые компоненты.
 */
export const APPEARANCE_LABEL = 'Оформление и версия для слабовидящих';

export const A11Y_APPEARANCE_SECTION = {
  title: 'Версия для слабовидящих',
  // Переключение версии сразу меняет оформление всей страницы и открывает
  // A11yPanel под шапкой — панель «Оформление» закрываем, фокус — на триггер.
  render: ({ close }) => <A11yToggle block onToggle={close} />,
};
