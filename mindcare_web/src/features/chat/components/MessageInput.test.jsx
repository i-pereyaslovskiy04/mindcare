import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import MessageInput from './MessageInput';

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
