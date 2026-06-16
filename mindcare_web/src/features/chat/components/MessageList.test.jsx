import { render, screen, fireEvent } from '@testing-library/react';
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

// ── Actions menu: Редактировать / Удалить (Stage 31y) ─────────────────────────

const ownMsg = { id: 1, uuid: 'u1', text: 'моё', mine: true, senderId: 5, time: '10:00', createdAt: A };
const inMsg = { id: 2, uuid: 'u2', text: 'входящее', mine: false, senderId: 7, time: '10:00', createdAt: A };

const MENU = 'Действия с сообщением';

// Меню только у своих сообщений, когда чат управляем (manageable=true).
test('actions menu appears only for own manageable user message', () => {
  render(
    <MessageList
      messages={[ownMsg, inMsg]}
      contact={contact}
      manageable
      onStartEdit={jest.fn()}
      onRequestDelete={jest.fn()}
    />,
  );
  expect(screen.getAllByRole('button', { name: MENU })).toHaveLength(1);
});

// manageable=false (closed/archive) → меню нет даже у своих.
test('no actions menu when chat is not manageable (closed/archive)', () => {
  render(<MessageList messages={[ownMsg, inMsg]} contact={contact} manageable={false} />);
  expect(screen.queryByRole('button', { name: MENU })).not.toBeInTheDocument();
});

// System-сообщение не получает меню даже при manageable.
test('no actions menu for system message', () => {
  const sys = { id: 3, text: 'служебное', system: true, time: '10:00', createdAt: A };
  render(
    <MessageList messages={[sys]} contact={{ name: 'Системные', initials: '' }} manageable onStartEdit={jest.fn()} />,
  );
  expect(screen.queryByRole('button', { name: MENU })).not.toBeInTheDocument();
});

// Меню открывается и содержит «Редактировать» и «Удалить».
test('opening the menu shows Редактировать and Удалить', () => {
  render(
    <MessageList messages={[ownMsg]} contact={contact} manageable onStartEdit={jest.fn()} onRequestDelete={jest.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: MENU }));
  expect(screen.getByRole('menuitem', { name: 'Редактировать' })).toBeInTheDocument();
  expect(screen.getByRole('menuitem', { name: 'Удалить' })).toBeInTheDocument();
});

// «Редактировать» из меню запускает существующий edit flow (onStartEdit).
test('menu Редактировать calls onStartEdit with the message', () => {
  const onStartEdit = jest.fn();
  render(
    <MessageList messages={[ownMsg]} contact={contact} manageable onStartEdit={onStartEdit} onRequestDelete={jest.fn()} />,
  );
  fireEvent.click(screen.getByRole('button', { name: MENU }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Редактировать' }));
  expect(onStartEdit).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'u1' }));
});

// «Удалить» из меню вызывает onRequestDelete с сообщением (подтверждение — выше).
test('menu Удалить calls onRequestDelete with the message', () => {
  const onRequestDelete = jest.fn();
  render(
    <MessageList messages={[ownMsg]} contact={contact} manageable onStartEdit={jest.fn()} onRequestDelete={onRequestDelete} />,
  );
  fireEvent.click(screen.getByRole('button', { name: MENU }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  expect(onRequestDelete).toHaveBeenCalledWith(expect.objectContaining({ uuid: 'u1' }));
});

// H. Отредактированное сообщение показывает метку «изменено».
test('H. edited message shows "изменено" label', () => {
  const edited = { ...ownMsg, text: 'новый текст', editedAt: '2024-01-01T10:05:00.000Z' };
  render(<MessageList messages={[edited]} contact={contact} manageable onStartEdit={jest.fn()} />);
  expect(screen.getByText('новый текст')).toBeInTheDocument();
  expect(screen.getByText(/изменено/)).toBeInTheDocument();
});

// J. «Старое» своё сообщение по-прежнему управляемо в активном чате (нет time-limit).
test('J. old own message still has actions menu in active chat', () => {
  const old = { ...ownMsg, createdAt: '2023-01-01T10:00:00.000Z' };
  render(<MessageList messages={[old]} contact={contact} manageable onStartEdit={jest.fn()} onRequestDelete={jest.fn()} />);
  expect(screen.getByRole('button', { name: MENU })).toBeInTheDocument();
});

// ── Deleted messages hidden from the feed (Stage 31y-hotfix) ──────────────────

// Удалённое сообщение НЕ рендерится: ни bubble, ни плейсхолдера, ни меню.
test('deleted message is not rendered at all (no placeholder)', () => {
  const deleted = { ...ownMsg, text: '', deleted: true };
  render(
    <MessageList messages={[deleted]} contact={contact} manageable onStartEdit={jest.fn()} onRequestDelete={jest.fn()} />,
  );
  expect(screen.queryByText('Сообщение удалено')).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: MENU })).not.toBeInTheDocument();
  // ничего не осталось → пустое состояние ленты
  expect(screen.getByText('Сообщений пока нет.')).toBeInTheDocument();
});

// Текст удалённого сообщения не показывается, видимые соседи рендерятся как обычно.
test('deleted message is filtered out, remaining messages still render', () => {
  const deleted = { ...ownMsg, id: 1, uuid: 'u1', text: 'секрет', deleted: true };
  const kept = { id: 2, uuid: 'u2', text: 'видимое', mine: true, senderId: 5, time: '10:01', createdAt: A };
  render(<MessageList messages={[deleted, kept]} contact={contact} manageable onStartEdit={jest.fn()} />);
  expect(screen.queryByText('секрет')).not.toBeInTheDocument();
  expect(screen.queryByText('Сообщение удалено')).not.toBeInTheDocument();
  expect(screen.getByText('видимое')).toBeInTheDocument();
});
