import { render, screen, fireEvent, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import SessionHistory from './SessionHistory';

const row = (id, rawStatus, extra = {}) => ({
  id,
  date: '2026-10-15',
  time: '09:00–09:50',
  title: 'Консультация',
  psychologist: 'Николай Константинович',
  status: 'past',
  rawStatus,
  desc: '',
  ...extra,
});

const SESSIONS = [
  row('done', 'completed', { date: '2026-10-15' }),
  row('cancel', 'cancelled', { date: '2026-10-10' }),
  row('decl', 'declined', { date: '2026-10-08' }),
  row('noshow', 'no_show', { date: '2026-10-05' }),
  row('past-confirmed', 'confirmed', { date: '2026-10-01' }),
];

const toggle = () => screen.getByRole('button', { name: /^История сессий/ });

test('по умолчанию свёрнута, количество видно в заголовке', () => {
  render(<SessionHistory sessions={SESSIONS} />);
  expect(toggle()).toHaveAccessibleName('История сессий · 5');
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('list')).toBeNull();
  // aria-controls указывает на (скрытый) список.
  // eslint-disable-next-line testing-library/no-node-access
  const list = document.getElementById(toggle().getAttribute('aria-controls'));
  expect(list).not.toBeNull();
  expect(list).not.toBeVisible();
});

test('клик раскрывает, повторный — сворачивает', () => {
  render(<SessionHistory sessions={SESSIONS} />);
  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute('aria-expanded', 'true');
  expect(screen.getAllByRole('listitem')).toHaveLength(5);

  fireEvent.click(toggle());
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
  expect(screen.queryByRole('list')).toBeNull();
});

test('Enter и Space на заголовке работают (нативная <button>)', () => {
  render(<SessionHistory sessions={SESSIONS} />);
  expect(toggle().tagName).toBe('BUTTON');
  expect(toggle()).toHaveAttribute('type', 'button');
  toggle().focus();
  userEvent.keyboard('{Enter}');
  expect(toggle()).toHaveAttribute('aria-expanded', 'true');
  userEvent.keyboard(' ');
  expect(toggle()).toHaveAttribute('aria-expanded', 'false');
});

test('итог встречи: completed/cancelled/declined/no_show; past confirmed — без итога', () => {
  render(<SessionHistory sessions={SESSIONS} />);
  fireEvent.click(toggle());
  const items = screen.getAllByRole('listitem');
  const [done, cancel, decl, noshow, pastConfirmed] = items;

  expect(within(done).getByText('Состоялась')).toBeInTheDocument();
  expect(within(cancel).getByText('Отменена')).toBeInTheDocument();
  expect(within(decl).getByText('Отклонена')).toBeInTheDocument();
  expect(within(noshow).getByText('Неявка')).toBeInTheDocument();

  // Прошедшая confirmed: результат неизвестен — ни «Состоялась», ни «Подтверждена».
  expect(within(pastConfirmed).getByText('Консультация')).toBeInTheDocument();
  expect(within(pastConfirmed).queryByText('Состоялась')).toBeNull();
  expect(screen.queryByText('Подтверждена')).toBeNull();
  expect(screen.getAllByText('Состоялась')).toHaveLength(1);
});

test('отменённые и несостоявшиеся записи остаются в истории, без действий', () => {
  render(<SessionHistory sessions={SESSIONS} />);
  fireEvent.click(toggle());
  const items = screen.getAllByRole('listitem');
  expect(items).toHaveLength(5);
  expect(within(items[1]).getByText('10 октября')).toBeInTheDocument();
  // В списке нет кнопок — только заголовок-переключатель.
  expect(screen.getAllByRole('button')).toHaveLength(1);
});

test('пустая история не рендерится', () => {
  render(<SessionHistory sessions={[]} />);
  expect(screen.queryByRole('button')).toBeNull();
  expect(screen.queryByText(/История сессий/)).toBeNull();
});
