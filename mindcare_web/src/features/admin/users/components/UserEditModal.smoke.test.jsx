import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as api from '../../../../api/users.api';
import UserEditModal from './UserEditModal';

jest.mock('../../../../api/users.api');

const USER_INFO = {
  email: 'student@donstu.ru',
  created_at: '2026-01-01T00:00:00Z',
  last_login: null,
};

beforeEach(() => {
  api.getUser.mockResolvedValue({
    full_name: 'Студент Тестов',
    phone: '',
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

test('role field is rendered and current student role is shown (not selectable)', async () => {
  renderModal();

  // дождаться загрузки пользователя
  expect(await screen.findByText('Роль пользователя')).toBeInTheDocument();
  // текущая роль student отображается как значение через displayLabel
  expect(screen.getByRole('button', { name: /Студент/ })).toBeInTheDocument();
});

test('role field appears before phone field in DOM order', async () => {
  renderModal();
  const roleLabel = await screen.findByText('Роль пользователя');
  const phoneLabel = screen.getByText('Телефон');
  // Node.DOCUMENT_POSITION_FOLLOWING (4) => phoneLabel идёт ПОСЛЕ roleLabel
  expect(roleLabel.compareDocumentPosition(phoneLabel) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
});

test('dropdown offers staff roles and NOT student', async () => {
  renderModal();
  const control = await screen.findByRole('button', { name: /Студент/ });
  fireEvent.click(control);

  const options = await screen.findAllByRole('option');
  const labels = options.map((o) => o.textContent);
  expect(labels).toEqual(expect.arrayContaining(['Психолог', 'Супервизор', 'Администратор']));
  expect(screen.queryByRole('option', { name: 'Студент' })).toBeNull();
});

test('selecting a staff role reveals the legal basis block', async () => {
  renderModal();
  const control = await screen.findByRole('button', { name: /Студент/ });
  fireEvent.click(control);

  const psychologist = await screen.findByRole('option', { name: 'Психолог' });
  // Select использует onMouseDown для выбора опции
  fireEvent.mouseDown(psychologist);

  await waitFor(() => {
    expect(screen.getByText('Документ-основание')).toBeInTheDocument();
  });
  expect(screen.getByText(/документированного основания для назначения этой роли/i))
    .toBeInTheDocument();
});
