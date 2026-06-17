import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MessageInput from './MessageInput';

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

// D. В режиме редактирования input заполнен текстом + видна панель.
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

// E. Кнопка «Отменить» вызывает onCancelEdit.
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

// F. Escape в режиме редактирования вызывает onCancelEdit.
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

// G. Submit в режиме редактирования вызывает onSubmitEdit, а не onSend.
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

// Обычная отправка не сломана: submit без editing вызывает onSend.
test('normal send calls onSend when not editing', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  fireEvent.change(screen.getByRole('textbox'), { target: { value: 'привет' } });
  fireEvent.click(screen.getByRole('button', { name: 'Отправить' }));
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('привет'));
});

test('Enter without Shift sends the message', async () => {
  const restoreTouch = mockTouchComposer(false);
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: 'привет' } });
  fireEvent.keyDown(textarea, { key: 'Enter', shiftKey: false });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('привет'));
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
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('строка 1\nстрока 2'));
  restoreTouch();
});

test('message with internal newlines is sent with newlines preserved', async () => {
  const onSend = jest.fn().mockResolvedValue(true);
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');
  fireEvent.change(textarea, { target: { value: '  строка 1\nстрока 2  ' } });
  fireEvent.keyDown(textarea, { key: 'Enter' });
  await waitFor(() => expect(onSend).toHaveBeenCalledWith('строка 1\nстрока 2'));
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
  render(<MessageInput onSend={onSend} />);
  const textarea = screen.getByRole('textbox');

  setScrollHeight(textarea, 120);
  fireEvent.change(textarea, { target: { value: '1\n2\n3\n4' } });
  expect(textarea.style.overflowY).toBe('auto');

  setScrollHeight(textarea, 42);
  fireEvent.keyDown(textarea, { key: 'Enter' });

  await waitFor(() => expect(onSend).toHaveBeenCalledWith('1\n2\n3\n4'));
  await waitFor(() => expect(textarea).toHaveValue(''));
  expect(textarea.style.height).toBe('42px');
  expect(textarea.style.overflowY).toBe('hidden');

  styleSpy.mockRestore();
});

// H. Send button остаётся доступным (accessible name) и содержит иконку
// самолётика, даже когда текстовый label скрыт CSS-медиа-запросом на mobile
// (Stage 31z-hotfix2: icon-only compact button на узком экране).
test('H. send button keeps accessible name and icon when text label is hidden on mobile', () => {
  render(<MessageInput onSend={jest.fn()} />);
  const button = screen.getByRole('button', { name: 'Отправить' });
  expect(button).toHaveAttribute('aria-label', 'Отправить');
  // Icon — декоративный svg без role/text, доступа через Testing Library queries нет.
  // eslint-disable-next-line testing-library/no-node-access
  expect(button.querySelector('svg')).toBeInTheDocument();
  expect(button).toHaveTextContent('Отправить');
});

// I. Disabled state не сломан icon-only вёрсткой: пустой текст → кнопка disabled.
test('I. send button is disabled when input is empty', () => {
  render(<MessageInput onSend={jest.fn()} />);
  expect(screen.getByRole('button', { name: 'Отправить' })).toBeDisabled();
});

// J. В edit mode тот же icon-only паттерн: accessible name и иконка edit сохраняются.
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
