import { render, screen, fireEvent, waitFor, within } from '@testing-library/react';
import SettingsPage from './SettingsPage';
import { useAuth } from '../../../features/auth/AuthContext';
import * as authApi from '../../../api/auth.api';
import * as verificationApi from '../../../api/studentVerification.api';

const mockNavigate = jest.fn();
const mockLocation = { pathname: '/student/settings', hash: '' };
// react-router-dom (v7) не резолвится jest-резолвером проекта — virtual mock,
// как в CabinetSettingsPage.test.jsx.
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
  useLocation: () => mockLocation,
}), { virtual: true });
jest.mock('../../../features/auth/AuthContext', () => ({
  useAuth: jest.fn(),
}));
jest.mock('../../../api/auth.api');
jest.mock('../../../api/studentVerification.api');

function authState(overrides = {}) {
  return {
    user: { id: '5', roles: ['student'] },
    isImpersonating: false,
    logout: jest.fn(),
    refreshUser: jest.fn(),
    deactivateOwnAccount: jest.fn().mockResolvedValue(undefined),
    clearSession: jest.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  mockNavigate.mockReset();
  mockLocation.hash = '';
  verificationApi.getMyVerification.mockResolvedValue({
    status: 'not_submitted', can_submit: true, current: null,
  });
  verificationApi.getFaculties.mockResolvedValue({
    items: [
      { code: 'law', label: 'Юридический факультет' },
      { code: 'history', label: 'Исторический факультет' },
    ],
  });
  authApi.getProfile.mockResolvedValue({
    full_name: 'Студент Тестов', email: 's@donnu.ru', phone: '', role: 'student',
  });
});

test('pure student sees the deactivation card', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  expect(await screen.findByText('Отключение аккаунта')).toBeInTheDocument();
  expect(
    screen.getByText(/восстановить аккаунт может только\s+администратор/),
  ).toBeInTheDocument();
});

test.each([
  ['staff with implicit student', { user: { id: '5', roles: ['psychologist', 'student'] } }],
  ['admin + student', { user: { id: '5', roles: ['admin', 'student'] } }],
  ['impersonation session', { isImpersonating: true }],
])('card hidden for %s', async (_name, overrides) => {
  useAuth.mockReturnValue(authState(overrides));
  render(<SettingsPage />);
  await screen.findByText('Профиль');
  expect(screen.queryByText('Отключение аккаунта')).toBeNull();
});

test('confirming calls API, navigates to public page, then clears auth', async () => {
  const state = authState();
  useAuth.mockReturnValue(state);
  render(<SettingsPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Отключить аккаунт' }));

  const dialog = screen.getByRole('dialog', {
    name: 'Подтверждение отключения аккаунта',
  });
  expect(within(dialog).getByText(/данные и email сохранятся/)).toBeInTheDocument();
  expect(within(dialog).getByText(/только через администратора/)).toBeInTheDocument();
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отключить аккаунт' }));

  await waitFor(() => expect(state.clearSession).toHaveBeenCalledTimes(1));
  expect(state.deactivateOwnAccount).toHaveBeenCalledTimes(1);
  expect(state.logout).not.toHaveBeenCalled();
  expect(mockNavigate).toHaveBeenCalledWith('/', expect.objectContaining({ replace: true }));
  expect(mockNavigate.mock.invocationCallOrder[0])
    .toBeLessThan(state.clearSession.mock.invocationCallOrder[0]);
});

test('server refusal keeps the session and shows the error', async () => {
  const state = authState({
    deactivateOwnAccount: jest.fn().mockRejectedValue(new Error('Недоступно')),
  });
  useAuth.mockReturnValue(state);
  render(<SettingsPage />);
  fireEvent.click(await screen.findByRole('button', { name: 'Отключить аккаунт' }));
  const dialog = screen.getByRole('dialog', {
    name: 'Подтверждение отключения аккаунта',
  });
  fireEvent.click(within(dialog).getByRole('button', { name: 'Отключить аккаунт' }));

  expect(await screen.findByText('Недоступно')).toBeInTheDocument();
  expect(state.clearSession).not.toHaveBeenCalled();
  expect(mockNavigate).not.toHaveBeenCalled();
});

// ── подпись роли — общая карта shared/lib/roles.js, без локальной копии ──────

test('роль в профиле подписана общей картой: «Пользователь», а не «Студент»', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  expect(await screen.findByText('Пользователь')).toBeInTheDocument();
  // «Студент Тестов» в имени профиля — не подпись роли; отдельного «Студент» нет.
  expect(screen.queryByText('Студент')).toBeNull();
});

test('подписи остальных ролей прежние (общая карта), роль приходит из профиля', async () => {
  authApi.getProfile.mockResolvedValue({
    full_name: 'Иван Тестов', email: 'p@donnu.ru', phone: '', role: 'psychologist',
  });
  useAuth.mockReturnValue(authState({ user: { id: '5', roles: ['psychologist', 'student'] } }));
  render(<SettingsPage />);
  expect(await screen.findByText('Психолог')).toBeInTheDocument();
  expect(screen.queryByText('Пользователь')).toBeNull();
});

// ── Подтверждение студента ДонГУ (ADR-029) ───────────────────────────────────

const PENDING = {
  status: 'pending',
  can_submit: false,
  current: {
    uuid: 'r-1', status: 'pending',
    faculty: { code: 'law', label: 'Юридический факультет' },
    submitted_at: '2026-10-01T09:00:00Z', reviewed_at: null, rejection_reason: null,
  },
};

test('чистый пользователь видит раздел со статусом «Не подтверждено» и формой', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  expect(await within(section).findByText('Не подтверждено')).toBeInTheDocument();
  expect(within(section).getByRole('button', { name: 'Отправить на проверку' }))
    .toBeInTheDocument();
  expect(section).toHaveAttribute('id', 'student-verification');
});

test.each([
  ['staff с неявным student', { user: { id: '5', roles: ['psychologist', 'student'] } }],
  ['режим «под именем»', { isImpersonating: true }],
])('раздел self-service скрыт: %s — статус не запрашивается', async (_n, overrides) => {
  useAuth.mockReturnValue(authState(overrides));
  render(<SettingsPage />);
  await screen.findByText('Профиль');
  expect(screen.queryByRole('button', { name: 'Отправить на проверку' })).toBeNull();
  expect(verificationApi.getMyVerification).not.toHaveBeenCalled();
});

test('подача заявки отправляет код факультета и номер с ведущими нулями', async () => {
  useAuth.mockReturnValue(authState());
  verificationApi.submitMyVerification.mockResolvedValue(PENDING);
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  await waitFor(() => expect(verificationApi.getFaculties).toHaveBeenCalled());
  const trigger = await within(section).findByRole('button', { name: 'Факультет' });

  fireEvent.click(trigger);
  fireEvent.mouseDown(await screen.findByRole('option', { name: 'Юридический факультет' }));
  fireEvent.change(within(section).getByLabelText('Номер студенческого билета'), {
    target: { value: ' 000123 ' },
  });
  fireEvent.click(within(section).getByRole('button', { name: 'Отправить на проверку' }));

  await waitFor(() => expect(verificationApi.submitMyVerification).toHaveBeenCalledWith({
    faculty_code: 'law', ticket_number: '000123',
  }));
  expect(await within(section).findByText('На проверке')).toBeInTheDocument();
  expect(within(section).queryByRole('button', { name: 'Отправить на проверку' })).toBeNull();
});

test('без факультета форма не отправляется', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  fireEvent.change(await within(section).findByLabelText('Номер студенческого билета'), {
    target: { value: '123' },
  });
  fireEvent.click(within(section).getByRole('button', { name: 'Отправить на проверку' }));
  expect(await within(section).findByRole('alert')).toHaveTextContent('Выберите факультет');
  expect(verificationApi.submitMyVerification).not.toHaveBeenCalled();
});

test('отказ: показано пояснение и доступна повторная подача', async () => {
  verificationApi.getMyVerification.mockResolvedValue({
    status: 'rejected',
    can_submit: true,
    current: {
      ...PENDING.current,
      status: 'rejected',
      reviewed_at: '2026-10-02T09:00:00Z',
      rejection_reason: 'Номер не читается',
    },
  });
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  expect(await within(section).findByText('Отклонено')).toBeInTheDocument();
  expect(within(section).getByText('Номер не читается')).toBeInTheDocument();
  expect(within(section).getByRole('button', { name: 'Отправить на проверку' }))
    .toBeInTheDocument();
});

test('подтверждённый: бейдж в профиле, роль по-прежнему «Пользователь»', async () => {
  verificationApi.getMyVerification.mockResolvedValue({
    status: 'approved',
    can_submit: false,
    current: { ...PENDING.current, status: 'approved', reviewed_at: '2026-10-02T09:00:00Z' },
  });
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  expect(await screen.findByText('Студент ДонГУ подтверждён')).toBeInTheDocument();
  expect(screen.getByText('Пользователь')).toBeInTheDocument();
  const section = screen.getByRole('region', { name: 'Подтверждение студента ДонГУ' });
  expect(within(section).getByText('Подтверждено')).toBeInTheDocument();
  expect(within(section).queryByRole('button', { name: 'Отправить на проверку' })).toBeNull();
});

test('ссылка из уведомления (#student-verification) прокручивает к разделу и фокусирует его', async () => {
  const scrollSpy = jest.fn();
  window.HTMLElement.prototype.scrollIntoView = scrollSpy;
  mockLocation.hash = '#student-verification';
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  await waitFor(() => expect(scrollSpy).toHaveBeenCalled());
  expect(scrollSpy.mock.instances[0]).toBe(section);
  expect(section).toHaveFocus();
});

// ── Доступность формы смены пароля ──────────────────────────────────────────

/** Раздел подтверждения студента грузит статус и факультеты асинхронно —
    дожидаемся их, чтобы обновления не приходили после конца теста. */
async function renderSettingsReady() {
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  await within(section).findByText('Не подтверждено');
  await waitFor(() => expect(verificationApi.getFaculties).toHaveBeenCalled());
}

test('поля профиля связаны с подписями; Email остаётся только для чтения', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();

  const fullName = await screen.findByLabelText('ФИО');
  const email = screen.getByLabelText('Email');
  const phone = screen.getByLabelText('Номер телефона');
  expect(fullName).toHaveValue('Студент Тестов');
  expect(email).toHaveValue('s@donnu.ru');
  expect(email).toHaveAttribute('readonly');
  expect(phone).toHaveAttribute('type', 'tel');
  expect(new Set([fullName.id, email.id, phone.id]).size).toBe(3);

  // Часовой пояс — кастомный Select (кнопка): имя через aria-labelledby на
  // видимую подпись, без фиктивного htmlFor.
  const tz = screen.getByRole('button', { name: 'Часовой пояс' });
  expect(tz).toHaveAttribute('aria-haspopup', 'listbox');
  expect(screen.getByText('Часовой пояс')).not.toHaveAttribute('for');
});

test('поля пароля имеют доступные имена и сохраняют autocomplete', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();

  const current = screen.getByLabelText('Текущий пароль');
  const next = screen.getByLabelText('Новый пароль');
  const confirm = screen.getByLabelText('Подтверждение нового пароля');

  expect(current).toHaveAttribute('autocomplete', 'current-password');
  expect(next).toHaveAttribute('autocomplete', 'new-password');
  expect(confirm).toHaveAttribute('autocomplete', 'new-password');
  expect(new Set([current.id, next.id, confirm.id]).size).toBe(3);
  [current, next, confirm].forEach((el) => expect(el).not.toHaveAttribute('aria-describedby'));
});

test('ошибка смены пароля объявляется и описывает поля формы', async () => {
  useAuth.mockReturnValue(authState());
  authApi.changePassword.mockRejectedValue(new Error('Неверный текущий пароль'));
  await renderSettingsReady();

  fireEvent.change(screen.getByLabelText('Текущий пароль'), { target: { value: 'old-pass-1' } });
  fireEvent.change(screen.getByLabelText('Новый пароль'), { target: { value: 'new-pass-12' } });
  fireEvent.change(screen.getByLabelText('Подтверждение нового пароля'), { target: { value: 'new-pass-12' } });
  fireEvent.click(screen.getByRole('button', { name: 'Изменить пароль' }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Неверный текущий пароль');
  ['Текущий пароль', 'Новый пароль', 'Подтверждение нового пароля'].forEach((name) => {
    expect(screen.getByLabelText(name)).toHaveAccessibleDescription('Неверный текущий пароль');
  });
});

// ── Закрытая модалка не доступна с клавиатуры (shared Modal) ────────────────

test('закрытая модалка отключения изолирована (inert), открытая — нет', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();
  const trigger = screen.getByRole('button', { name: 'Отключить аккаунт' });

  // Кнопка «Отключить аккаунт» внутри закрытой модалки не видна дереву
  // доступности и лежит под inert-overlay — до неё не дойти Tab'ом.
  expect(screen.getAllByRole('button', { name: 'Отключить аккаунт' })).toHaveLength(1);
  const closed = screen.getByRole('dialog', { hidden: true, name: 'Подтверждение отключения аккаунта' });
  // eslint-disable-next-line testing-library/no-node-access
  expect(closed.closest('[inert]')).not.toBeNull();

  trigger.focus();
  fireEvent.click(trigger);
  const dialog = screen.getByRole('dialog', { name: 'Подтверждение отключения аккаунта' });
  // eslint-disable-next-line testing-library/no-node-access
  expect(dialog.closest('[inert]')).toBeNull();

  fireEvent.click(within(dialog).getByRole('button', { name: 'Отмена' }));
  expect(screen.queryByRole('dialog')).toBeNull();
  expect(trigger).toHaveFocus();
});
