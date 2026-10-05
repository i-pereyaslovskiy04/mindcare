/**
 * Regression (Stage Social Auth 4, UX hotfix): автоматический
 * POST /api/auth/oauth/registration/init под React StrictMode уходит в сеть
 * ФИЗИЧЕСКИ ровно один раз. auth.api здесь НЕ мокается — считаются реальные
 * вызовы fetch через настоящий apiFetch. После init рендерится общий шаг
 * RegistrationOtpStep (тот же, что у регистрации по паролю) на этой же
 * странице — ни отдельной social-формы, ни второй модалки.
 */
import { StrictMode } from 'react';
import { render, screen } from '@testing-library/react';
import OAuthCallbackPage from './OAuthCallbackPage';
import * as AuthContext from '../AuthContext';
import RegistrationOtpStep from '../ui/RegistrationOtpStep';

jest.mock('react-router-dom', () => ({
  useNavigate: () => jest.fn(),
  Link: ({ to, children, ...rest }) => <a href={to} {...rest}>{children}</a>,
}), { virtual: true });
jest.mock('../AuthContext', () => ({ useAuth: jest.fn() }));
// Обёртка-шпион над НАСТОЯЩИМ общим шагом: рендер не подменяется.
// (resetMocks в CRA сбрасывает реализацию — она восстанавливается в beforeEach.)
jest.mock('../ui/RegistrationOtpStep', () => {
  const actual = jest.requireActual('../ui/RegistrationOtpStep');
  return { __esModule: true, ...actual, default: jest.fn() };
});
const ActualRegistrationOtpStep = jest.requireActual('../ui/RegistrationOtpStep').default;

const TICKET = 'tkt_REG_STRICT_0123456789abcdefghij';
const INIT_PATH = '/api/auth/oauth/registration/init';
let fetchSpy;
const originalFetch = global.fetch;

function initCalls() {
  return fetchSpy.mock.calls.filter(([url]) => String(url).endsWith(INIT_PATH));
}

beforeEach(() => {
  jest.clearAllMocks();
  RegistrationOtpStep.mockImplementation(ActualRegistrationOtpStep);
  AuthContext.useAuth.mockReturnValue({
    completeOAuthLogin: jest.fn(),
    completeOAuthRegistration: jest.fn(),
    loading: false,
  });
  fetchSpy = jest.fn(() => Promise.resolve({
    ok: true,
    status: 200,
    json: () => Promise.resolve({
      message: 'Код подтверждения отправлен на email', email_masked: 'i***@yandex.ru',
    }),
  }));
  global.fetch = fetchSpy;
  window.history.replaceState(null, '', `/auth/callback#result=registration&ticket=${TICKET}`);
});

afterEach(() => {
  global.fetch = originalFetch;
  window.history.replaceState(null, '', '/');
});

test('StrictMode: registration/init физически отправляется ровно один раз', async () => {
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await screen.findByRole('group', { name: 'Код подтверждения' });
  // Даём StrictMode-повторам и микрозадачам шанс отправить лишний запрос.
  await new Promise((r) => setTimeout(r, 50));

  expect(fetchSpy).toHaveBeenCalledTimes(1);
  const calls = initCalls();
  expect(calls).toHaveLength(1);
  const [, options] = calls[0];
  expect(options.method).toBe('POST');
  expect(JSON.parse(options.body)).toEqual({ ticket: TICKET });   // ни email, ни имени
});

test('после init — общий RegistrationOtpStep с маскированным email, без второй формы/модалки', async () => {
  render(<StrictMode><OAuthCallbackPage /></StrictMode>);
  await screen.findByRole('group', { name: 'Код подтверждения' });

  expect(RegistrationOtpStep).toHaveBeenCalled();
  const props = RegistrationOtpStep.mock.calls.at(-1)[0];
  expect(props.email).toBe('i***@yandex.ru');
  expect(props.consent).toEqual(expect.objectContaining({ checked: false }));
  expect(props.backLabel).toBe('← Начать заново');
  expect(JSON.stringify(props)).not.toContain(TICKET);

  expect(screen.getAllByText('Подтверждение регистрации')).toHaveLength(1);
  expect(screen.queryByRole('dialog')).toBeNull();          // не модалка поверх страницы
  expect(screen.queryByRole('tablist')).toBeNull();
  expect(screen.queryByLabelText('Имя')).toBeNull();
  expect(screen.queryByLabelText('Email')).toBeNull();
  expect(screen.queryByText('Завершение регистрации')).toBeNull();   // старая форма
  expect(document.body.innerHTML).not.toContain(TICKET);
});
