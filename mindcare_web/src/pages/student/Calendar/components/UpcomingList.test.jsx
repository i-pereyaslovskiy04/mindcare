import { render, screen, fireEvent, within } from '@testing-library/react';
import UpcomingList from './UpcomingList';

const base = {
  date: '2026-10-15',
  time: '09:00–09:50',
  title: 'Консультация',
  psychologist: 'Николай Константинович',
  type: 'video',
  status: 'upcoming',
};
const confirmed = {
  ...base, id: 'a', uuid: 'a', rawStatus: 'confirmed',
  statusLabel: 'Подтверждена', statusTone: 'success', canCancel: true,
};
const pending = {
  ...base, id: 'b', uuid: 'b', date: '2026-10-30', time: '16:00–16:50',
  rawStatus: 'pending_confirmation',
  statusLabel: 'Ожидает подтверждения', statusTone: 'warning', canCancel: true,
};

test('карточка: информация, статус-текст (не кнопка) и действия по состоянию', () => {
  const onCancel = jest.fn();
  render(<UpcomingList sessions={[confirmed, pending]} onCancel={onCancel} />);
  const [first, second] = screen.getAllByRole('listitem');

  expect(within(first).getByText('15 октября · 09:00–09:50 · Николай Константинович'))
    .toBeInTheDocument();
  // Статус — состояние, а не элемент управления.
  expect(within(first).getByText('Подтверждена')).toBeInTheDocument();
  expect(within(first).queryByRole('button', { name: 'Подтверждена' })).toBeNull();
  expect(within(first).getAllByRole('button').map((b) => b.textContent))
    .toEqual(['Подключиться', 'Отменить']);

  expect(within(second).getByText('Ожидает подтверждения')).toBeInTheDocument();
  expect(within(second).getAllByRole('button').map((b) => b.textContent))
    .toEqual(['Отменить']);

  fireEvent.click(within(second).getByRole('button', { name: 'Отменить' }));
  expect(onCancel).toHaveBeenCalledWith('b');
});

test('без доступных действий в карточке нет кнопок, статус остаётся', () => {
  render(<UpcomingList sessions={[{ ...pending, canCancel: false }]} onCancel={jest.fn()} />);
  expect(screen.getByText('Ожидает подтверждения')).toBeInTheDocument();
  expect(screen.queryAllByRole('button')).toHaveLength(0);
});
