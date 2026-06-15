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
