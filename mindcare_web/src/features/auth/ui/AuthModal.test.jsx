import fs from 'fs';
import path from 'path';
import {
  act, fireEvent, render, screen, waitFor, within,
} from '@testing-library/react';
import AuthModal, { AUTH_MODAL_MODE } from './AuthModal';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../api/auth.api', () => ({
  oauthStart: jest.fn(),
  registerInit: jest.fn(),
  registerConfirm: jest.fn(),
  oauthRegistrationInit: jest.fn(),
  oauthRegistrationPreview: jest.fn(),
}));
jest.mock('../../../api/config.api', () => ({
  ...jest.requireActual('../../../api/config.api'),
  getPublicConfig: jest.fn(),
}));
// RegisterForm читает публичный список доменов; здесь он не важен — пустой.
// Обычная функция, а не jest.fn(): resetMocks (CRA) обнулил бы её реализацию.
jest.mock('../../../api/domains.api', () => ({
  ...jest.requireActual('../../../api/domains.api'),
  getPublicEmailDomains: () => Promise.resolve({ domains: [] }),
}));
jest.mock('../forgot-password/ForgotPasswordModal', () => () => null);

let completeOAuthRegistration;

beforeEach(() => {
  jest.clearAllMocks();
  completeOAuthRegistration = jest.fn().mockResolvedValue({ roles: ['student'] });
  AuthContext.useAuth.mockReturnValue({
    login: jest.fn(), completeOAuthRegistration, loading: false,
  });
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
  authApi.registerInit.mockResolvedValue({ message: 'ok' });
  authApi.oauthRegistrationPreview.mockResolvedValue({
    provider: 'vk', email_masked: null, email_allowed: false, email_editable: true,
  });
  authApi.oauthRegistrationInit.mockResolvedValue({ message: 'ok', email_masked: 's***@donnu.ru' });
});

// Дождаться списка провайдеров (SocialButtons) до действий пользователя.
async function entryReady() {
  await waitFor(() => expect(screen.getByRole('button', { name: 'Войти через Яндекс' })).toBeEnabled());
}

async function openRegisterTab() {
  render(<AuthModal isOpen onClose={jest.fn()} />);
  await entryReady();
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
}

// Скрытая вкладка «Вход» остаётся в DOM — запросы только внутри видимой панели.
const registerPanel = () => screen.getByRole('tabpanel', { name: 'Регистрация' });

function fillAndSubmit() {
  const value = (text) => ({ target: { value: text } });
  fireEvent.change(within(registerPanel()).getByLabelText('Имя'), value('Иван Студентов'));
  fireEvent.change(within(registerPanel()).getByLabelText('Email'), value('student@donnu.ru'));
  fireEvent.change(within(registerPanel()).getByLabelText('Пароль'), value('SecurePass42!'));
  fireEvent.change(within(registerPanel()).getByLabelText('Повторите пароль'), value('SecurePass42!'));
  fireEvent.click(within(registerPanel()).getByRole('checkbox'));
  fireEvent.click(within(registerPanel()).getByRole('button', { name: 'Продолжить' }));
}

test('основная форма: вкладки «Вход | Регистрация» есть', async () => {
  await openRegisterTab();
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(screen.getByRole('tab', { name: 'Вход' })).toBeInTheDocument();
  expect(within(registerPanel()).getByLabelText('Имя')).toBeInTheDocument();
});

test('шаг кода обычной регистрации: общий шаг без вкладок, «Изменить данные» возвращает их', async () => {
  await openRegisterTab();
  fillAndSubmit();

  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
  expect(screen.getByText('student@donnu.ru')).toBeInTheDocument();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(screen.queryByRole('checkbox')).toBeNull();   // согласие уже принято на шаге 1

  fireEvent.click(screen.getByRole('button', { name: '← Изменить данные' }));
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(within(registerPanel()).getByLabelText('Имя')).toHaveValue('Иван Студентов');
  // Форма смонтирована заново — дождаться её списка провайдеров.
  await entryReady();
});

// ── регистрация через провайдера: social-режимы внутри той же модалки ───────

const TICKET = 'tkt_REG_MODAL_0123456789abcdefghij';
const VK = Object.freeze({ ticket: TICKET, provider: 'vk', emailStep: true });
const YANDEX = Object.freeze({ ticket: TICKET, provider: 'yandex', emailStep: false });

const theDialog = () => screen.getByRole('dialog', { name: 'Вход и регистрация' });
const modeOf = () => screen.getByTestId('auth-modal-body').getAttribute('data-mode');
const emailTitle = () => screen.findByRole('heading', { name: 'Почта для регистрации' });

function expectNoEntryUi() {
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('tab')).toBeNull();
  expect(screen.queryByRole('tabpanel', { hidden: true })).toBeNull();
  // Формы входа и регистрации не смонтированы вовсе (даже скрытыми).
  expect(screen.queryByLabelText('Пароль')).toBeNull();
  expect(screen.queryByLabelText('Имя')).toBeNull();
  expect(screen.queryByLabelText('Email')).toBeNull();
  expect(screen.queryByRole('button', { name: 'Войти' })).toBeNull();
  expect(screen.queryByRole('button', { name: /Яндекс/ })).toBeNull();
  expect(configApi.getPublicConfig).not.toHaveBeenCalled();   // SocialButtons не смонтирован
}

test('обычный режим: mode=entry', async () => {
  await openRegisterTab();
  expect(modeOf()).toBe(AUTH_MODAL_MODE.ENTRY);
});

test('socialEmail: шаг email внутри модалки, вкладок и форм входа/регистрации нет', async () => {
  render(<AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={jest.fn()} />);

  const heading = await emailTitle();
  expect(within(theDialog()).getByRole('heading', { name: 'Почта для регистрации' })).toBe(heading);
  expect(modeOf()).toBe(AUTH_MODAL_MODE.SOCIAL_EMAIL);
  expectNoEntryUi();
  expect(within(theDialog()).getByLabelText('Электронная почта')).toHaveValue('');
  expect(within(theDialog()).getByRole('button', { name: 'Получить код' })).toBeInTheDocument();
  // Тот же каркас модалки: один диалог с общим контейнером authBody.
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  expect(within(theDialog()).getByTestId('auth-modal-body')).toHaveClass('authBody');
  expect(document.body.innerHTML).not.toContain(TICKET);
});

test('socialLoading: пока идёт preview — статус, вкладок уже нет', async () => {
  let resolvePreview;
  authApi.oauthRegistrationPreview.mockReturnValue(new Promise((r) => { resolvePreview = r; }));
  render(<AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={jest.fn()} />);

  expect(within(theDialog()).getByRole('status')).toHaveTextContent('Готовим регистрацию…');
  expect(modeOf()).toBe(AUTH_MODAL_MODE.SOCIAL_LOADING);
  expectNoEntryUi();

  resolvePreview({ provider: 'vk', email_masked: null, email_allowed: false, email_editable: true });
  await emailTitle();
});

test('socialOtp: шаг кода в той же модалке, вкладок нет; «Изменить email» возвращает socialEmail', async () => {
  render(<AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={jest.fn()} />);
  await emailTitle();
  fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: 'student@donnu.ru' } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));

  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(within(theDialog()).getByRole('heading', { name: 'Подтверждение регистрации' }))
    .toBeInTheDocument();
  expect(within(theDialog()).getByText('s***@donnu.ru')).toBeInTheDocument();
  await waitFor(() => expect(modeOf()).toBe(AUTH_MODAL_MODE.SOCIAL_OTP));
  expectNoEntryUi();
  expect(screen.getAllByRole('dialog')).toHaveLength(1);
  expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();

  fireEvent.click(screen.getByRole('button', { name: 'Изменить email' }));
  await emailTitle();
  await waitFor(() => expect(modeOf()).toBe(AUTH_MODAL_MODE.SOCIAL_EMAIL));
  expectNoEntryUi();
});

test('Яндекс: сразу socialOtp (код отправлен автоматически), шага email и вкладок нет', async () => {
  render(<AuthModal isOpen onClose={jest.fn()} social={YANDEX} onSocialExit={jest.fn()} />);
  await screen.findByRole('group', { name: 'Код подтверждения' });
  await waitFor(() => expect(modeOf()).toBe(AUTH_MODAL_MODE.SOCIAL_OTP));
  expectNoEntryUi();
  expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET });
  expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Начать заново' })).toBeInTheDocument();
});

test('«Начать заново» → onSocialExit; без social модалка снова обычная, с вкладками', async () => {
  const onSocialExit = jest.fn();
  const { rerender } = render(
    <AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={onSocialExit} />,
  );
  await emailTitle();
  fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
  expect(onSocialExit).toHaveBeenCalledTimes(1);
  expect(onSocialExit).toHaveBeenCalledWith({ tab: 'register' });

  // Владелец забыл ticket и просит вкладку «Регистрация».
  rerender(
    <AuthModal isOpen onClose={jest.fn()} social={null} onSocialExit={onSocialExit} initialTab="register" />,
  );
  await entryReady();
  expect(modeOf()).toBe(AUTH_MODAL_MODE.ENTRY);
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Регистрация');
  expect(within(registerPanel()).getByLabelText('Имя')).toHaveValue('');
  expect(screen.queryByRole('heading', { name: 'Почта для регистрации' })).toBeNull();
  expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
});

test('выход из social-режима на вкладку «Вход» показывает сообщение об ошибке', async () => {
  const text = 'Время на завершение регистрации истекло. Начните заново через VK.';
  const { rerender } = render(
    <AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={jest.fn()} />,
  );
  await emailTitle();
  expect(screen.queryByText(text)).toBeNull();

  rerender(
    <AuthModal isOpen onClose={jest.fn()} social={null} message={text} messageTone="error" />,
  );
  await entryReady();
  expect(screen.getByRole('tab', { selected: true })).toHaveTextContent('Вход');
  expect(screen.getByText(text)).toHaveAttribute('role', 'alert');
  expect(screen.getByText(text)).toHaveClass('errorMessage');
});

test('шаг кода обычной регистрации не «залипает»: после social-режима вкладки на месте', async () => {
  const { rerender } = render(<AuthModal isOpen onClose={jest.fn()} />);
  await entryReady();
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
  fillAndSubmit();
  await screen.findByRole('group', { name: 'Код подтверждения' });
  expect(screen.queryByRole('tablist')).toBeNull();

  rerender(<AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={jest.fn()} />);
  await emailTitle();
  rerender(<AuthModal isOpen onClose={jest.fn()} social={null} />);

  await entryReady();
  expect(screen.getByRole('tablist')).toBeInTheDocument();
  expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
});

// ── юридические ссылки: новая вкладка во всех потоках регистрации ───────────
//
// Переход в той же вкладке выгружает страницу: пропадает заполненная форма, а
// при регистрации через провайдера — ticket, который живёт только в памяти.

const UI_DIR = __dirname;

/** Все ссылки, видимые сейчас в модалке, безопасны: новая вкладка + rel. */
function expectLegalLinksOpenInNewTab() {
  const links = within(theDialog()).getAllByRole('link');
  expect(links.map((link) => link.textContent)).toEqual(['политикой персональных данных']);
  for (const link of links) {
    expect(link).toHaveAttribute('href', '/privacy-policy');          // адрес документа прежний
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  }
}

describe('юридические ссылки открываются в новой вкладке', () => {
  test('обычная регистрация: форма', async () => {
    await openRegisterTab();
    expectLegalLinksOpenInNewTab();
  });

  test('обычная регистрация: на шаге кода ссылок нет (согласие принято на первом шаге)', async () => {
    await openRegisterTab();
    fillAndSubmit();
    await screen.findByRole('group', { name: 'Код подтверждения' });
    expect(within(theDialog()).queryByRole('link')).toBeNull();
  });

  test('Яндекс: шаг кода', async () => {
    render(<AuthModal isOpen onClose={jest.fn()} social={YANDEX} onSocialExit={jest.fn()} />);
    await screen.findByRole('group', { name: 'Код подтверждения' });
    expectLegalLinksOpenInNewTab();
  });

  test('VK: на шаге email ссылок нет, на шаге кода — в новой вкладке', async () => {
    const onSocialExit = jest.fn();
    render(<AuthModal isOpen onClose={jest.fn()} social={VK} onSocialExit={onSocialExit} />);
    await emailTitle();
    expect(within(theDialog()).queryByRole('link')).toBeNull();

    fireEvent.change(screen.getByLabelText('Электронная почта'), { target: { value: 'student@donnu.ru' } });
    fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
    await screen.findByRole('group', { name: 'Код подтверждения' });
    expectLegalLinksOpenInNewTab();

    // Клик по ссылке не прерывает регистрацию: шаг кода на месте, выхода из потока нет.
    fireEvent.click(within(theDialog()).getByRole('link'));
    expect(screen.getByRole('group', { name: 'Код подтверждения' })).toBeInTheDocument();
    expect(onSocialExit).not.toHaveBeenCalled();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  });

  test('в исходниках auth-компонентов нет ссылок, открывающихся в той же вкладке', () => {
    const sources = [];
    const walk = (dir) => {
      for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
        const full = path.join(dir, entry.name);
        if (entry.isDirectory()) walk(full);
        else if (/\.jsx$/.test(entry.name) && !/\.test\.jsx$/.test(entry.name)) sources.push(full);
      }
    };
    walk(path.join(UI_DIR, '..'));                                    // весь features/auth

    const anchors = sources.flatMap((file) => (
      (fs.readFileSync(file, 'utf8').match(/<a\s[^>]*>/g) || [])
        .map((tag) => ({ file: path.basename(file), tag }))
    ));
    expect(anchors.map((a) => a.file).sort()).toEqual(['RegisterForm.jsx', 'RegistrationOtpStep.jsx']);
    for (const { tag } of anchors) {
      expect(tag).toMatch(/target="_blank"/);
      expect(tag).toMatch(/rel="noopener noreferrer"/);
    }
    // И ни одного router-<Link> на документы: он тоже увёл бы с главной.
    for (const file of sources) {
      expect(fs.readFileSync(file, 'utf8')).not.toMatch(/<Link\s/);
    }
  });
});

// ── Подтверждение регистрации по ссылке из письма (/register/confirm#r=…) ───

const confirmEmail = 'student@donnu.ru';
const REF = '8a62d590-71a1-4b17-90f7-4a5ff0c9d782';

// На шаге confirm панели «Вход» и «Регистрация» скрыты, но смонтированы и
// загружают список провайдеров — дожидаемся его (без act-предупреждений).
async function hiddenProvidersReady() {
  await waitFor(() => {
    const buttons = screen.getAllByRole('button', { name: 'Войти через Яндекс', hidden: true });
    buttons.forEach((b) => expect(b).toBeEnabled());
  });
}

function typeCodeIn(container, digits) {
  const group = within(container).getByRole('group', { name: 'Код подтверждения' });
  within(group).getAllByRole('textbox').forEach((input, i) => {
    fireEvent.change(input, { target: { value: digits[i] } });
  });
}

function renderConfirm(props = {}) {
  return render(
    <AuthModal isOpen onClose={jest.fn()} initialTab="confirm" registrationReference={REF} {...props} />,
  );
}

const confirmHeading = () => screen.queryByRole('heading', { name: 'Подтверждение регистрации' });
const confirmBody = () => screen.getByTestId('auth-modal-body');

test('шаг по ссылке: только код, без поля email и без вкладок', async () => {
  renderConfirm();
  await hiddenProvidersReady();
  expect(confirmBody()).toHaveAttribute('data-mode', AUTH_MODAL_MODE.CONFIRM);
  expect(confirmHeading()).toBeInTheDocument();
  expect(screen.getByText('Введите 6-значный код из письма.')).toBeInTheDocument();
  expect(within(confirmBody()).getByRole('group', { name: 'Код подтверждения' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'Начать регистрацию заново' })).toBeInTheDocument();
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Email' })).toBeNull();
  // Reference пользователю не показывается.
  expect(confirmBody()).not.toHaveTextContent(REF);
});

test('успех без владельца маршрута → «Вход» с сообщением и email из ответа, без автовхода', async () => {
  const login = jest.fn();
  AuthContext.useAuth.mockReturnValue({ login, completeOAuthRegistration, loading: false });
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена', email: confirmEmail });
  const onClose = jest.fn();
  renderConfirm({ onClose });
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '482915');

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Регистрация завершена. Войдите в свою учётную запись.',
  );
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
  expect(authApi.registerConfirm).toHaveBeenCalledWith({ registrationReference: REF, code: '482915' });
  expect(screen.getByRole('tab', { name: 'Вход' })).toHaveAttribute('aria-selected', 'true');
  const loginPanel = screen.getByRole('tabpanel', { name: 'Вход' });
  expect(within(loginPanel).getByLabelText('Email')).toHaveValue(confirmEmail);
  expect(within(loginPanel).getByLabelText('Пароль')).toHaveValue('');
  expect(login).not.toHaveBeenCalled();
  expect(onClose).not.toHaveBeenCalled();
  expect(confirmHeading()).toBeNull();
});

test('успех с владельцем маршрута → onRegistrationConfirmed(email), модалка сама вкладку не меняет', async () => {
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена', email: confirmEmail });
  const onRegistrationConfirmed = jest.fn();
  renderConfirm({ onRegistrationConfirmed });
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '482915');
  await waitFor(() => expect(onRegistrationConfirmed).toHaveBeenCalledWith(confirmEmail));
  expect(screen.queryByRole('status')).toBeNull();
});

test('неверный код → ошибка у ячеек, код очищен, шаг открыт', async () => {
  authApi.registerConfirm.mockRejectedValue(Object.assign(
    new Error('Неверный код. Осталось попыток: 4'), { status: 400, code: 'otp_invalid' },
  ));
  renderConfirm();
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '111111');
  const alert = await screen.findByText('Неверный код. Осталось попыток: 4');
  expect(alert).toHaveAttribute('role', 'alert');
  const cells = within(confirmBody()).getAllByRole('textbox');
  cells.forEach((cell) => {
    expect(cell).toHaveValue('');
    expect(cell).toHaveAttribute('aria-invalid', 'true');
    expect(cell).toHaveAttribute('aria-describedby', alert.id);
  });
  expect(confirmHeading()).toBeInTheDocument();
});

test.each([
  ['registration_reference_invalid',
    'Ссылка недействительна или срок её действия истёк. Начните регистрацию заново.'],
  ['otp_expired', 'Срок действия кода истёк. Начните регистрацию заново.'],
  ['otp_attempts_exhausted', 'Попытки ввода кода исчерпаны. Начните регистрацию заново.'],
])('терминальный код %s → объяснение и только «Начать регистрацию заново»', async (code, text) => {
  authApi.registerConfirm.mockRejectedValue(Object.assign(new Error('любой текст'), { status: 400, code }));
  renderConfirm();
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '111111');
  expect(await screen.findByText(text)).toHaveAttribute('role', 'alert');
  expect(within(confirmBody()).queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByRole('button', { name: 'Подтвердить' })).toBeNull();
  expect(screen.getByRole('button', { name: 'Начать регистрацию заново' })).toBeInTheDocument();
});

test('ссылка без reference → объяснение, без кода и без поля email', async () => {
  render(<AuthModal isOpen onClose={jest.fn()} initialTab="confirm" />);
  await hiddenProvidersReady();
  expect(screen.getByText(
    'Эта ссылка не содержит данных для продолжения регистрации. Начните регистрацию заново.',
  )).toBeInTheDocument();
  expect(within(confirmBody()).queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
  expect(screen.queryByRole('textbox', { name: 'Email' })).toBeNull();
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('«Начать регистрацию заново» без владельца → обычная форма регистрации с вкладками', async () => {
  renderConfirm();
  await hiddenProvidersReady();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  await entryReady();
  expect(screen.getByRole('tab', { name: 'Регистрация' })).toHaveAttribute('aria-selected', 'true');
  expect(within(registerPanel()).getByLabelText('Имя')).toHaveValue('');
  expect(authApi.registerInit).not.toHaveBeenCalled();
});

test('«Начать регистрацию заново» с владельцем → onRegistrationRestart', async () => {
  const onRegistrationRestart = jest.fn();
  renderConfirm({ onRegistrationRestart });
  await hiddenProvidersReady();
  fireEvent.click(screen.getByRole('button', { name: 'Начать регистрацию заново' }));
  expect(onRegistrationRestart).toHaveBeenCalledTimes(1);
});

test('loginEmail подставляется в форму входа', async () => {
  render(<AuthModal isOpen onClose={jest.fn()} loginEmail={confirmEmail} />);
  await entryReady();
  const loginPanel = screen.getByRole('tabpanel', { name: 'Вход' });
  expect(within(loginPanel).getByLabelText('Email')).toHaveValue(confirmEmail);
});

test('обычный шаг кода в той же вкладке: confirm и автоматический вход, как раньше', async () => {
  const login = jest.fn().mockResolvedValue({});
  AuthContext.useAuth.mockReturnValue({ login, completeOAuthRegistration, loading: false });
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена' });
  const onClose = jest.fn();
  render(<AuthModal isOpen onClose={onClose} />);
  await entryReady();
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
  fillAndSubmit();
  await screen.findByText(/Отправили 6-значный код/);
  typeCodeIn(screen.getByTestId('auth-modal-body'), '482915');

  await waitFor(() => expect(login).toHaveBeenCalledWith({
    email: 'student@donnu.ru', password: 'SecurePass42!',
  }));
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
  expect(authApi.registerConfirm).toHaveBeenCalledWith({ email: 'student@donnu.ru', code: '482915' });
  expect(onClose).toHaveBeenCalled();
});

test('сбой автовхода после успешного confirm → «Вход» с email, а не использованный код', async () => {
  const login = jest.fn().mockRejectedValue(new Error('Сеть недоступна'));
  AuthContext.useAuth.mockReturnValue({ login, completeOAuthRegistration, loading: false });
  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена' });
  const onClose = jest.fn();
  render(<AuthModal isOpen onClose={onClose} />);
  await entryReady();
  fireEvent.click(screen.getByRole('tab', { name: 'Регистрация' }));
  fillAndSubmit();
  await screen.findByText(/Отправили 6-значный код/);
  typeCodeIn(screen.getByTestId('auth-modal-body'), '482915');

  expect(await screen.findByRole('status')).toHaveTextContent(
    'Регистрация завершена. Войдите в свою учётную запись.',
  );
  expect(screen.getByRole('tab', { name: 'Вход' })).toHaveAttribute('aria-selected', 'true');
  const loginPanel = screen.getByRole('tabpanel', { name: 'Вход' });
  expect(within(loginPanel).getByLabelText('Email')).toHaveValue('student@donnu.ru');
  expect(screen.queryByText(/Отправили 6-значный код/)).toBeNull();
  expect(onClose).not.toHaveBeenCalled();
  expect(authApi.registerConfirm).toHaveBeenCalledTimes(1);
});

// ── смена ссылки в той же вкладке: состояние привязано к reference ──────────

const REF_B = '0f8f2f44-2a8e-4c1e-9d55-0c3b1d1e2a77';
const REF_INVALID_TEXT =
  'Ссылка недействительна или срок её действия истёк. Начните регистрацию заново.';

function modalWith(ref, props = {}) {
  return (
    <AuthModal isOpen onClose={jest.fn()} initialTab="confirm" registrationReference={ref} {...props} />
  );
}

const codeCells = () => within(
  within(confirmBody()).getByRole('group', { name: 'Код подтверждения' }),
).getAllByRole('textbox');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

test('терминальная ошибка ссылки A → ссылка B: шаг кода снова доступен, ошибки A нет', async () => {
  authApi.registerConfirm.mockRejectedValueOnce(Object.assign(
    new Error('любой текст'), { status: 400, code: 'registration_reference_invalid' },
  ));
  const { rerender } = render(modalWith(REF));
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '111111');
  await screen.findByText(REF_INVALID_TEXT);

  rerender(modalWith(REF_B));
  expect(screen.queryByText(REF_INVALID_TEXT)).toBeNull();
  codeCells().forEach((cell) => {
    expect(cell).toHaveValue('');
    expect(cell).toBeEnabled();
    expect(cell).not.toHaveAttribute('aria-invalid');
  });
  await waitFor(() => expect(codeCells()[0]).toHaveFocus());

  authApi.registerConfirm.mockResolvedValue({ message: 'Регистрация завершена', email: confirmEmail });
  typeCodeIn(confirmBody(), '482915');
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenLastCalledWith({
    registrationReference: REF_B, code: '482915',
  }));
});

test('часть кода для ссылки A → ссылка B: код пустой', async () => {
  const { rerender } = render(modalWith(REF));
  await hiddenProvidersReady();
  codeCells().slice(0, 3).forEach((cell, i) => {
    fireEvent.change(cell, { target: { value: '482'[i] } });
  });
  expect(codeCells()[2]).toHaveValue('2');

  rerender(modalWith(REF_B));
  codeCells().forEach((cell) => expect(cell).toHaveValue(''));
  expect(authApi.registerConfirm).not.toHaveBeenCalled();
});

test('поздний успех запроса A после перехода на B: UI B не меняется', async () => {
  const pendingA = deferred();
  authApi.registerConfirm.mockReturnValueOnce(pendingA.promise);
  const onRegistrationConfirmed = jest.fn();
  const { rerender } = render(modalWith(REF, { onRegistrationConfirmed }));
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '111111');
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledTimes(1));

  rerender(modalWith(REF_B, { onRegistrationConfirmed }));
  await act(async () => { pendingA.resolve({ message: 'Регистрация завершена', email: confirmEmail }); });

  expect(onRegistrationConfirmed).not.toHaveBeenCalled();
  expect(screen.queryByRole('status')).toBeNull();
  expect(confirmHeading()).toBeInTheDocument();
  codeCells().forEach((cell) => {
    expect(cell).toHaveValue('');
    expect(cell).toBeEnabled();
  });
  expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
});

test('поздняя ошибка запроса A после перехода на B: ни ошибки, ни терминального экрана A', async () => {
  const pendingA = deferred();
  authApi.registerConfirm.mockReturnValueOnce(pendingA.promise);
  const { rerender } = render(modalWith(REF));
  await hiddenProvidersReady();
  typeCodeIn(confirmBody(), '111111');
  await waitFor(() => expect(authApi.registerConfirm).toHaveBeenCalledTimes(1));

  rerender(modalWith(REF_B));
  await act(async () => {
    pendingA.reject(Object.assign(
      new Error('любой текст'), { status: 400, code: 'registration_reference_invalid' },
    ));
  });

  expect(screen.queryByText(REF_INVALID_TEXT)).toBeNull();
  expect(screen.queryByRole('alert')).toBeNull();
  expect(within(confirmBody()).getByRole('group', { name: 'Код подтверждения' })).toBeInTheDocument();
});
