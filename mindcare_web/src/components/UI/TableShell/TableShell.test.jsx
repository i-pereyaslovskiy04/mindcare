import { render, screen, within } from '@testing-library/react';
import TableShell from './TableShell';

function renderShell(props = {}) {
  return render(
    <TableShell caption="Пользователи" {...props}>
      <thead><tr><th scope="col">Имя</th></tr></thead>
      <tbody><tr><td>Ли Ан</td></tr></tbody>
    </TableShell>,
  );
}

test('семантическая таблица с доступным именем из caption', () => {
  renderShell();
  const table = screen.getByRole('table', { name: 'Пользователи' });
  expect(within(table).getByRole('columnheader', { name: 'Имя' })).toBeInTheDocument();
  expect(within(table).getByRole('cell', { name: 'Ли Ан' })).toBeInTheDocument();
});

test('caption по умолчанию скрыт визуально, captionVisible показывает его', () => {
  const { unmount } = renderShell();
  expect(screen.getByText('Пользователи')).toHaveClass('visually-hidden');
  unmount();
  renderShell({ captionVisible: true });
  expect(screen.getByText('Пользователи')).not.toHaveClass('visually-hidden');
});

test('tableClassName и aria-* уходят на <table>, className — на контейнер', () => {
  renderShell({ className: 'outer', tableClassName: 'inner', 'aria-describedby': 'hint' });
  const table = screen.getByRole('table');
  expect(table).toHaveClass('inner');
  expect(table).toHaveAttribute('aria-describedby', 'hint');
  // eslint-disable-next-line testing-library/no-node-access
  expect(table.parentElement).toHaveClass('outer');
});

test('без caption подписи нет', () => {
  render(<TableShell><tbody><tr><td>x</td></tr></tbody></TableShell>);
  expect(screen.getByRole('table')).not.toHaveAccessibleName();
});
