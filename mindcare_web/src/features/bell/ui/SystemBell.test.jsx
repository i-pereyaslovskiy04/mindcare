import { act, fireEvent, render, screen, waitFor, within } from '@testing-library/react';
import * as chatApi from '../../../api/chat.api';
import { notifyMessagesUpdated } from '../../chat/lib/messagesEvents';
import SystemBell from './SystemBell';

// react-router-dom (v7) не резолвится jest-резолвером проекта — virtual mock.
jest.mock('react-router-dom', () => ({
  Link: ({ children, to, className, onClick }) => (
    <a
      href={to}
      className={className}
      onClick={(e) => { e.preventDefault(); onClick?.(e); }}
    >
      {children}
    </a>
  ),
}), { virtual: true });

jest.mock('../../../api/chat.api');

const today = new Date().toISOString();
const sysMsg = (id, readAt = null, content = `Системное ${id}`) => ({
  id,
  uuid: `sm-${id}`,
  sender_id: null,
  sender_role: 'system',
  is_mine: false,
  content,
  created_at: today,
  read_at: readAt,
  edited_at: null,
  is_deleted: false,
  attachments: [],
});

function mockUnread(count) {
  chatApi.getSystemConversation.mockResolvedValue({
    conversation: { uuid: 'sys-1', type: 'system', last_message_at: today, unread_count: count },
  });
}

/** Рендер + ожидание первого ответа unread_count (без act-предупреждений). */
async function renderBell(cabinetRole = 'student') {
  const utils = render(
    <div>
      <SystemBell cabinetRole={cabinetRole} />
      <button type="button">Дальше</button>
    </div>,
  );
  await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
  return utils;
}

const bellButton = () => screen.getByRole('button', { name: /^Уведомления/ });
const panel = () => screen.getByRole('region', { name: 'Уведомления' });

beforeEach(() => {
  jest.clearAllMocks();
  mockUnread(0);
  chatApi.getSystemMessages.mockResolvedValue({ items: [] });
  chatApi.markSystemConversationRead.mockResolvedValue({ updated_count: 0 });
});

describe('badge', () => {
  test('показывает реальный unread_count системной беседы', async () => {
    mockUnread(3);
    await renderBell();
    expect(await screen.findByRole('button', { name: 'Уведомления, новых: 3' })).toBeInTheDocument();
    expect(within(bellButton()).getByText('3')).toHaveAttribute('aria-hidden', 'true');
    expect(chatApi.getSystemConversation).toHaveBeenCalledTimes(1);
  });

  test('0 → badge нет, без «точки»', async () => {
    await renderBell();
    await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
    const bell = screen.getByRole('button', { name: 'Уведомления' });
    // eslint-disable-next-line testing-library/no-node-access
    expect(bell.querySelector('span')).toBeNull();
  });

  test('больше 99 → «99+», в доступном имени — точное число', async () => {
    mockUnread(150);
    await renderBell();
    const bell = await screen.findByRole('button', { name: 'Уведомления, новых: 150' });
    expect(within(bell).getByText('99+')).toBeInTheDocument();
  });

  test('ошибка загрузки → badge нет', async () => {
    chatApi.getSystemConversation.mockRejectedValue(new Error('network'));
    await renderBell();
    await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
    const bell = screen.getByRole('button', { name: 'Уведомления' });
    // eslint-disable-next-line testing-library/no-node-access
    expect(bell.querySelector('span')).toBeNull();
  });

  test('messagesEvents (mark-read в Messenger) сразу обновляет badge', async () => {
    mockUnread(2);
    await renderBell();
    expect(await screen.findByRole('button', { name: 'Уведомления, новых: 2' })).toBeInTheDocument();

    mockUnread(0);
    act(() => notifyMessagesUpdated());
    expect(await screen.findByRole('button', { name: 'Уведомления' })).toBeInTheDocument();
    expect(chatApi.getSystemConversation).toHaveBeenCalledTimes(2);
  });
});

describe('панель', () => {
  test('открывается: aria-expanded/aria-controls, заголовок «Уведомления»', async () => {
    await renderBell();
    const bell = bellButton();
    expect(bell).toHaveAttribute('aria-expanded', 'false');
    expect(bell).not.toHaveAttribute('aria-controls');

    fireEvent.click(bell);
    expect(bell).toHaveAttribute('aria-expanded', 'true');
    expect(bell).toHaveAttribute('aria-controls', panel().id);
    expect(within(panel()).getByRole('heading', { name: 'Уведомления' })).toBeInTheDocument();

    fireEvent.click(bell);
    expect(bell).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
  });

  test('показывает максимум 5 непрочитанных, новые сверху; прочитанные — нет', async () => {
    mockUnread(6);
    chatApi.getSystemMessages.mockResolvedValue({
      items: [1, 2, 3, 4, 5, 6].map((id) => sysMsg(id)),
    });
    await renderBell();
    fireEvent.click(await screen.findByRole('button', { name: 'Уведомления, новых: 6' }));

    const links = await within(panel()).findAllByRole('link', { name: /^Системное/ });
    expect(links.map((a) => a.textContent.replace(/\d\d:\d\d$/, ''))).toEqual([
      'Системное 6', 'Системное 5', 'Системное 4', 'Системное 3', 'Системное 2',
    ]);
    expect(chatApi.getSystemMessages).toHaveBeenCalledWith({ limit: 5 });
  });

  test('прочитанные сообщения не показываются', async () => {
    mockUnread(1);
    chatApi.getSystemMessages.mockResolvedValue({
      items: [sysMsg(1, today), sysMsg(2, today), sysMsg(3)],
    });
    await renderBell();
    fireEvent.click(bellButton());
    const links = await within(panel()).findAllByRole('link', { name: /^Системное/ });
    expect(links).toHaveLength(1);
    expect(links[0]).toHaveTextContent('Системное 3');
  });

  test('пустое состояние «Новых уведомлений нет», «Показать все» остаётся', async () => {
    chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1, today)] });
    await renderBell('psychologist');
    fireEvent.click(bellButton());
    expect(await within(panel()).findByText('Новых уведомлений нет')).toBeInTheDocument();
    expect(within(panel()).getByRole('link', { name: 'Показать все' }))
      .toHaveAttribute('href', '/psychologist/chat?system=1');
  });

  test('ошибка списка — понятный текст, без ложного пустого состояния', async () => {
    mockUnread(1);
    chatApi.getSystemMessages.mockRejectedValue(new Error('network'));
    await renderBell();
    fireEvent.click(bellButton());
    expect(await within(panel()).findByText('Не удалось загрузить уведомления.')).toBeInTheDocument();
    expect(within(panel()).queryByText('Новых уведомлений нет')).toBeNull();
  });

  test('превью без сырого внутреннего URL', async () => {
    mockUnread(1);
    chatApi.getSystemMessages.mockResolvedValue({
      items: [sysMsg(1, null, 'Подтвердите статус: /student/settings#student-verification')],
    });
    await renderBell();
    fireEvent.click(bellButton());
    const link = await within(panel()).findByRole('link', { name: /Подтвердите статус/ });
    expect(link).toHaveTextContent('Подтвердите статус: Подтверждение студента ДонГУ');
    expect(link).not.toHaveTextContent('/student/settings');
  });

  test('открытие панели НЕ отмечает сообщения прочитанными', async () => {
    mockUnread(2);
    chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1), sysMsg(2)] });
    await renderBell();
    fireEvent.click(await screen.findByRole('button', { name: 'Уведомления, новых: 2' }));
    await within(panel()).findAllByRole('link', { name: /^Системное/ });
    expect(chatApi.markSystemConversationRead).not.toHaveBeenCalled();
    // badge остаётся прежним
    expect(bellButton()).toHaveAccessibleName('Уведомления, новых: 2');
  });
});

describe('переходы', () => {
  test.each([
    ['student', '/student/chat?system=1'],
    ['psychologist', '/psychologist/chat?system=1'],
  ])('%s: пункт и «Показать все» ведут в системную беседу Messenger', async (role, href) => {
    mockUnread(1);
    chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(7)] });
    await renderBell(role);
    fireEvent.click(bellButton());

    const item = await within(panel()).findByRole('link', { name: /Системное 7/ });
    expect(item).toHaveAttribute('href', href);
    expect(within(panel()).getByRole('link', { name: 'Показать все' })).toHaveAttribute('href', href);

    // Клик по пункту закрывает панель; mark-read делает уже Messenger.
    fireEvent.click(item);
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
    expect(chatApi.markSystemConversationRead).not.toHaveBeenCalled();
  });

  test('«Показать все» закрывает панель', async () => {
    await renderBell();
    fireEvent.click(bellButton());
    fireEvent.click(await within(panel()).findByRole('link', { name: 'Показать все' }));
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
  });
});

describe('клавиатура и закрытие', () => {
  test('Escape закрывает и возвращает фокус на колокольчик', async () => {
    await renderBell();
    const bell = bellButton();
    fireEvent.click(bell);
    within(panel()).getByRole('link', { name: 'Показать все' }).focus();

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
    expect(bell).toHaveAttribute('aria-expanded', 'false');
    expect(bell).toHaveFocus();
    await waitFor(() => expect(chatApi.getSystemMessages).toHaveBeenCalled());
  });

  test('клик снаружи закрывает, клик внутри панели — нет', async () => {
    await renderBell();
    fireEvent.click(bellButton());
    fireEvent.mouseDown(within(panel()).getByRole('heading', { name: 'Уведомления' }));
    expect(panel()).toBeInTheDocument();

    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
    await waitFor(() => expect(chatApi.getSystemMessages).toHaveBeenCalled());
  });

  test('панель — сразу после кнопки в порядке Tab, без focus trap; уход фокуса закрывает', async () => {
    mockUnread(1);
    chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1)] });
    await renderBell();
    const bell = bellButton();
    fireEvent.click(bell);
    const item = await within(panel()).findByRole('link', { name: /Системное 1/ });
    const showAll = within(panel()).getByRole('link', { name: 'Показать все' });
    const next = screen.getByRole('button', { name: 'Дальше' });

    // DOM-порядок: кнопка → пункты → «Показать все» → следующий контрол.
    // eslint-disable-next-line no-bitwise
    expect(bell.compareDocumentPosition(item) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // eslint-disable-next-line no-bitwise
    expect(showAll.compareDocumentPosition(next) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();

    // Переход фокуса внутри панели её не закрывает…
    fireEvent.blur(bell, { relatedTarget: item });
    expect(panel()).toBeInTheDocument();
    // …а уход дальше по странице — закрывает (без возврата фокуса).
    fireEvent.blur(showAll, { relatedTarget: next });
    expect(screen.queryByRole('region', { name: 'Уведомления' })).toBeNull();
  });

  test('пункты — ссылки, доступные с клавиатуры', async () => {
    mockUnread(1);
    chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1)] });
    await renderBell();
    fireEvent.click(bellButton());
    const item = await within(panel()).findByRole('link', { name: /Системное 1/ });
    item.focus();
    expect(item).toHaveFocus();
    expect(item.tagName).toBe('A');
  });
});

test('новое непрочитанное при открытой панели — список обновляется', async () => {
  mockUnread(1);
  chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1)] });
  await renderBell();
  fireEvent.click(await screen.findByRole('button', { name: 'Уведомления, новых: 1' }));
  await within(panel()).findByRole('link', { name: /Системное 1/ });

  mockUnread(2);
  chatApi.getSystemMessages.mockResolvedValue({ items: [sysMsg(1), sysMsg(2)] });
  act(() => notifyMessagesUpdated());
  expect(await within(panel()).findByRole('link', { name: /Системное 2/ })).toBeInTheDocument();
  expect(chatApi.markSystemConversationRead).not.toHaveBeenCalled();
});
