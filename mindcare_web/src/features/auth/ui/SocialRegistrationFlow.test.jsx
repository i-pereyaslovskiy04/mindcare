/**
 * Регистрация через внешний провайдер внутри AuthModal: машина шагов
 * SocialRegistrationFlow (Stage Social Auth 4, VK-1B). Сеть (auth.api) и
 * AuthContext подменены; шаги email и кода — НАСТОЯЩИЕ, под шпионами.
 * Перенос `/auth/callback` → главная → AuthModal и реальные сетевые вызовы —
 * в `socialRegistration.integration.test.jsx`.
 */
import { StrictMode } from 'react';
import { act, fireEvent, render, screen, waitFor } from '@testing-library/react';
import SocialRegistrationFlow, { SOCIAL_STEP } from './SocialRegistrationFlow';
import * as AuthContext from '../AuthContext';
import * as authApi from '../../../api/auth.api';

const mockNavigate = jest.fn();
jest.mock('react-router-dom', () => ({
  useNavigate: () => mockNavigate,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
jest.mock('../../../api/auth.api', () => ({
  oauthRegistrationInit: jest.fn(),
  oauthRegistrationPreview: jest.fn(),
}));
// Шпионы над НАСТОЯЩИМИ шагами: считают монтирования, рендер не подменяется
// (реализация восстанавливается в beforeEach — CRA resetMocks).
jest.mock('./SocialEmailStep', () => {
  const actual = jest.requireActual('./SocialEmailStep');
  return { __esModule: true, ...actual, default: jest.fn() };
});
// eslint-disable-next-line import/first
import SocialEmailStep from './SocialEmailStep';

jest.mock('./RegistrationOtpStep', () => {
  const actual = jest.requireActual('./RegistrationOtpStep');
  return { __esModule: true, ...actual, default: jest.fn() };
});
// eslint-disable-next-line import/first
import RegistrationOtpStep from './RegistrationOtpStep';

const ActualSocialEmailStep = jest.requireActual('./SocialEmailStep').default;
const ActualRegistrationOtpStep = jest.requireActual('./RegistrationOtpStep').default;

const TICKET = 'tkt_REG_SYNTHETIC_zyxwvutsrqponmlk';
const MASKED = 'i***@yandex.ru';
const NEW_EMAIL = 'student.new@donnu.ru';

let completeOAuthRegistration;
let onExit;
let onStepChange;

beforeEach(() => {
  jest.clearAllMocks();
  SocialEmailStep.mockImplementation(ActualSocialEmailStep);
  RegistrationOtpStep.mockImplementation(ActualRegistrationOtpStep);
  completeOAuthRegistration = jest.fn().mockResolvedValue({ roles: ['student'] });
  AuthContext.useAuth.mockReturnValue({ completeOAuthRegistration, loading: false });
  authApi.oauthRegistrationPreview.mockResolvedValue({
    provider: 'vk', email_masked: null, email_allowed: false, email_editable: true,
  });
  authApi.oauthRegistrationInit.mockResolvedValue({ message: 'ok', email_masked: MASKED });
  onExit = jest.fn();
  onStepChange = jest.fn();
  sessionStorage.clear();
  localStorage.clear();
});

const VK = Object.freeze({ ticket: TICKET, provider: 'vk', emailStep: true });
const YANDEX = Object.freeze({ ticket: TICKET, provider: 'yandex', emailStep: false });

function renderFlow(registration, wrap = (ui) => ui) {
  return render(wrap(
    <SocialRegistrationFlow
      registration={registration}
      onExit={onExit}
      onStepChange={onStepChange}
    />,
  ));
}

const strict = (ui) => <StrictMode>{ui}</StrictMode>;
const codeStep = () => screen.findByRole('group', { name: 'Код подтверждения' });
const emailStep = () => screen.findByRole('heading', { name: 'Почта для регистрации' });
const emailField = () => screen.getByLabelText('Электронная почта');

function typeCode(value = '123456') {
  fireEvent.paste(screen.getByLabelText('Цифра 1'), {
    clipboardData: { getData: () => value },
  });
}

function submitManual(email = NEW_EMAIL) {
  fireEvent.change(emailField(), { target: { value: email } });
  fireEvent.click(screen.getByRole('button', { name: 'Получить код' }));
}

function previewGives(over) {
  authApi.oauthRegistrationPreview.mockResolvedValue({
    provider: 'vk', email_masked: null, email_allowed: false, email_editable: true, ...over,
  });
}

/** Терминальный выход: обычная AuthModal «Вход» с фиксированным текстом. */
function expectTerminalExit(message) {
  expect(onExit).toHaveBeenCalledTimes(1);
  expect(onExit).toHaveBeenCalledWith({ tab: 'login', message, messageTone: 'error' });
  expect(JSON.stringify(onExit.mock.calls)).not.toMatch(/RAW|SECRET|tkt_REG/);
  expect(mockNavigate).not.toHaveBeenCalled();
}

/**
 * Пишет КАЖДОЕ состояние DOM с момента первого коммита: появлялись ли поле
 * кода, заголовок шага кода и какой статус был виден. MutationObserver ловит
 * даже кратковременную вставку узлов («вспышку»).
 */
function recordDom() {
  const seen = [];
  const snapshot = () => {
    seen.push({
      otpField: screen.queryByLabelText('Цифра 1') !== null,
      otpTitle: screen.queryByText('Подтверждение регистрации') !== null,
      emailTitle: screen.queryByText('Почта для регистрации') !== null,
      status: screen.queryByRole('status')?.textContent ?? '',
    });
  };
  const observer = new MutationObserver(snapshot);
  observer.observe(document.body, { subtree: true, childList: true, characterData: true });
  return { seen, snapshot, stop: () => observer.disconnect() };
}

// ── Яндекс: фиксированный email → автоматический код → шаг кода ──────────────

describe('Яндекс (email фиксирован)', () => {
  test('код отправляется автоматически; до ответа — статус, шага кода нет', async () => {
    let resolveInit;
    authApi.oauthRegistrationInit.mockReturnValue(new Promise((r) => { resolveInit = r; }));
    const dom = recordDom();
    const { container } = renderFlow(YANDEX);
    dom.snapshot();

    expect(screen.getByRole('status')).toHaveTextContent('Отправляем код подтверждения…');
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET });
    expect(RegistrationOtpStep).not.toHaveBeenCalled();
    expect(dom.seen.some((s) => s.otpField || s.otpTitle)).toBe(false);

    await act(async () => { resolveInit({ message: 'ok', email_masked: MASKED }); });
    dom.stop();

    expect(await codeStep()).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Подтверждение регистрации' })).toBeInTheDocument();
    expect(screen.getByText(MASKED)).toBeInTheDocument();
    expect(screen.queryByRole('status')).toBeNull();
    expect(container.innerHTML).not.toContain(TICKET);
    // Ни preview, ни шага email у Яндекса нет.
    expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
    expect(SocialEmailStep).not.toHaveBeenCalled();
    expect(dom.seen.some((s) => s.emailTitle)).toBe(false);
    expect(onStepChange).toHaveBeenLastCalledWith(SOCIAL_STEP.OTP);
  });

  test('шаг кода: только код и согласие — без имени, email, пароля и вкладок', async () => {
    renderFlow(YANDEX);
    await codeStep();

    expect(screen.queryByLabelText('Имя')).toBeNull();
    expect(screen.queryByLabelText(/почта|Email/i)).toBeNull();
    expect(screen.queryByLabelText(/Пароль/)).toBeNull();
    expect(screen.queryAllByRole('textbox').filter(
      (el) => !/Цифра/.test(el.getAttribute('aria-label') || ''),
    )).toEqual([]);
    expect(screen.queryByRole('tablist')).toBeNull();
    expect(screen.getByRole('checkbox')).not.toBeChecked();
    expect(screen.getByText(/Отправить повторно через/)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Начать заново' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Изменить email' })).toBeNull();
  });

  test('StrictMode: автоматический init ровно один', async () => {
    renderFlow(YANDEX, strict);
    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET });
    expect(authApi.oauthRegistrationPreview).not.toHaveBeenCalled();
  });

  test('без согласия код не подтверждается', async () => {
    renderFlow(YANDEX);
    await codeStep();
    typeCode();
    fireEvent.click(screen.getByRole('button', { name: 'Подтвердить' }));

    expect(await screen.findByText('Необходимо принять политику персональных данных'))
      .toBeInTheDocument();
    await new Promise((r) => setTimeout(r, 200));
    expect(completeOAuthRegistration).not.toHaveBeenCalled();
  });

  test('код + согласие → сессия через AuthContext → /dashboard', async () => {
    renderFlow(YANDEX);
    await codeStep();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard'));
    expect(mockNavigate).toHaveBeenCalledTimes(1);
    expect(completeOAuthRegistration).toHaveBeenCalledTimes(1);
    // Confirm не получает email — только ticket, код и согласие.
    expect(completeOAuthRegistration).toHaveBeenCalledWith(TICKET, '123456', true);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(onExit).not.toHaveBeenCalled();
  });

  test('повторная отправка — тот же ticket без адреса, таймер заново', async () => {
    jest.useFakeTimers();
    try {
      renderFlow(YANDEX);
      await act(async () => { await Promise.resolve(); });
      for (let i = 0; i < 61; i += 1) {
        // eslint-disable-next-line no-await-in-loop
        await act(async () => { jest.advanceTimersByTime(1000); });
      }
      fireEvent.click(screen.getByRole('button', { name: 'Отправить повторно' }));
      // Дать ответу init обновить шаг внутри act (таймеры подменены).
      await act(async () => { await Promise.resolve(); await Promise.resolve(); });
      expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(2);

      expect(authApi.oauthRegistrationInit.mock.calls[1][0]).toEqual({ ticket: TICKET });
      expect(await screen.findByText(/Отправить повторно через/)).toBeInTheDocument();
    } finally {
      jest.useRealTimers();
    }
  });

  test.each([
    [{ status: 409, code: 'email_already_exists' },
      'Аккаунт с таким email уже существует. Войдите по email и паролю.'],
    [{ status: 400, code: 'oauth_ticket_invalid' },
      'Время на завершение регистрации истекло. Начните заново через Яндекс.'],
    [{ status: 500, code: 'email_delivery_failed' }, 'Не удалось отправить письмо. Попробуйте позже.'],
    [{ status: 500 }, 'Не удалось завершить регистрацию. Попробуйте ещё раз.'],
  ])('ошибка автоматического init %j → обычная AuthModal «Вход» с текстом', async (props, text) => {
    authApi.oauthRegistrationInit.mockRejectedValue(
      Object.assign(new Error('RAW server SECRET'), props),
    );
    renderFlow(YANDEX);

    await waitFor(() => expect(onExit).toHaveBeenCalled());
    expectTerminalExit(text);
    expect(screen.queryByRole('alert')).toBeNull();
    expect(RegistrationOtpStep).not.toHaveBeenCalled();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
  });

  test('email занят на confirm → отказ на шаге кода, подтверждение и повтор заблокированы', async () => {
    completeOAuthRegistration.mockRejectedValue(Object.assign(new Error('x'), {
      status: 409, code: 'email_already_exists',
    }));
    renderFlow(YANDEX);
    await codeStep();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    expect(await screen.findByText(
      'Аккаунт с таким email уже существует. Войдите по email и паролю.',
    )).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Подтвердить' })).toBeDisabled();
    expect(screen.queryByText(/Отправить повторно/)).toBeNull();
    expect(onExit).not.toHaveBeenCalled();          // остаётся только «Начать заново»
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('«Начать заново» → выход на вкладку «Регистрация», backend не вызывается', async () => {
    renderFlow(YANDEX);
    await codeStep();
    authApi.oauthRegistrationInit.mockClear();

    fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));

    expect(onExit).toHaveBeenCalledTimes(1);
    expect(onExit).toHaveBeenCalledWith({ tab: 'register' });
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
    expect(completeOAuthRegistration).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });
});

// ── VK ID: preview → шаг email → шаг кода ────────────────────────────────────

describe('VK ID (email выбирает пользователь)', () => {
  test('preview один раз → шаг email; код и шаг кода не появляются', async () => {
    let resolvePreview;
    authApi.oauthRegistrationPreview.mockReturnValue(new Promise((r) => { resolvePreview = r; }));
    const dom = recordDom();
    const { container } = renderFlow(VK);
    dom.snapshot();

    expect(screen.getByRole('status')).toHaveTextContent('Готовим регистрацию…');
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledWith({ ticket: TICKET });
    expect(SocialEmailStep).not.toHaveBeenCalled();             // до ответа preview шага нет

    await act(async () => {
      resolvePreview({ provider: 'vk', email_masked: null, email_allowed: false, email_editable: true });
    });
    await emailStep();
    dom.stop();

    expect(emailField()).toHaveValue('');
    expect(emailField()).not.toHaveAttribute('readonly');
    expect(screen.getByRole('button', { name: 'Получить код' })).toBeInTheDocument();
    // Ни автоматической отправки кода, ни шага кода.
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
    expect(RegistrationOtpStep).not.toHaveBeenCalled();
    expect(dom.seen.some((s) => s.otpField || s.otpTitle)).toBe(false);
    expect(dom.seen.some((s) => /Отправляем код/.test(s.status))).toBe(false);
    expect(container.innerHTML).not.toContain(TICKET);
    expect(onExit).not.toHaveBeenCalled();
    expect(onStepChange).toHaveBeenLastCalledWith(SOCIAL_STEP.EMAIL);
  });

  test('VK вернул разрешённый email → адрес только для чтения, «Продолжить» шлёт init без email', async () => {
    previewGives({ email_masked: 'i***@donnu.ru', email_allowed: true });
    renderFlow(VK);
    await emailStep();

    expect(emailField()).toHaveValue('i***@donnu.ru');
    expect(emailField()).toHaveAttribute('readonly');
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));

    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET, email: null });
    expect(screen.getByText(MASKED)).toBeInTheDocument();       // маска из ответа init
  });

  test('ручной ввод → init с адресом → шаг кода → согласие + код → /dashboard', async () => {
    authApi.oauthRegistrationInit.mockResolvedValue({ message: 'ok', email_masked: 's***@donnu.ru' });
    renderFlow(VK);
    await emailStep();
    submitManual();

    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET, email: NEW_EMAIL });
    expect(screen.getByText('s***@donnu.ru')).toBeInTheDocument();
    expect(screen.queryByText(NEW_EMAIL)).toBeNull();           // raw адрес на шаге кода не показан
    expect(screen.getByRole('button', { name: 'Изменить email' })).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Начать заново' })).toBeNull();
    expect(onStepChange).toHaveBeenLastCalledWith(SOCIAL_STEP.OTP);

    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();
    await waitFor(() => expect(mockNavigate).toHaveBeenCalledWith('/dashboard'));
    // Confirm не получает email — только ticket, код и согласие.
    expect(completeOAuthRegistration).toHaveBeenCalledWith(TICKET, '123456', true);
    expect(mockNavigate).toHaveBeenCalledTimes(1);
  });

  test.each([
    ['домен не разрешён',
      { status: 422, code: 'domain_not_allowed',
        message: 'Регистрация доступна только для разрешённых почтовых доменов.' },
      'Регистрация доступна только для разрешённых почтовых доменов.'],
    ['email занят', { status: 409, code: 'email_already_exists', message: 'RAW' },
      'Аккаунт с таким email уже существует. Войдите по email и паролю.'],
    ['лимит', { status: 429, code: 'rate_limited' }, 'Слишком много попыток. Попробуйте немного позже.'],
  ])('исправимая ошибка (%s) остаётся на шаге email, можно указать другой адрес', async (_, props, text) => {
    authApi.oauthRegistrationInit
      .mockRejectedValueOnce(Object.assign(new Error(props.message || 'x'), props))
      .mockResolvedValueOnce({ message: 'ok', email_masked: 'o***@donnu.ru' });
    renderFlow(VK);
    await emailStep();
    submitManual('taken@donnu.ru');

    expect(await screen.findByText(text)).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Почта для регистрации' })).toBeInTheDocument();
    expect(onExit).not.toHaveBeenCalled();                      // поток не прерывается
    expect(RegistrationOtpStep).not.toHaveBeenCalled();
    expect(emailField()).toHaveValue('taken@donnu.ru');         // ввод сохранён

    submitManual('other@donnu.ru');                             // исправили
    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenLastCalledWith({
      ticket: TICKET, email: 'other@donnu.ru',
    });
  });

  test.each([
    [{ status: 400, code: 'oauth_ticket_invalid' },
      'Время на завершение регистрации истекло. Начните заново через VK.'],
    [{ status: 409, code: 'oauth_identity_already_linked' },
      'Этот аккаунт VK уже привязан к MindCare. Нажмите «VK» ещё раз, чтобы войти.'],
  ])('терминальная ошибка init %j → обычная AuthModal «Вход»', async (props, text) => {
    authApi.oauthRegistrationInit.mockRejectedValue(Object.assign(new Error('RAW'), props));
    renderFlow(VK);
    await emailStep();
    submitManual();
    await waitFor(() => expect(onExit).toHaveBeenCalled());
    expectTerminalExit(text);
  });

  test('ошибка preview → обычная AuthModal «Вход», шага email нет', async () => {
    authApi.oauthRegistrationPreview.mockRejectedValue(
      Object.assign(new Error('RAW'), { status: 400, code: 'oauth_ticket_invalid' }),
    );
    renderFlow(VK);
    await waitFor(() => expect(onExit).toHaveBeenCalled());
    expectTerminalExit('Время на завершение регистрации истекло. Начните заново через VK.');
    expect(SocialEmailStep).not.toHaveBeenCalled();
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
  });

  test('«Изменить email» с шага кода → шаг email с текущим адресом; новый адрес → новый код', async () => {
    authApi.oauthRegistrationInit
      .mockResolvedValueOnce({ message: 'ok', email_masked: 'a***@donnu.ru' })
      .mockResolvedValueOnce({ message: 'ok', email_masked: 'b***@donnu.ru' });
    renderFlow(VK);
    await emailStep();
    submitManual('a.address@donnu.ru');
    await codeStep();

    fireEvent.click(screen.getByRole('button', { name: 'Изменить email' }));
    await emailStep();
    expect(screen.queryByRole('group', { name: 'Код подтверждения' })).toBeNull();
    expect(emailField()).toHaveValue('a***@donnu.ru');          // адрес, привязанный сейчас
    expect(emailField()).toHaveAttribute('readonly');
    expect(onExit).not.toHaveBeenCalled();
    expect(onStepChange).toHaveBeenLastCalledWith(SOCIAL_STEP.EMAIL);

    fireEvent.click(screen.getByRole('button', { name: /Указать другую/ }));
    submitManual('b.address@donnu.ru');
    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(2);
    expect(authApi.oauthRegistrationInit).toHaveBeenLastCalledWith({
      ticket: TICKET, email: 'b.address@donnu.ru',
    });
    expect(screen.getByText('b***@donnu.ru')).toBeInTheDocument();
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);   // preview — один раз
  });

  test('вернулись на шаг email и нажали «Продолжить» под cooldown → обратно к вводу кода', async () => {
    authApi.oauthRegistrationInit
      .mockResolvedValueOnce({ message: 'ok', email_masked: 'a***@donnu.ru' })
      .mockRejectedValueOnce(Object.assign(new Error('Повторная отправка доступна через 50 с'), {
        status: 429, code: 'otp_cooldown',
      }));
    renderFlow(VK);
    await emailStep();
    submitManual('a.address@donnu.ru');
    await codeStep();
    fireEvent.click(screen.getByRole('button', { name: 'Изменить email' }));
    await emailStep();
    fireEvent.click(screen.getByRole('button', { name: 'Продолжить' }));

    await codeStep();
    expect(screen.getByText('a***@donnu.ru')).toBeInTheDocument();
    expect(onExit).not.toHaveBeenCalled();
  });

  test('email занят на confirm → ошибка на шаге кода, адрес можно изменить', async () => {
    completeOAuthRegistration.mockRejectedValue(Object.assign(new Error('x'), {
      status: 409, code: 'email_already_exists',
    }));
    renderFlow(VK);
    await emailStep();
    submitManual();
    await codeStep();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    expect(await screen.findByText(
      'Аккаунт с таким email уже существует. Войдите по email и паролю.',
    )).toBeInTheDocument();
    expect(onExit).not.toHaveBeenCalled();                      // не терминально для VK
    fireEvent.click(screen.getByRole('button', { name: 'Изменить email' }));
    await emailStep();
  });

  test('ticket истёк на confirm → обычная AuthModal «Вход»', async () => {
    completeOAuthRegistration.mockRejectedValue(Object.assign(new Error('RAW'), {
      status: 400, code: 'oauth_ticket_invalid',
    }));
    renderFlow(VK);
    await emailStep();
    submitManual();
    await codeStep();
    fireEvent.click(screen.getByRole('checkbox'));
    typeCode();

    await waitFor(() => expect(onExit).toHaveBeenCalled());
    expectTerminalExit('Время на завершение регистрации истекло. Начните заново через VK.');
  });

  test('«Начать заново» на шаге email → выход на вкладку «Регистрация», backend не вызывается', async () => {
    renderFlow(VK);
    await emailStep();
    fireEvent.click(screen.getByRole('button', { name: 'Начать заново' }));
    expect(onExit).toHaveBeenCalledTimes(1);
    expect(onExit).toHaveBeenCalledWith({ tab: 'register' });
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();
    expect(mockNavigate).not.toHaveBeenCalled();
  });

  test('StrictMode: preview ровно один, init — ровно один на действие', async () => {
    renderFlow(VK, strict);
    await emailStep();
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).not.toHaveBeenCalled();

    fireEvent.change(emailField(), { target: { value: NEW_EMAIL } });
    const submit = screen.getByRole('button', { name: 'Получить код' });
    fireEvent.click(submit);
    fireEvent.click(submit);                                    // двойной клик
    await codeStep();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1);
  });

  test('ticket и адрес не попадают в storage, URL, DOM и navigation', async () => {
    const setItem = jest.spyOn(Storage.prototype, 'setItem');
    const { container } = renderFlow(VK);
    await emailStep();
    submitManual();
    await codeStep();

    expect(setItem).not.toHaveBeenCalled();
    expect(window.location.href).not.toContain(TICKET);
    expect(window.location.href).not.toContain(NEW_EMAIL);
    expect(JSON.stringify(window.history.state ?? null)).not.toMatch(/tkt_REG|donnu/);
    expect(container.innerHTML).not.toContain(TICKET);
    expect(container.innerHTML).not.toContain(NEW_EMAIL);
    expect(mockNavigate).not.toHaveBeenCalled();
    setItem.mockRestore();
  });

  test('preview сообщил «адрес фиксирован» → шаг email пропускается (автоматический init)', async () => {
    previewGives({ provider: 'yandex', email_masked: MASKED, email_allowed: true, email_editable: false });
    renderFlow(VK);
    await codeStep();
    expect(SocialEmailStep).not.toHaveBeenCalled();
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1);
    expect(authApi.oauthRegistrationInit).toHaveBeenCalledWith({ ticket: TICKET });
  });
});

// ── выход из потока: поздние ответы игнорируются ─────────────────────────────

describe('после выхода из потока', () => {
  test('модалку закрыли во время preview: поздняя ошибка не открывает её заново', async () => {
    let rejectPreview;
    authApi.oauthRegistrationPreview.mockReturnValue(new Promise((_, r) => { rejectPreview = r; }));
    const { unmount } = renderFlow(VK);
    await waitFor(() => expect(authApi.oauthRegistrationPreview).toHaveBeenCalledTimes(1));

    unmount();                                                  // владелец забыл ticket
    await act(async () => {
      rejectPreview(Object.assign(new Error('x'), { status: 400, code: 'oauth_ticket_invalid' }));
    });
    expect(onExit).not.toHaveBeenCalled();
  });

  test('модалку закрыли во время отправки кода: поздний успех не показывает шаг кода', async () => {
    let resolveInit;
    authApi.oauthRegistrationInit.mockReturnValue(new Promise((r) => { resolveInit = r; }));
    const { unmount } = renderFlow(VK);
    await emailStep();
    submitManual();
    await waitFor(() => expect(authApi.oauthRegistrationInit).toHaveBeenCalledTimes(1));

    unmount();
    await act(async () => { resolveInit({ message: 'ok', email_masked: MASKED }); });
    expect(RegistrationOtpStep).not.toHaveBeenCalled();
    expect(onExit).not.toHaveBeenCalled();
  });
});

test('тексты шагов: без длинного тире и символов стрелок', async () => {
  const { container } = renderFlow(VK);
  await emailStep();
  expect(container.textContent).not.toMatch(/[—–←→]/);
  submitManual();
  await codeStep();
  expect(container.textContent).not.toMatch(/[—–←→]/);
});
