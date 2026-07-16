import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as api from '../../../../api/users.api';
import UserEditModal from './UserEditModal';
import { useAuth } from '../../../auth/AuthContext';

jest.mock('../../../../api/users.api');
// useAuth используется для self-admin guard; в unit-smoke мокаем контекст
// (иначе тянется AuthContext → react-router-dom без провайдера). jest.fn()
// (не статичный объект) — чтобы отдельный тест мог переопределить currentUserId
// через mockReturnValue и проверить сравнение id с редактируемым пользователем.
jest.mock('../../../auth/AuthContext', () => ({
  useAuth: jest.fn(),
}));

const USER_INFO = {
  email: 'student@donstu.ru',
  created_at: '2026-01-01T00:00:00Z',
  last_login: null,
};

beforeEach(() => {
  useAuth.mockReturnValue({ user: { id: 1 } });
  api.getUser.mockResolvedValue({
    full_name: 'Студент Тестов',
    phone: '',
    roles: ['student'],
    role: 'student',
    is_active: true,
  });
  api.updateUser.mockResolvedValue({});
});

function renderModal() {
  return render(
    <UserEditModal
      open
      uuid="u1"
      userInfo={USER_INFO}
      onClose={jest.fn()}
      onUpdated={jest.fn()}
    />,
  );
}

test('staff role checkboxes are rendered; student shown read-only (no student checkbox)', async () => {
  renderModal();

  expect(await screen.findByText('Роли пользователя')).toBeInTheDocument();
  // staff-роли — чекбоксы
  expect(screen.getByRole('checkbox', { name: 'Психолог' })).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: 'Супервизор' })).toBeInTheDocument();
  expect(screen.getByRole('checkbox', { name: 'Администратор' })).toBeInTheDocument();
  // student НЕ чекбокс — только read-only badge
  expect(screen.queryByRole('checkbox', { name: 'Студент' })).toBeNull();
  expect(screen.getByText('Студент')).toBeInTheDocument();
});

test('student-only: staff checkboxes are disabled with an explanation, no legal basis reveal', async () => {
  renderModal();
  const psy = await screen.findByRole('checkbox', { name: 'Психолог' });

  // backend разрешает добавление staff-роли только тому, у кого она уже есть —
  // student-only пользователь не может назначить первую staff-роль через edit.
  expect(psy).toBeDisabled();
  expect(screen.getByText(/Назначение служебной роли доступно только/)).toBeInTheDocument();

  fireEvent.click(psy);
  expect(screen.queryByText('Документ-основание')).toBeNull();
  expect(api.updateUser).not.toHaveBeenCalled();
});

test('self-admin: admin checkbox is disabled with explanation when editing own account', async () => {
  useAuth.mockReturnValue({ user: { id: 99 } });
  api.getUser.mockResolvedValueOnce({
    id: 99, full_name: 'Self Admin', phone: '',
    roles: ['admin', 'supervisor'], is_active: true,
  });
  renderModal();

  const adminCb = await screen.findByRole('checkbox', { name: 'Администратор' });
  expect(adminCb).toBeDisabled();
  expect(
    screen.getByText('Нельзя снять у себя роль администратора.'),
  ).toBeInTheDocument();

  // supervisor не заблокирован self-guard'ом (не admin) — можно снять.
  const supCb = screen.getByRole('checkbox', { name: 'Супервизор' });
  expect(supCb).not.toBeDisabled();
});

test('non-self admin: admin checkbox is NOT locked when editing another account', async () => {
  useAuth.mockReturnValue({ user: { id: 1 } }); // current user id !== target id
  api.getUser.mockResolvedValueOnce({
    id: 99, full_name: 'Other Admin', phone: '',
    roles: ['admin', 'supervisor'], is_active: true,
  });
  renderModal();

  const adminCb = await screen.findByRole('checkbox', { name: 'Администратор' });
  expect(adminCb).not.toBeDisabled();
  expect(
    screen.queryByText('Нельзя снять у себя роль администратора.'),
  ).not.toBeInTheDocument();
});

test('user with an existing staff role: checking another staff role reveals the legal basis block', async () => {
  api.getUser.mockResolvedValueOnce({
    full_name: 'Психолог Иванов', phone: '',
    roles: ['psychologist'], is_active: true,
  });
  renderModal();
  const sup = await screen.findByRole('checkbox', { name: 'Супервизор' });

  // до выбора — legal basis скрыт, чекбоксы доступны (уже есть staff-роль)
  expect(screen.queryByText('Документ-основание')).toBeNull();
  expect(sup).not.toBeDisabled();

  fireEvent.click(sup);

  await waitFor(() => {
    expect(screen.getByText('Документ-основание')).toBeInTheDocument();
  });
});
