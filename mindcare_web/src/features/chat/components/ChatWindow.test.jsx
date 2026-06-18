import { useState } from 'react';
import { render, screen, fireEvent, waitFor, createEvent } from '@testing-library/react';
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

// Helpers for drag events (jsdom DragEvent.dataTransfer is read-only;
// we patch it via Object.defineProperty on the raw DOM event).
function fireDragEnter(element, types = ['Files']) {
  const ev = createEvent.dragEnter(element);
  Object.defineProperty(ev, 'dataTransfer', {
    value: { types, files: [] },
    configurable: true,
  });
  fireEvent(element, ev);
}

function fireDragLeave(element) {
  fireEvent.dragLeave(element);
}

function fireDrop(element, files = []) {
  const ev = createEvent.drop(element);
  Object.defineProperty(ev, 'dataTransfer', {
    value: { types: ['Files'], files },
    configurable: true,
  });
  fireEvent(element, ev);
}

function getChatWindow() {
  return screen.getByTestId('chat-window');
}

// ── Existing tests (unchanged behaviour) ─────────────────────────────────────

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
  fireEvent.click(screen.getByRole('button', { name: 'Удалить' }));

  await waitFor(() => expect(onDelete).toHaveBeenCalledWith('u1'));
});

// После успешного удаления сообщение исчезает из ленты (без плейсхолдера).
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

// Closed/read-only беседа: меню действий не показывается.
test('no actions menu in a closed conversation', () => {
  renderWindow({ closed: true });
  expect(screen.queryByRole('button', { name: 'Действия с сообщением' })).not.toBeInTheDocument();
});

// Stage 31aa: полный edit-flow через ChatWindow.
test('full edit-flow through ChatWindow: kebab menu → edit composer → submit calls onEdit, then resets', async () => {
  const onEdit = jest.fn().mockResolvedValue(true);
  renderWindow({ onEdit });

  fireEvent.click(screen.getByRole('button', { name: 'Действия с сообщением' }));
  fireEvent.click(screen.getByRole('menuitem', { name: 'Редактировать' }));

  expect(screen.getByText('Редактирование сообщения')).toBeInTheDocument();
  const input = screen.getByRole('textbox');
  expect(input).toHaveValue('моё сообщение');

  fireEvent.change(input, { target: { value: 'обновлённое сообщение' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));

  await waitFor(() => expect(onEdit).toHaveBeenCalledWith('u1', 'обновлённое сообщение', { removeAttachmentUuids: [] }));

  await waitFor(() => expect(screen.queryByText('Редактирование сообщения')).not.toBeInTheDocument());
  expect(screen.getByRole('button', { name: 'Отправить' })).toBeInTheDocument();
});

// ── Drag-and-drop (Stage 32f) ─────────────────────────────────────────────────

test('dragEnter with files shows overlay', () => {
  renderWindow();
  fireDragEnter(getChatWindow());
  expect(screen.getByText('Перетащите файлы сюда')).toBeInTheDocument();
});

test('dragEnter with plain text does not show overlay', () => {
  renderWindow();
  fireDragEnter(getChatWindow(), ['text/plain']);
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('dragLeave after dragEnter hides overlay', () => {
  renderWindow();
  fireDragEnter(getChatWindow());
  expect(screen.getByText('Перетащите файлы сюда')).toBeInTheDocument();
  fireDragLeave(getChatWindow());
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('dragEnter counter: nested enter/leave does not hide overlay prematurely', () => {
  renderWindow();
  const el = getChatWindow();
  // Enter twice (simulates moving over a child element)
  fireDragEnter(el);
  fireDragEnter(el);
  // Leave once — counter goes from 2 to 1, overlay must still be visible.
  fireDragLeave(el);
  expect(screen.getByText('Перетащите файлы сюда')).toBeInTheDocument();
  // Leave again — counter reaches 0, overlay hides.
  fireDragLeave(el);
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('drop files adds them to SelectedAttachmentList', async () => {
  renderWindow();
  const file = new File(['content'], 'report.pdf', { type: 'application/pdf' });
  fireDrop(getChatWindow(), [file]);
  await screen.findByText('report.pdf');
});

test('drop hides overlay', () => {
  renderWindow();
  fireDragEnter(getChatWindow());
  expect(screen.getByText('Перетащите файлы сюда')).toBeInTheDocument();
  fireDrop(getChatWindow(), []);
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('drop file-only then click send calls onSend with empty text and files', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  renderWindow({ onSend });
  const file = new File(['content'], 'doc.pdf', { type: 'application/pdf' });
  fireDrop(getChatWindow(), [file]);
  await screen.findByText('doc.pdf');
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('', [file]));
});

test('drag ignored when composer is hidden (closed)', () => {
  renderWindow({ closed: true });
  fireDragEnter(getChatWindow());
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('drag ignored when composer is hidden (readOnly/system)', () => {
  renderWindow({ readOnly: true, readOnlyNotice: 'Системная беседа' });
  fireDragEnter(getChatWindow());
  expect(screen.queryByText('Перетащите файлы сюда')).not.toBeInTheDocument();
});

test('exceeding max files on drop shows error alert', async () => {
  renderWindow();
  const files = Array.from({ length: 6 }, (_, i) =>
    new File(['x'], `f${i}.pdf`, { type: 'application/pdf' }),
  );
  fireDrop(getChatWindow(), files);
  await screen.findByRole('alert');
  expect(screen.getByText(/не больше 5/)).toBeInTheDocument();
});

test('existing selected files are preserved when drop exceeds limit', async () => {
  renderWindow();
  // eslint-disable-next-line testing-library/no-node-access
  const fileInput = document.querySelector('input[type="file"]');
  // First: add 3 files via picker
  const existing = Array.from({ length: 3 }, (_, i) =>
    new File(['x'], `ex${i}.pdf`, { type: 'application/pdf' }),
  );
  fireEvent.change(fileInput, { target: { files: existing } });
  await screen.findByText('ex0.pdf');

  // Then drop 4 more → total 7, truncated to 5, error shown
  const dropped = Array.from({ length: 4 }, (_, i) =>
    new File(['x'], `dr${i}.pdf`, { type: 'application/pdf' }),
  );
  fireDrop(getChatWindow(), dropped);
  await screen.findByRole('alert');
  // 5 remove buttons = 5 files total
  expect(screen.getAllByRole('button', { name: /Убрать/ })).toHaveLength(5);
});

test('drop of empty file shows error', async () => {
  renderWindow();
  const emptyFile = new File([], 'empty.pdf', { type: 'application/pdf' });
  fireDrop(getChatWindow(), [emptyFile]);
  await screen.findByRole('alert');
  expect(screen.getByText(/Пустой файл/)).toBeInTheDocument();
});
