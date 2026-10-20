import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { useSearchParams } from 'react-router-dom';
import * as chatApi from '../../../api/chat.api';
import ChatPage from './ChatPage';

// react-router-dom (v7) не резолвится jest-резолвером проекта — virtual mock
// (LinkifiedText рендерит router <Link> для внутренних ссылок system-сообщений;
// useSearchParams — deep-link ?system=1).
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => require('react').createElement(
    'a', { href: to, 'data-router-link': 'true', ...rest }, children,
  ),
  useSearchParams: jest.fn(),
}), { virtual: true });

jest.mock('../../../api/chat.api');

// jsdom не реализует scrollIntoView (используется в MessageList) — полифилл.
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

let currentSearch = '';
let setSearchParamsMock;

beforeEach(() => {
  currentSearch = '';
  setSearchParamsMock = jest.fn((next) => {
    currentSearch = new URLSearchParams(next).toString();
  });
  useSearchParams.mockImplementation(() => [
    new URLSearchParams(currentSearch),
    setSearchParamsMock,
  ]);
  chatApi.getStudentConversations.mockResolvedValue({
    items: [
      {
        uuid: 'eng-1',
        partner: { id: 2, full_name: 'Иван Петров' },
        engagement_status: 'active',
        last_message_at: null,
        unread_count: 0,
        peer_is_online: true,
      },
    ],
    total: 1,
    page: 1,
    size: 20,
  });
  chatApi.getStudentConversationMessages.mockResolvedValue({
    items: [
      {
        id: 1,
        uuid: 'm1',
        sender_id: 2,
        sender_role: 'psychologist',
        is_mine: false,
        content: 'Здравствуйте',
        created_at: new Date().toISOString(),
        read_at: null,
      },
    ],
  });
  chatApi.sendStudentConversationMessage.mockResolvedValue({});
  chatApi.markStudentConversationRead.mockResolvedValue({ updated_count: 0 });
  chatApi.getSystemConversation.mockResolvedValue({ conversation: null });
  chatApi.getSystemMessages.mockResolvedValue({ items: [] });
  chatApi.markSystemConversationRead.mockResolvedValue({ updated_count: 0 });
});

test('student ChatPage renders dialog list (list mode)', async () => {
  render(<ChatPage />);
  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  expect(
    screen.getByRole('heading', { level: 2, name: 'Системные сообщения' }),
  ).toBeInTheDocument();
});

test('student ChatPage opens thread (back button path) without crashing', async () => {
  render(<ChatPage />);
  const item = await screen.findByText('Иван Петров');
  fireEvent.click(item);
  // шапка чата с back-кнопкой + сообщение собеседника
  expect(await screen.findByLabelText('Назад к списку диалогов')).toBeInTheDocument();
  expect(await screen.findByText('Здравствуйте')).toBeInTheDocument();
});

function renderPage(query = '') {
  currentSearch = query;
  return render(<ChatPage />);
}

const SYSTEM_CONV = {
  uuid: 'sys-1', type: 'system', last_message_at: new Date().toISOString(), unread_count: 1,
};
const SYSTEM_MSG = {
  id: 10,
  uuid: 'sm-10',
  sender_id: null,
  sender_role: 'system',
  is_mine: false,
  content: 'Ваша учётная запись создана.',
  created_at: new Date().toISOString(),
  read_at: null,
};

test('без ?system=1 системная беседа не открывается и mark-read не вызывается', async () => {
  chatApi.getSystemConversation.mockResolvedValue({ conversation: SYSTEM_CONV });
  renderPage();
  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
  expect(chatApi.getSystemMessages).not.toHaveBeenCalled();
  expect(chatApi.markSystemConversationRead).not.toHaveBeenCalled();
  expect(setSearchParamsMock).not.toHaveBeenCalled();
});

test('?system=1 открывает системную беседу, mark-read — существующим механизмом, query очищается', async () => {
  chatApi.getSystemConversation.mockResolvedValue({ conversation: SYSTEM_CONV });
  chatApi.getSystemMessages.mockResolvedValue({ items: [SYSTEM_MSG] });
  renderPage('system=1');

  expect(await screen.findByText('Ваша учётная запись создана.')).toBeInTheDocument();
  expect(chatApi.getSystemMessages).toHaveBeenCalledWith({ limit: 100 });
  await waitFor(() => expect(chatApi.markSystemConversationRead).toHaveBeenCalledTimes(1));
  expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
  // Обычный диалог не открывался.
  expect(chatApi.getStudentConversationMessages).not.toHaveBeenCalled();
});

test('?system=1 ждёт загрузки системной беседы и до неё query не трогает', async () => {
  let resolveMeta;
  chatApi.getSystemConversation.mockReturnValue(new Promise((resolve) => {
    resolveMeta = resolve;
  }));
  renderPage('system=1');

  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  expect(setSearchParamsMock).not.toHaveBeenCalled();
  expect(chatApi.getSystemMessages).not.toHaveBeenCalled();

  resolveMeta({ conversation: SYSTEM_CONV });
  await waitFor(() => expect(chatApi.getSystemMessages).toHaveBeenCalledWith({ limit: 100 }));
  await waitFor(() => expect(chatApi.markSystemConversationRead).toHaveBeenCalledTimes(1));
  expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
});

test('?system=1 без системной беседы открывает её пустое состояние', async () => {
  renderPage('system=1');
  expect(await screen.findByText('Системных сообщений пока нет.')).toBeInTheDocument();
  expect(setSearchParamsMock).toHaveBeenCalledWith({}, { replace: true });
});

test('?system=1 убирает только свой параметр, остальные сохраняются', async () => {
  renderPage('system=1&from=bell');
  await waitFor(() => {
    expect(setSearchParamsMock).toHaveBeenCalledWith({ from: 'bell' }, { replace: true });
  });
});

test('system=0 ничего не открывает и query не трогает', async () => {
  renderPage('system=0');
  expect(await screen.findByText('Иван Петров')).toBeInTheDocument();
  await waitFor(() => expect(chatApi.getSystemConversation).toHaveBeenCalled());
  expect(chatApi.getSystemMessages).not.toHaveBeenCalled();
  expect(setSearchParamsMock).not.toHaveBeenCalled();
});
