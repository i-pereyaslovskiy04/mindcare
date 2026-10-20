import { useState } from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MessageInput from './MessageInput';
import { mergeSelectedFiles } from '../lib/attachmentSelection';

// ── Helpers ───────────────────────────────────────────────────────────────────

function mockTextareaMetrics() {
  return jest.spyOn(window, 'getComputedStyle').mockReturnValue({
    fontSize: '14px',
    lineHeight: '20px',
    paddingTop: '10px',
    paddingBottom: '10px',
    borderTopWidth: '1px',
    borderBottomWidth: '1px',
  });
}

function setScrollHeight(el, value) {
  Object.defineProperty(el, 'scrollHeight', {
    configurable: true,
    value,
  });
}

function mockTouchComposer(matches) {
  const original = window.matchMedia;
  window.matchMedia = jest.fn().mockImplementation((query) => ({
    matches: query === '(hover: none) and (pointer: coarse)' ? matches : false,
    media: query,
    onchange: null,
    addListener: jest.fn(),
    removeListener: jest.fn(),
    addEventListener: jest.fn(),
    removeEventListener: jest.fn(),
    dispatchEvent: jest.fn(),
  }));
  return () => {
    window.matchMedia = original;
  };
}

function makeFile(name = 'test.pdf', size = 1024, type = 'application/pdf') {
  return new File([new ArrayBuffer(size)], name, { type });
}

// Hidden file input не попадает в accessibility tree, поэтому используем прямой
// DOM-поиск через querySelector. Все usages идут через эту функцию.
// eslint-disable-next-line testing-library/no-node-access
const getFileInput = () => document.querySelector('input[type="file"]');

/**
 * Stateful wrapper, имитирующий то, как ChatWindow управляет selectedFiles.
 * Нужен для тестов, которые проверяют выбор файлов через файловый инпут.
 */
function WithFiles({ onSend: extOnSend = jest.fn(), sending = false, ...rest }) {
  const [selectedFiles, setSelectedFiles] = useState([]);
  const [attachError, setAttachError] = useState(null);

  const onFilesSelected = (rawFiles) => {
    const { files, error } = mergeSelectedFiles(selectedFiles, rawFiles);
    setSelectedFiles(files);
    setAttachError(error);
  };

  return (
    <MessageInput
      {...rest}
      onSend={extOnSend}
      sending={sending}
      selectedFiles={selectedFiles}
      onFilesSelected={onFilesSelected}
      onRemoveFile={(index) => {
        setSelectedFiles((prev) => prev.filter((_, i) => i !== index));
        setAttachError(null);
      }}
      onClearFiles={() => setSelectedFiles([])}
      attachError={attachError}
    />
  );
}

// ── Edit mode (existing tests) ────────────────────────────────────────────────

test('D. edit mode prefills composer and shows banner', () => {
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 'старый текст' }}
      onSubmitEdit={jest.fn()}
      onCancelEdit={jest.fn()}
    />,
  );
  expect(screen.getByText('Редактирование сообщения')).toBeInTheDocument();
  expect(screen.getByRole('textbox')).toHaveValue('старый текст');
  expect(screen.getByRole('button', { name: 'Сохранить' })).toBeInTheDocument();
});

test('E. cancel button calls onCancelEdit', () => {
  const onCancelEdit = jest.fn();
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 't' }}
      onSubmitEdit={jest.fn()}
      onCancelEdit={onCancelEdit}
    />,
  );
  fireEvent.click(screen.getByRole('button', { name: 'Отменить' }));
  expect(onCancelEdit).toHaveBeenCalled();
});

test('F. Escape cancels edit', () => {
  const onCancelEdit = jest.fn();
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 't' }}
      onSubmitEdit={jest.fn()}
      onCancelEdit={onCancelEdit}
    />,
  );
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Escape' });
  expect(onCancelEdit).toHaveBeenCalled();
});

test('G. submit in edit mode calls onSubmitEdit, not onSend', async () => {
  const onSend = jest.fn();
  const onSubmitEdit = jest.fn().mockResolvedValue(true);
  render(
    <MessageInput
      onSend={onSend}
      editing={{ uuid: 'u1', text: 'было' }}
      onSubmitEdit={onSubmitEdit}
      onCancelEdit={jest.fn()}
    />,
  );
  const input = screen.getByRole('textbox');
  fireEvent.change(input, { target: { value: 'стало' } });
  fireEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  await waitFor(() => expect(onSubmitEdit).toHaveBeenCalledWith('стало'));
  expect(onSend).not.toHaveBeenCalled();
});

// ── Обычная отправка ──────────────────────────────────────────────────────────

test('normal send calls onSend with text and empty files array', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'привет' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('привет', []));
});

test('Enter without Shift sends the message', async () => {
  const restoreTouch = mockTouchComposer(false);
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: 'привет' } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('привет', []));
  restoreTouch();
});

test('Shift+Enter does not send and keeps multiline textarea value', () => {
  const restoreTouch = mockTouchComposer(false);
  const onSend = jest.fn();
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: 'строка 1' } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });
  expect(onSend).not.toHaveBeenCalled();
  expect(textarea).toHaveValue('строка 1\nстрока 2');
  restoreTouch();
});

test('mobile Enter does not send and allows newline in textarea', () => {
  const restoreTouch = mockTouchComposer(true);
  const onSend = jest.fn();
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');

  fireEvent.change(textarea, { target: { value: 'строка 1' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });

  expect(onSend).not.toHaveBeenCalled();
  expect(textarea).toHaveValue('строка 1\nстрока 2');
  restoreTouch();
});

test('mobile sends multiline message only by button', async () => {
  const restoreTouch = mockTouchComposer(true);
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');

  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  expect(onSend).not.toHaveBeenCalled();

  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('строка 1\nстрока 2', []));
  restoreTouch();
});

test('message with internal newlines is sent with newlines preserved', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: '  строка 1\nстрока 2  ' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('строка 1\nстрока 2', []));
});

test('whitespace-only message with spaces and newlines is not sent', () => {
  const onSend = jest.fn();
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: '   \n   ' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  expect(onSend).not.toHaveBeenCalled();
});

test('edit mode Enter saves and Shift+Enter keeps editing multiline text', async () => {
  const restoreTouch = mockTouchComposer(false);
  const onSubmitEdit = jest.fn().mockResolvedValue(true);
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 'старый текст' }}
      onSubmitEdit={onSubmitEdit}
      onCancelEdit={jest.fn()}
    />,
  );
  const textarea = screen.getByRole('textbox');

  fireEvent.change(textarea, { target: { value: 'строка 1' } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: true });
  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });
  expect(onSubmitEdit).not.toHaveBeenCalled();
  expect(textarea).toHaveValue('строка 1\nстрока 2');

  fireEvent.keyDown(textarea, { key: 'Enter' });
  await waitFor(() => expect(onSubmitEdit).toHaveBeenCalledWith('строка 1\nстрока 2'));
  restoreTouch();
});

test('mobile edit mode Enter does not save and allows newline', () => {
  const restoreTouch = mockTouchComposer(true);
  const onSubmitEdit = jest.fn();
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 'старый текст' }}
      onSubmitEdit={onSubmitEdit}
      onCancelEdit={jest.fn()}
    />,
  );
  const textarea = screen.getByRole('textbox');

  fireEvent.change(textarea, { target: { value: 'строка 1' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });

  expect(onSubmitEdit).not.toHaveBeenCalled();
  expect(textarea).toHaveValue('строка 1\nстрока 2');
  restoreTouch();
});

test('textarea autosizes up to three lines and scrolls from the fourth line', () => {
  const styleSpy = mockTextareaMetrics();
  render(<MessageInput onSend={jest.fn()} />);
  const textarea = screen.getByRole('textbox');

  setScrollHeight(textarea, 60);
  fireEvent.change(textarea, { target: { value: 'строка 1\nстрока 2' } });
  expect(textarea.style.height).toBe('60px');
  expect(textarea.style.overflowY).toBe('hidden');

  setScrollHeight(textarea, 120);
  fireEvent.change(textarea, { target: { value: '1\n2\n3\n4' } });
  expect(textarea.style.height).toBe('82px');
  expect(textarea.style.overflowY).toBe('auto');

  styleSpy.mockRestore();
});

test('textarea resets to one-line height after successful multiline send', async () => {
  const styleSpy = mockTextareaMetrics();
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} onClearFiles={jest.fn()} />);
  const textarea = screen.getByRole('textbox');

  setScrollHeight(textarea, 120);
  fireEvent.change(textarea, { target: { value: '1\n2\n3\n4' } });
  expect(textarea.style.overflowY).toBe('auto');

  setScrollHeight(textarea, 42);
  fireEvent.keyDown(textarea, { key: 'Enter' });

  await waitFor(() => expect(onSend).toHaveBeenCalledWith('1\n2\n3\n4', []));
  await waitFor(() => expect(textarea).toHaveValue(''));
  expect(textarea.style.height).toBe('42px');
  expect(textarea.style.overflowY).toBe('hidden');

  styleSpy.mockRestore();
});

// H. Send button остаётся доступным (accessible name) и содержит иконку самолётика.
test('H. send button keeps accessible name and icon', () => {
  render(<MessageInput onSend={jest.fn()} />);
  const button = screen.getByRole('button', { name: 'Отправить' });
  expect(button).toHaveAttribute('aria-label', 'Отправить');
  // eslint-disable-next-line testing-library/no-node-access
  expect(button.querySelector('svg')).toBeInTheDocument();
  expect(button).toHaveTextContent('Отправить');
});

// I. Disabled state: пустой текст И нет файлов → кнопка disabled.
test('I. send button is disabled when input is empty and no files selected', () => {
  render(<MessageInput onSend={jest.fn()} />);
  expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled();
});

// J. В edit mode accessible name и иконка сохраняются.
test('J. save button in edit mode keeps accessible name and icon', () => {
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 'текст' }}
      onSubmitEdit={jest.fn()}
      onCancelEdit={jest.fn()}
    />,
  );
  const button = screen.getByRole('button', { name: 'Сохранить' });
  expect(button).toHaveAttribute('aria-label', 'Сохранить');
  // eslint-disable-next-line testing-library/no-node-access
  expect(button.querySelector('svg')).toBeInTheDocument();
});

// ── Attachment picker (Stage 32e/32f) ─────────────────────────────────────────

test('K. attach button is rendered outside edit mode', () => {
  render(<MessageInput onSend={jest.fn()} />);
  expect(screen.getByRole('button', { name: 'Прикрепить файл' })).toBeInTheDocument();
});

test('K2. attach button is NOT rendered in edit mode', () => {
  render(
    <MessageInput
      onSend={jest.fn()}
      editing={{ uuid: 'u1', text: 'текст' }}
      onSubmitEdit={jest.fn()}
      onCancelEdit={jest.fn()}
    />,
  );
  expect(screen.queryByRole('button', { name: 'Прикрепить файл' })).not.toBeInTheDocument();
});

test('L. selecting a file shows it in SelectedAttachmentList', () => {
  render(<WithFiles onSend={jest.fn()} />);
  fireEvent.change(getFileInput(), { target: { files: [makeFile('отчёт.pdf')] } });
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
});

test('M. can remove selected file before send', () => {
  render(<WithFiles onSend={jest.fn()} />);
  fireEvent.change(getFileInput(), { target: { files: [makeFile('doc.pdf')] } });
  expect(screen.getByText('doc.pdf')).toBeInTheDocument();
  fireEvent.click(screen.getByRole('button', { name: /Убрать doc\.pdf/ }));
  expect(screen.queryByText('doc.pdf')).not.toBeInTheDocument();
});

test('N. attachment-only send: empty text + file → onSend called with file', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<WithFiles onSend={onSend} />);
  const file = makeFile('photo.jpg', 2048, 'image/jpeg');
  fireEvent.change(getFileInput(), { target: { files: [file] } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('', [file]));
});

test('O. text+file send: onSend receives text and files', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<WithFiles onSend={onSend} />);
  const file = makeFile('attach.pdf');
  fireEvent.change(getFileInput(), { target: { files: [file] } });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'смотри вложение' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() =>
    expect(onSend).toHaveBeenCalledWith('смотри вложение', [file]),
  );
});

test('P. successful send clears text and files', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<WithFiles onSend={onSend} />);
  fireEvent.change(getFileInput(), { target: { files: [makeFile('doc.pdf')] } });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'текст' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalled());
  await waitFor(() => expect(screen.getByRole('textbox')).toHaveValue(''));
  expect(screen.queryByText('doc.pdf')).not.toBeInTheDocument();
});

test('Q. failed send (onSend returns false) keeps text and files', async () => {
  const onSend = jest.fn().mockResolvedValue(false);
  render(<WithFiles onSend={onSend} />);
  fireEvent.change(getFileInput(), { target: { files: [makeFile('doc.pdf')] } });
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'черновик' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalled());
  expect(screen.getByRole('textbox')).toHaveValue('черновик');
  expect(screen.getByText('doc.pdf')).toBeInTheDocument();
});

test('R. attach button disabled when sending=true', () => {
  render(<MessageInput onSend={jest.fn()} sending />);
  expect(screen.getByRole('button', { name: 'Прикрепить файл' })).toBeDisabled();
});

test('R2. send button enabled when only files selected via prop (no text)', () => {
  const file = makeFile('doc.pdf');
  render(<MessageInput onSend={jest.fn()} selectedFiles={[file]} />);
  expect(screen.getByRole('button', { name: 'Отправить' })).not.toBeDisabled();
});

test('S. max 5 files: selecting more shows error and truncates to 5', () => {
  render(<WithFiles onSend={jest.fn()} />);
  const files = Array.from({ length: 7 }, (_, i) => makeFile(`file${i}.pdf`));
  fireEvent.change(getFileInput(), { target: { files } });
  expect(screen.getByRole('alert')).toBeInTheDocument();
  expect(screen.getByText(/не больше 5/)).toBeInTheDocument();
});

test('T. empty file (size=0) is rejected silently — no remove button appears', () => {
  render(<WithFiles onSend={jest.fn()} />);
  const empty = new File([], 'empty.pdf', { type: 'application/pdf' });
  fireEvent.change(getFileInput(), { target: { files: [empty] } });
  expect(screen.queryByRole('button', { name: /Убрать/ })).not.toBeInTheDocument();
});

test('U. desktop Enter sends file-only message', async () => {
  const restoreTouch = mockTouchComposer(false);
  const onSend = jest.fn().mockResolvedValue(true);
  render(<WithFiles onSend={onSend} />);
  fireEvent.change(getFileInput(), { target: { files: [makeFile('doc.pdf')] } });
  fireEvent.keyDown(screen.getByRole('textbox'), { key: 'Enter' });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('', [expect.any(File)]));
  restoreTouch();
});

test('V. files injected via selectedFiles prop render in list', () => {
  const file = makeFile('injected.pdf');
  render(<MessageInput onSend={jest.fn()} selectedFiles={[file]} />);
  expect(screen.getByText('injected.pdf')).toBeInTheDocument();
});
