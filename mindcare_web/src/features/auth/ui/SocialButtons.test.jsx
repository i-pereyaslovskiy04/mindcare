import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import SocialButtons from './SocialButtons';
import * as authApi from '../../../api/auth.api';
import * as configApi from '../../../api/config.api';
import * as oauthLib from '../lib/oauthCallback';

jest.mock('../../../api/auth.api', () => ({ oauthStart: jest.fn() }));
jest.mock('../../../api/config.api', () => ({
  ...jest.requireActual('../../../api/config.api'),
  getPublicConfig: jest.fn(),
}));
jest.mock('../lib/oauthCallback', () => ({
  ...jest.requireActual('../lib/oauthCallback'),
  navigateToProvider: jest.fn(),
}));

const AUTHORIZE_URL = 'https://oauth.yandex.ru/authorize?state=SYNTHETIC';
const VK_AUTHORIZE_URL = 'https://id.vk.ru/authorize?state=SYNTHETIC_VK';
const PROVIDER_KEY = 'mindcare_oauth_provider';
// Собирается из частей: литерал script-URL в исходнике запрещён линтером.
const SCRIPT_URL = ['javascript', 'alert(1)'].join(':');

const yandexButton = () => screen.getByRole('button', { name: 'Войти через Яндекс' });
const vkButton = () => screen.getByRole('button', { name: /ВКонтакте/ });

beforeEach(() => {
  jest.clearAllMocks();
  sessionStorage.clear();
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex'] });
});

async function showWithYandex() {
  render(<SocialButtons />);
  await waitFor(() => expect(yandexButton()).toBeEnabled());
}

async function showWithBoth() {
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['yandex', 'vk'] });
  render(<SocialButtons />);
  await waitFor(() => expect(vkButton()).toBeEnabled());
}

// ── состав блока ─────────────────────────────────────────────────────────────

test('ровно две кнопки — VK и Яндекс; Telegram нет', async () => {
  await showWithYandex();
  expect(screen.getAllByRole('button')).toHaveLength(2);
  expect(vkButton()).toBeInTheDocument();
  expect(yandexButton()).toBeInTheDocument();
  expect(screen.queryByText(/Telegram/i)).toBeNull();
  expect(screen.getByText('или продолжить с email')).toBeInTheDocument();
});

test('VK без адаптера на backend: видна, но disabled и без единого запроса', async () => {
  await showWithYandex();
  expect(vkButton()).toBeDisabled();
  fireEvent.click(vkButton());
  expect(authApi.oauthStart).not.toHaveBeenCalled();
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
});

test('VK активна, только когда backend сообщил провайдера vk', async () => {
  await showWithBoth();
  expect(vkButton()).toBeEnabled();
  expect(vkButton()).not.toHaveAttribute('title');
  expect(yandexButton()).toBeEnabled();
});

test('только vk на backend → VK активна, Яндекс disabled', async () => {
  configApi.getPublicConfig.mockResolvedValue({ social_providers: ['vk'] });
  render(<SocialButtons />);
  await waitFor(() => expect(vkButton()).toBeEnabled());
  expect(yandexButton()).toBeDisabled();
  fireEvent.click(yandexButton());
  expect(authApi.oauthStart).not.toHaveBeenCalled();
});

// ── клик по VK ───────────────────────────────────────────────────────────────

test('клик по VK → один oauthStart("vk"), переход и запомненный провайдер', async () => {
  authApi.oauthStart.mockResolvedValue({ authorize_url: VK_AUTHORIZE_URL });
  await showWithBoth();
  fireEvent.click(vkButton());

  await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalledWith(VK_AUTHORIZE_URL));
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(authApi.oauthStart).toHaveBeenCalledWith('vk');
  expect(sessionStorage.getItem(PROVIDER_KEY)).toBe('vk');
});

test('загрузка не смешивается: идёт старт VK — «Переход…» только у VK, второй старт невозможен', async () => {
  authApi.oauthStart.mockReturnValue(new Promise(() => {}));
  await showWithBoth();
  fireEvent.click(vkButton());

  await waitFor(() => expect(vkButton()).toHaveAttribute('aria-busy', 'true'));
  expect(vkButton()).toHaveTextContent('Переход…');
  expect(yandexButton()).not.toHaveAttribute('aria-busy');
  expect(yandexButton()).toHaveTextContent('Яндекс');
  expect(yandexButton()).toBeDisabled();          // общий state-cookie: один старт за раз
  fireEvent.click(yandexButton());
  fireEvent.click(vkButton());
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(authApi.oauthStart).toHaveBeenCalledWith('vk');
});

test('идёт старт Яндекса — «Переход…» только у Яндекса', async () => {
  authApi.oauthStart.mockReturnValue(new Promise(() => {}));
  await showWithBoth();
  fireEvent.click(yandexButton());

  await waitFor(() => expect(yandexButton()).toHaveAttribute('aria-busy', 'true'));
  expect(vkButton()).not.toHaveAttribute('aria-busy');
  expect(vkButton()).toHaveTextContent('VK');
  expect(authApi.oauthStart).toHaveBeenCalledWith('yandex');
});

test.each([
  [{ status: 404, code: 'oauth_provider_unavailable' },
    'Вход через VK сейчас недоступен. Войдите по email и паролю.'],
  [{ status: 500 }, 'Не удалось начать вход через VK. Попробуйте ещё раз.'],
])('ошибка start VK %j → текст про VK, обе кнопки снова доступны', async (props, message) => {
  authApi.oauthStart.mockRejectedValue(Object.assign(new Error('RAW internal detail'), props));
  await showWithBoth();
  fireEvent.click(vkButton());

  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText(/RAW internal/)).toBeNull();
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
  expect(vkButton()).toBeEnabled();
  expect(yandexButton()).toBeEnabled();
  expect(sessionStorage.getItem(PROVIDER_KEY)).toBeNull();   // переход не состоялся
});

// ── доступность Яндекса ──────────────────────────────────────────────────────

test('Яндекс недоступен на backend → кнопка видна, но disabled', async () => {
  configApi.getPublicConfig.mockResolvedValue({ social_providers: [] });
  render(<SocialButtons />);
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  expect(yandexButton()).toBeDisabled();
  fireEvent.click(yandexButton());
  expect(authApi.oauthStart).not.toHaveBeenCalled();
});

test('конфиг не загрузился → Яндекс disabled, компонент не падает', async () => {
  configApi.getPublicConfig.mockRejectedValue(new Error('network'));
  render(<SocialButtons />);
  await waitFor(() => expect(configApi.getPublicConfig).toHaveBeenCalled());
  expect(yandexButton()).toBeDisabled();
  expect(vkButton()).toBeDisabled();
});

test('до ответа конфига Яндекс не активен', () => {
  configApi.getPublicConfig.mockReturnValue(new Promise(() => {}));
  render(<SocialButtons />);
  expect(yandexButton()).toBeDisabled();
});

// ── клик по Яндексу ──────────────────────────────────────────────────────────

test('клик → один oauthStart("yandex") и top-level переход', async () => {
  authApi.oauthStart.mockResolvedValue({ authorize_url: AUTHORIZE_URL });
  await showWithYandex();
  fireEvent.click(yandexButton());

  await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalledWith(AUTHORIZE_URL));
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(authApi.oauthStart).toHaveBeenCalledWith('yandex');   // без intent вкладки
});

test('во время старта повторный клик не шлёт второй start', async () => {
  authApi.oauthStart.mockReturnValue(new Promise(() => {}));
  await showWithYandex();
  fireEvent.click(yandexButton());
  fireEvent.click(yandexButton());
  fireEvent.click(yandexButton());

  await waitFor(() => expect(yandexButton()).toBeDisabled());
  expect(authApi.oauthStart).toHaveBeenCalledTimes(1);
  expect(yandexButton()).toHaveAttribute('aria-busy', 'true');
});

test('в storage пишется только имя провайдера — ни адрес, ни state', async () => {
  const setItem = jest.spyOn(Storage.prototype, 'setItem');
  authApi.oauthStart.mockResolvedValue({ authorize_url: AUTHORIZE_URL });
  await showWithYandex();
  fireEvent.click(yandexButton());
  await waitFor(() => expect(oauthLib.navigateToProvider).toHaveBeenCalled());
  expect(setItem.mock.calls).toEqual([[PROVIDER_KEY, 'yandex']]);
  expect(JSON.stringify(setItem.mock.calls)).not.toMatch(/authorize|SYNTHETIC|state/);
  expect(localStorage.length).toBe(0);
  setItem.mockRestore();
});

test.each([
  [{ status: 429 }, 'Слишком много попыток. Попробуйте немного позже.'],
  [{ status: 404, code: 'oauth_provider_unavailable' },
    'Вход через Яндекс сейчас недоступен. Войдите по email и паролю.'],
  [{ status: 500 }, 'Не удалось начать вход через Яндекс. Попробуйте ещё раз.'],
])('ошибка start %j → безопасное сообщение, кнопка снова доступна', async (props, message) => {
  authApi.oauthStart.mockRejectedValue(Object.assign(new Error('RAW internal detail'), props));
  await showWithYandex();
  fireEvent.click(yandexButton());

  expect(await screen.findByRole('alert')).toHaveTextContent(message);
  expect(screen.queryByText(/RAW internal/)).toBeNull();
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
  expect(yandexButton()).toBeEnabled();
});

test.each([
  [{}], [{ authorize_url: '' }], [{ authorize_url: SCRIPT_URL }],
  [{ authorize_url: 'http://oauth.yandex.ru/authorize' }],
])('некорректный authorize_url (%j) → без перехода', async (payload) => {
  authApi.oauthStart.mockResolvedValue(payload);
  await showWithYandex();
  fireEvent.click(yandexButton());
  expect(await screen.findByRole('alert'))
    .toHaveTextContent('Не удалось начать вход через Яндекс. Попробуйте ещё раз.');
  expect(oauthLib.navigateToProvider).not.toHaveBeenCalled();
});
