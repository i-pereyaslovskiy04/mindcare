import { fireEvent, render, screen, within } from '@testing-library/react';
import UsersFilters from './UsersFilters';

const FILTERS = { role: '', is_active: '', includeDeleted: false };

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
  // Первый Select — «Все роли»; второй — статус.
  fireEvent.click(screen.getAllByRole('button', { name: /Все роли/ })[0]);
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
