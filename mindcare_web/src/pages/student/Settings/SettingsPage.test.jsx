import { render, screen, fireEvent, waitFor, within, act } from '@testing-library/react';
import SettingsPage from './SettingsPage';
import { useAuth } from '../../../features/auth/AuthContext';
import * as authApi from '../../../api/auth.api';
import * as verificationApi from '../../../api/studentVerification.api';
import * as contactsApi from '../../../api/contacts.api';

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
jest.mock('../../../api/contacts.api');
jest.mock('../../../features/auth/forgot-password/ForgotPasswordModal', () => function ModalStub(props) {
  return props.open ? (
    <div role="dialog" aria-label="Установка пароля">
      <span data-testid="fp-email">{props.initialEmail}</span>
      <span data-testid="fp-locked">{String(Boolean(props.emailLocked))}</span>
      <button type="button" onClick={props.onCompleted}>Завершить установку</button>
    </div>
  ) : null;
});

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
  contactsApi.getMyContacts.mockResolvedValue(CONTACTS_EMPTY);
});

const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'email', label: 'Email', service_kind: null },
  ],
  services: {},
};
const CONTACTS_EMPTY = {
  version: 0, updated_at: null, items: [],
  limits: { max_items: 10, label_max: 80, value_max: 500 }, catalog: CATALOG,
};

const openTab = (name) => fireEvent.click(screen.getByRole('tab', { name }));
// Кнопка сохранения формы карточки — «Сохранить»; контекст задаёт заголовок карточки.
const saveIn = (card) => within(screen.getByRole('region', { name: card }))
  .getByRole('button', { name: 'Сохранить' });

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
  await screen.findByText('Профиль');
  openTab('Безопасность');
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
  await screen.findByText('Профиль');
  openTab('Безопасность');
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

test('пояснение раздела — новый текст, без упоминания супервизора', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  const hint = within(section).getByText(/Вы можете подтвердить, что являетесь студентом/);
  expect(hint.textContent.replace(/\s+/g, ' ').trim()).toBe(
    'Вы можете подтвердить, что являетесь студентом Донецкого государственного '
    + 'университета. Подтверждение не влияет на доступ к тестам и консультациям.',
  );
  expect(section.textContent).not.toMatch(/супервизор/i);
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

test('без факультета: ошибка у поля «Факультет», фокус на нём, заявка не отправляется', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  await waitFor(() => expect(verificationApi.getFaculties).toHaveBeenCalled());
  const ticket = await within(section).findByLabelText('Номер студенческого билета');
  fireEvent.change(ticket, { target: { value: '123' } });
  fireEvent.click(within(section).getByRole('button', { name: 'Отправить на проверку' }));

  const faculty = within(section).getByRole('button', { name: 'Факультет' });
  expect(await within(section).findByRole('alert')).toHaveTextContent('Выберите факультет');
  expect(faculty).toHaveAttribute('aria-invalid', 'true');
  expect(faculty).toHaveAccessibleDescription('Выберите факультет');
  expect(faculty).toHaveFocus();
  expect(ticket).not.toHaveAttribute('aria-invalid');
  expect(verificationApi.submitMyVerification).not.toHaveBeenCalled();

  // Выбор факультета снимает ошибку поля.
  fireEvent.click(faculty);
  fireEvent.mouseDown(await screen.findByRole('option', { name: 'Юридический факультет' }));
  expect(faculty).not.toHaveAttribute('aria-invalid');
  expect(within(section).queryByRole('alert')).toBeNull();
});

test('без номера билета: ошибка у поля номера, фокус на нём, заявка не отправляется', async () => {
  useAuth.mockReturnValue(authState());
  render(<SettingsPage />);
  const section = await screen.findByRole('region', { name: 'Подтверждение студента ДонГУ' });
  await waitFor(() => expect(verificationApi.getFaculties).toHaveBeenCalled());
  fireEvent.click(await within(section).findByRole('button', { name: 'Факультет' }));
  fireEvent.mouseDown(await screen.findByRole('option', { name: 'Юридический факультет' }));
  const ticket = within(section).getByLabelText('Номер студенческого билета');
  fireEvent.change(ticket, { target: { value: '   ' } });
  fireEvent.click(within(section).getByRole('button', { name: 'Отправить на проверку' }));

  expect(await within(section).findByRole('alert'))
    .toHaveTextContent('Укажите номер студенческого билета');
  expect(ticket).toHaveAttribute('aria-invalid', 'true');
  expect(ticket).toHaveAccessibleDescription('Укажите номер студенческого билета');
  expect(ticket).toHaveFocus();
  expect(within(section).getByRole('button', { name: 'Факультет' })).not.toHaveAttribute('aria-invalid');
  expect(verificationApi.submitMyVerification).not.toHaveBeenCalled();

  fireEvent.change(ticket, { target: { value: '000123' } });
  expect(ticket).not.toHaveAttribute('aria-invalid');
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
  expect(section).toBeVisible();
});


// ── Три раздела настроек ─────────────────────────────────────────────────────

describe('разделы настроек', () => {
  it('по умолчанию открыты «Личные данные», остальные панели скрыты, но смонтированы', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    expect(screen.getByRole('tab', { name: 'Личные данные' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Личные данные' })).toBeVisible();
    expect(screen.getByText('Отключение аккаунта')).not.toBeVisible();
    expect(screen.getByText('Основной телефон')).not.toBeVisible();
  });

  it('вкладки переключаются стрелками клавиатуры', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    const first = screen.getByRole('tab', { name: 'Личные данные' });
    first.focus();
    fireEvent.keyDown(first, { key: 'ArrowRight' });
    expect(screen.getByRole('tab', { name: 'Контакты' })).toHaveAttribute('aria-selected', 'true');
    fireEvent.keyDown(screen.getByRole('tab', { name: 'Контакты' }), { key: 'End' });
    expect(screen.getByRole('tab', { name: 'Безопасность' })).toHaveAttribute('aria-selected', 'true');
    expect(screen.getByRole('tabpanel', { name: 'Безопасность' })).toBeVisible();
  });

  it('черновик ФИО переживает переключение разделов', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    const name = await screen.findByLabelText('ФИО');
    fireEvent.change(name, { target: { value: 'Новое Имя' } });
    openTab('Безопасность');
    openTab('Личные данные');
    expect(screen.getByLabelText('ФИО')).toHaveValue('Новое Имя');
  });

  it('ФИО и телефон сохраняются раздельно — каждый шлёт только свой ключ', async () => {
    useAuth.mockReturnValue(authState());
    authApi.updateProfile.mockImplementation(async (fields) => ({
      full_name: fields.full_name ?? 'Студент Тестов', phone: fields.phone ?? '',
    }));
    render(<SettingsPage />);
    fireEvent.change(await screen.findByLabelText('ФИО'), { target: { value: 'Иван Иванов' } });
    fireEvent.click(saveIn('Профиль'));
    await waitFor(() => expect(authApi.updateProfile).toHaveBeenCalledWith({ full_name: 'Иван Иванов' }));
    expect(await screen.findByText('ФИО сохранено.')).toBeInTheDocument();

    openTab('Контакты');
    const phone = await screen.findByLabelText('Номер телефона');
    fireEvent.change(phone, { target: { value: '9491234567' } });
    fireEvent.click(saveIn('Основной телефон'));
    await waitFor(() => expect(authApi.updateProfile).toHaveBeenLastCalledWith({ phone: '+7 (949) 123-45-67' }));
    expect(authApi.updateProfile).toHaveBeenCalledTimes(2);
    expect(await screen.findByText('Телефон сохранён.')).toBeInTheDocument();
  });

  it('очистка телефона отправляет phone: null', async () => {
    authApi.getProfile.mockResolvedValue({
      full_name: 'Студент Тестов', email: 's@donnu.ru', phone: '+7 (949) 123-45-67', role: 'student',
    });
    authApi.updateProfile.mockResolvedValue({ full_name: 'Студент Тестов', phone: null });
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    fireEvent.change(await screen.findByLabelText('Номер телефона'), { target: { value: '' } });
    fireEvent.click(saveIn('Основной телефон'));
    await waitFor(() => expect(authApi.updateProfile).toHaveBeenCalledWith({ phone: null }));
  });

  it('сбой обновления шапки не выглядит как сбой сохранения', async () => {
    const state = authState({ refreshUser: jest.fn().mockRejectedValue(new Error('шапка')) });
    useAuth.mockReturnValue(state);
    authApi.updateProfile.mockResolvedValue({ full_name: 'Иван', phone: '' });
    render(<SettingsPage />);
    fireEvent.change(await screen.findByLabelText('ФИО'), { target: { value: 'Иван' } });
    fireEvent.click(saveIn('Профиль'));
    expect(await screen.findByText('ФИО сохранено.')).toBeInTheDocument();
    expect(screen.queryByText('шапка')).toBeNull();
  });

  it('старой социальной формы и мёртвых настроек больше нет', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    expect(screen.queryByText('Социальные сети')).toBeNull();
    expect(screen.queryByText('Часовой пояс')).toBeNull();
    expect(screen.queryByText('Уведомления')).toBeNull();
    expect(screen.queryByText('Связаться с дежурным')).toBeNull();
    expect(screen.getByRole('link', { name: /Телефон доверия/ })).toHaveAttribute('href', 'tel:88002000122');
  });
});

describe('раздел «Контакты»', () => {
  it('дополнительные контакты запрашиваются при первом открытии раздела', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    expect(contactsApi.getMyContacts).not.toHaveBeenCalled();
    openTab('Контакты');
    await waitFor(() => expect(contactsApi.getMyContacts).toHaveBeenCalledTimes(1));
    openTab('Безопасность');
    openTab('Контакты');
    expect(contactsApi.getMyContacts).toHaveBeenCalledTimes(1);
  });

  it('подпись аудитории для чистого пользователя — психолог и супервизор', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    expect(await screen.findByText(/назначенному психологу и супервизору/)).toBeInTheDocument();
  });

  it('подпись для сотрудника — только назначенный психолог при сопровождении', async () => {
    useAuth.mockReturnValue(authState({ user: { id: '5', roles: ['psychologist', 'student'] } }));
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    const note = await screen.findByText(/при действующем сопровождении/);
    expect(note.textContent).not.toMatch(/супервизор/i);
    expect(note.textContent).not.toMatch(/только вам/i);
  });

  it('в режиме «под именем» — заметка и ни одного запроса контактов', async () => {
    useAuth.mockReturnValue(authState({ isImpersonating: true }));
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    expect(
      (await screen.findAllByText('Недоступно при входе под именем пользователя.')).length,
    ).toBeGreaterThan(0);
    expect(contactsApi.getMyContacts).not.toHaveBeenCalled();
    expect(contactsApi.saveMyContacts).not.toHaveBeenCalled();
  });

  it('добавленный контакт сохраняется вместе с клиентским UUID', async () => {
    useAuth.mockReturnValue(authState());
    contactsApi.saveMyContacts.mockImplementation(async ({ items }) => ({
      ...CONTACTS_EMPTY, version: 1, changed: true, items,
    }));
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    fireEvent.click(await screen.findByRole('button', { name: /Добавить контакт/ }));
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    const valueInputs = within(group).getAllByRole('textbox');
    fireEvent.change(valueInputs[0], { target: { value: '+79001234567' } });
    fireEvent.click(saveIn('Дополнительные контакты'));
    await waitFor(() => expect(contactsApi.saveMyContacts).toHaveBeenCalledTimes(1));
    const [{ version, items }] = contactsApi.saveMyContacts.mock.calls[0];
    expect(version).toBe(0);
    expect(items).toHaveLength(1);
    // Маска основного телефона; сервер нормализует значение к «+цифрам».
    expect(items[0]).toMatchObject({ type: 'phone', value: '+7 (900) 123-45-67', service: null, label: null });
    expect(items[0].id).toMatch(/^[0-9a-f-]{36}$/);
    expect(await screen.findByText('Контакты сохранены.')).toBeInTheDocument();
  });

  it('основной и дополнительный телефон вводятся одинаково (одна маска)', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    fireEvent.click(await screen.findByRole('button', { name: /Добавить контакт/ }));
    const main = screen.getByLabelText('Номер телефона', { selector: '#settings-phone' });
    const extra = within(screen.getByRole('group', { name: 'Контакт 1' })).getByLabelText('Номер телефона');

    ['89491234567', '9491234567', '+7 949 123 45 67', '8949123456712345678'].forEach((typed) => {
      fireEvent.change(main, { target: { value: typed } });
      fireEvent.change(extra, { target: { value: typed } });
      expect(extra).toHaveValue(main.value);
    });
    expect(main).toHaveValue('+7 (949) 123-45-67');
    expect(extra).toHaveAttribute('placeholder', main.getAttribute('placeholder'));
  });
});

describe('раздел «Безопасность»', () => {
  it('пароль есть — форма смены пароля', async () => {
    authApi.getProfile.mockResolvedValue({
      full_name: 'С', email: 's@donnu.ru', phone: '', role: 'student', has_password: true,
    });
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    expect(screen.getByLabelText('Текущий пароль')).toBeInTheDocument();
    expect(screen.queryByText('Установка пароля')).toBeNull();
  });

  it('пароля нет — установка по email вместо смены', async () => {
    authApi.getProfile.mockResolvedValue({
      full_name: 'С', email: 's@donnu.ru', phone: '', role: 'student', has_password: false,
    });
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    expect(await screen.findByText('Установка пароля')).toBeInTheDocument();
    expect(screen.queryByLabelText('Текущий пароль')).toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Установить пароль по email' }));
    expect(screen.getByTestId('fp-email')).toHaveTextContent('s@donnu.ru');
    expect(screen.getByTestId('fp-locked')).toHaveTextContent('true');
  });

  it('установка пароля: navigate → clearSession, logout не вызывается', async () => {
    authApi.getProfile.mockResolvedValue({
      full_name: 'С', email: 's@donnu.ru', phone: '', role: 'student', has_password: false,
    });
    const state = authState();
    useAuth.mockReturnValue(state);
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    fireEvent.click(await screen.findByRole('button', { name: 'Установить пароль по email' }));
    fireEvent.click(screen.getByRole('button', { name: 'Завершить установку' }));
    expect(mockNavigate).toHaveBeenCalledWith('/', expect.objectContaining({
      replace: true,
      state: expect.objectContaining({ openAuth: 'login', message: 'Пароль установлен. Войдите снова.' }),
    }));
    expect(state.clearSession).toHaveBeenCalledTimes(1);
    expect(state.logout).not.toHaveBeenCalled();
    expect(mockNavigate.mock.invocationCallOrder[0])
      .toBeLessThan(state.clearSession.mock.invocationCallOrder[0]);
  });

  it('смена пароля: после успеха navigate → clearSession без logout', async () => {
    authApi.changePassword.mockResolvedValue({});
    const state = authState();
    useAuth.mockReturnValue(state);
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    fireEvent.change(screen.getByLabelText('Текущий пароль'), { target: { value: 'old-password' } });
    fireEvent.change(screen.getByLabelText('Новый пароль'), { target: { value: 'new-password-1' } });
    fireEvent.change(screen.getByLabelText('Повторите новый пароль'), { target: { value: 'new-password-1' } });
    fireEvent.click(screen.getByRole('button', { name: 'Изменить пароль' }));
    expect(await screen.findByText('Пароль изменён. Войдите снова.')).toBeInTheDocument();
    expect(authApi.changePassword).toHaveBeenCalledWith({
      current_password: 'old-password',
      new_password: 'new-password-1',
      new_password_confirm: 'new-password-1',
    });
    await waitFor(() => expect(state.clearSession).toHaveBeenCalledTimes(1), { timeout: 3000 });
    expect(state.logout).not.toHaveBeenCalled();
    expect(mockNavigate).toHaveBeenCalledWith('/', expect.objectContaining({
      state: expect.objectContaining({ message: 'Пароль изменён. Войдите снова.' }),
    }));
  });

  it('уход со страницы до таймера не завершает сессию', async () => {
    authApi.changePassword.mockResolvedValue({});
    const state = authState();
    useAuth.mockReturnValue(state);
    const { unmount } = render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    fireEvent.change(screen.getByLabelText('Текущий пароль'), { target: { value: 'a' } });
    fireEvent.change(screen.getByLabelText('Новый пароль'), { target: { value: 'bbbbbbbb' } });
    fireEvent.change(screen.getByLabelText('Повторите новый пароль'), { target: { value: 'bbbbbbbb' } });
    fireEvent.click(screen.getByRole('button', { name: 'Изменить пароль' }));
    await screen.findByText('Пароль изменён. Войдите снова.');
    unmount();
    await act(async () => { await new Promise((r) => setTimeout(r, 1700)); });
    expect(state.clearSession).not.toHaveBeenCalled();
  });

  it('ошибка смены пароля показана, сессия не трогается', async () => {
    authApi.changePassword.mockRejectedValue(new Error('Неверный текущий пароль'));
    const state = authState();
    useAuth.mockReturnValue(state);
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Безопасность');
    fireEvent.change(screen.getByLabelText('Текущий пароль'), { target: { value: 'x' } });
    fireEvent.change(screen.getByLabelText('Новый пароль'), { target: { value: 'yyyyyyyy' } });
    fireEvent.change(screen.getByLabelText('Повторите новый пароль'), { target: { value: 'yyyyyyyy' } });
    fireEvent.click(screen.getByRole('button', { name: 'Изменить пароль' }));
    expect(await screen.findByText('Неверный текущий пароль')).toBeInTheDocument();
    expect(state.clearSession).not.toHaveBeenCalled();
  });
});

test('якорь #student-verification открывает «Личные данные», даже если ссылка пришла позже', async () => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
  useAuth.mockReturnValue(authState());
  const { rerender } = render(<SettingsPage />);
  await screen.findByText('Профиль');
  openTab('Безопасность');
  expect(screen.getByRole('tabpanel', { name: 'Безопасность' })).toBeVisible();
  mockLocation.hash = '#student-verification';
  rerender(<SettingsPage />);
  expect(screen.getByRole('tab', { name: 'Личные данные' })).toHaveAttribute('aria-selected', 'true');
  expect(screen.getByRole('region', { name: 'Подтверждение студента ДонГУ' })).toBeVisible();
});

describe('оформление разделов', () => {
  it('вкладки настроек — shared Tabs (равные колонки), роли и выбор сохранены', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    const list = screen.getByRole('tablist', { name: 'Разделы настроек' });
    expect(list.className).toMatch(/fill/);
    expect(screen.getAllByRole('tab')).toHaveLength(3);
    expect(screen.getByRole('tab', { name: 'Личные данные' })).toHaveAttribute('aria-selected', 'true');
  });

  it('форма дополнительных контактов: «Способ связи» вместо типа/сервиса, без «Подписи»', async () => {
    useAuth.mockReturnValue(authState());
    render(<SettingsPage />);
    await screen.findByText('Профиль');
    openTab('Контакты');
    fireEvent.click(await screen.findByRole('button', { name: /Добавить контакт/ }));
    const group = screen.getByRole('group', { name: 'Контакт 1' });
    expect(within(group).getByRole('button', { name: 'Способ связи' })).toHaveTextContent('Телефон');
    expect(within(group).queryByLabelText(/Подпись/)).toBeNull();
    expect(within(group).queryByText('Сервис')).toBeNull();
  });
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
  expect(fullName).toHaveValue('Студент Тестов');
  expect(email).toHaveValue('s@donnu.ru');
  expect(email).toHaveAttribute('readonly');
  expect(fullName.id).not.toBe(email.id);
});

test('поля пароля имеют доступные имена и сохраняют autocomplete', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();

  const current = screen.getByLabelText('Текущий пароль');
  const next = screen.getByLabelText('Новый пароль');
  const confirm = screen.getByLabelText('Повторите новый пароль');

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
  openTab('Безопасность');

  fireEvent.change(screen.getByLabelText('Текущий пароль'), { target: { value: 'old-pass-1' } });
  fireEvent.change(screen.getByLabelText('Новый пароль'), { target: { value: 'new-pass-12' } });
  fireEvent.change(screen.getByLabelText('Повторите новый пароль'), { target: { value: 'new-pass-12' } });
  fireEvent.click(screen.getByRole('button', { name: 'Изменить пароль' }));

  const alert = await screen.findByRole('alert');
  expect(alert).toHaveTextContent('Неверный текущий пароль');
  ['Текущий пароль', 'Новый пароль', 'Повторите новый пароль'].forEach((name) => {
    expect(screen.getByLabelText(name)).toHaveAccessibleDescription('Неверный текущий пароль');
  });
});

// ── Закрытая модалка не доступна с клавиатуры (shared Modal) ────────────────

test('закрытая модалка отключения изолирована (inert), открытая — нет', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();
  openTab('Безопасность');
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

// ── Единый стиль страницы: подписи полей и кнопки «Сохранить» ───────────────

test('подписи полей во всех разделах — по тексту, как пишутся', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();
  const section = screen.getByRole('region', { name: 'Подтверждение студента ДонГУ' });

  expect(screen.getByLabelText('ФИО')).toBeInTheDocument();
  const email = screen.getByLabelText('Email');
  expect(email).toHaveAttribute('readonly');
  expect(email).toHaveAccessibleDescription('Используется для входа, изменить нельзя');
  expect(within(section).getByRole('button', { name: 'Факультет' })).toBeInTheDocument();
  expect(within(section).getByLabelText('Номер студенческого билета')).toHaveAttribute('maxlength', '50');

  openTab('Контакты');
  await screen.findByText(/назначенному психологу и супервизору/);
  expect(screen.getByLabelText('Номер телефона', { selector: '#settings-phone' })).toBeInTheDocument();

  openTab('Безопасность');
  ['Текущий пароль', 'Новый пароль', 'Повторите новый пароль'].forEach((name) => {
    expect(screen.getByLabelText(name)).toBeInTheDocument();
  });
  expect(screen.queryByLabelText('Подтверждение нового пароля')).toBeNull();
});

test('в каждом разделе формы карточек сохраняются кнопкой «Сохранить»', async () => {
  useAuth.mockReturnValue(authState());
  await renderSettingsReady();

  const personal = screen.getByRole('tabpanel', { name: 'Личные данные' });
  expect(within(personal).getAllByRole('button', { name: 'Сохранить' })).toHaveLength(1);
  expect(saveIn('Профиль')).toBeInTheDocument();

  openTab('Контакты');
  await screen.findByText(/назначенному психологу и супервизору/);
  const contacts = screen.getByRole('tabpanel', { name: 'Контакты' });
  // Две карточки — у каждой своя «Сохранить» внутри её региона.
  expect(within(contacts).getAllByRole('button', { name: 'Сохранить' })).toHaveLength(2);
  expect(saveIn('Основной телефон')).toBeInTheDocument();
  expect(saveIn('Дополнительные контакты')).toBeInTheDocument();

  openTab('Безопасность');
  const security = screen.getByRole('tabpanel', { name: 'Безопасность' });
  expect(within(security).queryByRole('button', { name: 'Сохранить' })).toBeNull();
  expect(within(security).getByRole('button', { name: 'Изменить пароль' })).toBeInTheDocument();

  ['Сохранить ФИО', 'Сохранить телефон', 'Сохранить контакты'].forEach((name) => {
    expect(screen.queryByRole('button', { name, hidden: true })).toBeNull();
  });
});
