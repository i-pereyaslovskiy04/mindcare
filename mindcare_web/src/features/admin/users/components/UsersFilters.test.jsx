import { fireEvent, render, screen, within } from '@testing-library/react';
import UsersFilters from './UsersFilters';

const FILTERS = { role: '', showDisabled: false };

// Не «render*»: правило testing-library принимает такое имя за результат render().
function setup(overrides = {}) {
  const props = {
    query: '',
    onQueryChange: jest.fn(),
    filters: FILTERS,
    onFiltersChange: jest.fn(),
    ...overrides,
  };
  render(<UsersFilters {...props} />);
  return props;
}

function openRoleSelect() {
  // Единственный Select — роль (селектора статуса больше нет).
  fireEvent.click(screen.getByRole('button', { name: /Все роли/ }));
  return screen.getByRole('listbox');
}

test('фильтр ролей: student подписан «Пользователь» из общей карты, остальные подписи прежние', () => {
  setup();
  const options = within(openRoleSelect()).getAllByRole('option');
  expect(options.map((o) => o.textContent)).toEqual([
    'Все роли', 'Пользователь', 'Психолог', 'Администратор', 'Супервизор',
  ]);
  expect(screen.queryByRole('option', { name: 'Студент' })).toBeNull();
});

test('выбор «Пользователь» отправляет прежний код роли student', () => {
  const props = setup();
  fireEvent.mouseDown(within(openRoleSelect()).getByRole('option', { name: 'Пользователь' }));
  expect(props.onFiltersChange).toHaveBeenCalledWith({ ...FILTERS, role: 'student' });
});

test('выбранная роль student показывается подписью «Пользователь»', () => {
  setup({ filters: { ...FILTERS, role: 'student' } });
  expect(screen.getByRole('button', { name: /Пользователь/ })).toBeInTheDocument();
  expect(screen.queryByText('Студент')).toBeNull();
});

test('видимость задаёт одна галочка «Показать отключённых», селектора статуса нет', () => {
  const props = setup();
  expect(screen.getAllByRole('button', { name: /Все роли/ })).toHaveLength(1);
  expect(screen.queryByText('Показать ранее удалённых')).toBeNull();
  expect(screen.queryByRole('button', { name: /^Все$/ })).toBeNull();
  const checkbox = screen.getByRole('checkbox', { name: 'Показать отключённых' });
  expect(checkbox).not.toBeChecked();
  fireEvent.click(checkbox);
  expect(props.onFiltersChange).toHaveBeenCalledWith({ ...FILTERS, showDisabled: true });
});

test('галочка отражает текущее состояние фильтра', () => {
  setup({ filters: { ...FILTERS, showDisabled: true } });
  expect(screen.getByRole('checkbox', { name: 'Показать отключённых' })).toBeChecked();
});
