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

// Closed/read-only беседа: меню действий не показывается (нельзя удалять/править).
test('no actions menu in a closed conversation', () => {
  renderWindow({ closed: true });
  expect(screen.queryByRole('button', { name: 'Действия с сообщением' })).not.toBeInTheDocument();
});
