import { render, screen } from '@testing-library/react';
import MessageList from './MessageList';

// jsdom не реализует scrollIntoView (используется в MessageList useEffect).
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

const contact = { name: 'Иванова Мария', initials: 'ИМ', authorRole: 'психолог' };

const A = '2024-01-01T10:00:00.000Z';
const B = '2024-01-01T10:00:30.000Z';
const C = '2024-01-01T10:01:00.000Z';

// D. Своё сообщение подписано «Вы».
test('D. own message shows "Вы" author header', () => {
  const messages = [
    { id: 1, text: 'Спасибо, посмотрю', mine: true, senderId: 5, time: '10:00', createdAt: A },
  ];
  render(<MessageList messages={messages} contact={contact} />);
  expect(screen.getByText('Вы')).toBeInTheDocument();
});

// E. Сообщение собеседника подписано ФИО + ролью.
test('E. incoming message shows partner name and role', () => {
  const messages = [
    { id: 1, text: 'Здравствуйте', mine: false, senderId: 7, time: '10:00', createdAt: A },
  ];
  render(<MessageList messages={messages} contact={contact} />);
  expect(screen.getByText('Иванова Мария')).toBeInTheDocument();
  expect(screen.getByText(/психолог/)).toBeInTheDocument();
  expect(screen.queryByText('Вы')).not.toBeInTheDocument();
});

// B (render-level). Подряд идущие сообщения одного автора не дублируют header.
test('consecutive same-sender messages render the author header once', () => {
  const messages = [
    { id: 1, text: 'Первое', mine: false, senderId: 7, time: '10:00', createdAt: A },
    { id: 2, text: 'Второе', mine: false, senderId: 7, time: '10:00', createdAt: B },
    { id: 3, text: 'Третье', mine: false, senderId: 7, time: '10:01', createdAt: C },
  ];
  render(<MessageList messages={messages} contact={contact} />);
  expect(screen.getAllByText('Иванова Мария')).toHaveLength(1);
});

// C (render-level). При смене автора header появляется снова.
test('author header reappears after sender switch', () => {
  const messages = [
    { id: 1, text: 'Здравствуйте', mine: false, senderId: 7, time: '10:00', createdAt: A },
    { id: 2, text: 'Спасибо', mine: true, senderId: 5, time: '10:01', createdAt: C },
  ];
  render(<MessageList messages={messages} contact={contact} />);
  expect(screen.getByText('Иванова Мария')).toBeInTheDocument();
  expect(screen.getByText('Вы')).toBeInTheDocument();
});

// F. System conversation: служебные сообщения без human author header.
test('F. system messages do not render a human author header', () => {
  const messages = [
    { id: 1, text: 'Чат с психологом создан.', system: true, time: '10:00', createdAt: A },
  ];
  render(<MessageList messages={messages} contact={{ name: 'Системные уведомления', initials: '' }} />);
  expect(screen.getByText('Чат с психологом создан.')).toBeInTheDocument();
  expect(screen.queryByText('Вы')).not.toBeInTheDocument();
  expect(screen.queryByText('Системные уведомления')).not.toBeInTheDocument();
});

// G. Архивный/read-only диалог рендерится тем же MessageList → headers работают.
test('G. archived/read-only dialog still shows author headers', () => {
  const messages = [
    { id: 1, text: 'Старое сообщение', mine: false, senderId: 7, time: '10:00', createdAt: A },
    { id: 2, text: 'Мой ответ', mine: true, senderId: 5, time: '10:01', createdAt: C },
  ];
  render(<MessageList messages={messages} contact={contact} />);
  expect(screen.getByText('Иванова Мария')).toBeInTheDocument();
  expect(screen.getByText('Вы')).toBeInTheDocument();
});
