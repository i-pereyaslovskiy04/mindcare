import { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import ChatWindow from './ChatWindow';

// jsdom не реализует scrollIntoView (используется в MessageList).
beforeAll(() => {
  window.HTMLElement.prototype.scrollIntoView = jest.fn();
});

const contact = { id: 'c1', name: 'Иванова Мария', initials: 'ИМ', authorRole: 'психолог' };
const ownMsg = {
  id: 1, uuid: 'u1', text: 'моё сообщение', mine: true, senderId: 5,
  time: '10:00', createdAt: '2024-01-01T10:00:00.000Z',
};

function renderWindow(extra = {}) {
  return render(
    <ChatWindow
      contact={contact}
      messages={[ownMsg]}
      onSend={jest.fn()}
      onEdit={jest.fn()}
      onDelete={jest.fn().mockResolvedValue(true)}
      {...extra}
    />,
  );
}

// Изначально диалог подтверждения закрыт (не в a11y-дереве: overlay aria-hidden).
test('confirmation dialog is not shown initially', () => {
  renderWindow();
  expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
});

// Удалить из меню → открывается подтверждение «Удалить сообщение?».
test('menu Удалить opens the confirmation dialog', () => {
  renderWindow();
  fireEvent.click(screen.getByRole('button', { name: 'Действия с сообщением' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  const dialog = screen.getByRole('dialog');
  expect(dialog).toBeInTheDocument();
  expect(screen.getByText('Удалить сообщение?')).toBeInTheDocument();
});

// После подтверждения вызывается onDelete с uuid сообщения.
test('confirming deletion calls onDelete with the message uuid', async () => {
  const onDelete = jest.fn().mockResolvedValue(true);
  renderWindow({ onDelete });

  fireEvent.click(screen.getByRole('button', { name: 'Действия с сообщением' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  // меню закрылось → в a11y-дереве остаётся кнопка подтверждения «Удалить» диалога
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

  await waitFor(() => expect(onDelete).toHaveBeenCalledWith('u1'));
});

// После успешного удаления сообщение исчезает из ленты (без плейсхолдера).
// Stateful-harness повторяет контракт хука: onDelete(uuid) убирает сообщение из state.
test('after confirming delete the message disappears from the feed (no placeholder)', async () => {
  function Harness() {
    const [messages, setMessages] = useState([ownMsg]);
    const onDelete = (uuid) => {
      setMessages((prev) => prev.filter((m) => m.uuid !== uuid));
      return Promise.resolve(true);
    };
    return (
      <ChatWindow contact={contact} messages={messages} onSend={jest.fn()} onEdit={jest.fn()} onDelete={onDelete} />
    );
  }
  render(<Harness />);

  expect(screen.getByText('моё сообщение')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: 'Действия с сообщением' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Удалить' }));
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

  await waitFor(() => expect(screen.queryByText('моё сообщение')).not.toBeInTheDocument());
  expect(screen.queryByText('Сообщение удалено')).not.toBeInTheDocument();
});

// Closed/read-only беседа: меню действий не показывается (нельзя удалять/править).
test('no actions menu in a closed conversation', () => {
  renderWindow({ closed: true });
  expect(screen.queryByRole('button', { name: 'Действия с сообщением' })).not.toBeInTheDocument();
});

// Stage 31aa: полный edit-flow через ChatWindow — kebab-меню → «Редактировать»
// → composer в edit mode с прежним текстом → submit → onEdit(uuid, newText) →
// edit mode сброшен. Раньше этот путь был покрыт только частями (отдельно
// MessageList/MessageActionsMenu и отдельно MessageInput), без проверки связки.
test('full edit-flow through ChatWindow: kebab menu → edit composer → submit calls onEdit, then resets', async () => {
  const onEdit = jest.fn().mockResolvedValue(true);
  renderWindow({ onEdit });

  fireEvent.click(screen.getByRole('button', { name: 'Действия с сообщением' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Редактировать' }));

  // composer перешёл в edit mode: видна панель + input заполнен старым текстом.
  expect(screen.getByText('Редактирование сообщения')).toBeInTheDocument();
  const input = screen.getByRole('textbox');
  expect(input).toHaveValue('моё сообщение');

  fireEvent.change(input, { target: { value: 'обновлённое сообщение' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

  await waitFor(() => expect(onEdit).toHaveBeenCalledWith('u1', 'обновлённое сообщение'));

  // после успешного submit edit-mode сброшен: баннер исчез, composer вернулся к «Отправить».
  await waitFor(() => expect(screen.queryByText('Редактирование сообщения')).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Отправить' })).toBeInTheDocument();
});
