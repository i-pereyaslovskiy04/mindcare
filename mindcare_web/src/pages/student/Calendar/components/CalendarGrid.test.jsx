import { useRef, useState } from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import CalendarGrid from './CalendarGrid';

// Октябрь 2026; «сегодня» — 14-е, на него же сессия; на 20-е — прошедшая.
// Хвост сентября (28–30) и начало ноября (1) — дни соседних месяцев; на
// 1 ноября есть событие, чтобы проверить, что соседний месяц не активен.
const EVENTS = {
  '2026-10-14': [{ type: 'session', title: 'Консультация', time: '12:00–12:50' }],
  '2026-10-20': [{ type: 'past', title: 'Прошлая встреча', time: '10:00–10:50' }],
  '2026-11-01': [{ type: 'session', title: 'Ноябрьская', time: '09:00–09:50' }],
};
const SESSIONS = {
  '2026-10-14': { status: 'upcoming' },
  '2026-10-20': { status: 'past' },
  '2026-11-01': { status: 'upcoming' },
};

// Повторяет модель CalendarPage: выбранный день и открытое окно — наверху.
function Harness({ todayKey = '2026-10-14', onDayClick }) {
  const [selected, setSelected] = useState(null);
  const [open, setOpen] = useState(null);
  const ref = useRef(null);
  return (
    <div ref={ref}>
      <CalendarGrid
        year={2026}
        month={9}
        sessionMap={SESSIONS}
        todayKey={todayKey}
        selectedKey={selected}
        openKey={open}
        onDayClick={(key, pos) => {
          onDayClick?.(key, pos);
          setSelected(key);
          setOpen((cur) => (cur === key ? null : key));
        }}
        onDismiss={() => setOpen(null)}
        containerRef={ref}
        eventsMap={EVENTS}
        popupId="day-popup"
      />
    </div>
  );
}

const day = (name) => screen.getByRole('button', { name: new RegExp(`^${name}`) });

test('каждый день отображаемого месяца — кнопка с понятным именем', () => {
  render(<Harness />);
  const buttons = screen.getAllByRole('button');
  expect(buttons).toHaveLength(31);
  buttons.forEach((b) => {
    expect(b.tagName).toBe('BUTTON');
    expect(b).toHaveAttribute('type', 'button');
  });
  expect(day('14 октября')).toHaveAccessibleName('14 октября, среда, есть события');
  expect(day('16 октября')).toHaveAccessibleName('16 октября, пятница');
});

test('дни соседнего месяца — не кнопки, даже с событиями', () => {
  const onDayClick = jest.fn();
  render(<Harness onDayClick={onDayClick} />);
  expect(screen.queryByRole('button', { name: /сентября|ноября/ })).toBeNull();
  // «1» встречается дважды: 1 октября (кнопка) и 1 ноября (текст).
  const novFirst = screen.getAllByText('1')
    .find((el) => !el.closest('button')); // eslint-disable-line testing-library/no-node-access
  fireEvent.click(novFirst);
  expect(onDayClick).not.toHaveBeenCalled();
});

test('пустой день: нажатие выбирает его и открывает окно', () => {
  const onDayClick = jest.fn();
  render(<Harness onDayClick={onDayClick} />);
  const empty = day('16 октября');
  expect(empty).toHaveAttribute('aria-expanded', 'false');
  expect(empty).not.toHaveAttribute('aria-controls');

  fireEvent.click(empty);
  expect(onDayClick).toHaveBeenLastCalledWith('2026-10-16', expect.anything());
  expect(empty).toHaveAttribute('aria-expanded', 'true');
  expect(empty).toHaveAttribute('aria-controls', 'day-popup');
  expect(empty).toHaveClass('active');
  expect(empty).toHaveAccessibleName('16 октября, пятница, выбрано');
});

test('нажатие другого дня переносит выбор; повторное — закрывает окно', () => {
  render(<Harness />);
  fireEvent.click(day('16 октября'));
  fireEvent.click(day('20 октября'));
  expect(day('16 октября')).not.toHaveClass('active');
  expect(day('16 октября')).toHaveAttribute('aria-expanded', 'false');
  expect(day('20 октября')).toHaveClass('active');
  expect(day('20 октября')).toHaveAttribute('aria-expanded', 'true');

  fireEvent.click(day('20 октября'));
  expect(day('20 октября')).toHaveAttribute('aria-expanded', 'false');
});

test('сегодня + сессия + выбран: состояния сохраняются вместе, aria-current="date"', () => {
  render(<Harness />);
  const today = day('14 октября');
  expect(today).toHaveAttribute('aria-current', 'date');
  expect(today).toHaveClass('today');
  expect(today).toHaveClass('sessionDay');

  fireEvent.click(today);
  expect(today).toHaveClass('today');
  expect(today).toHaveClass('sessionDay');
  expect(today).toHaveClass('active');
  expect(today).toHaveAttribute('aria-current', 'date');
});

test('пустой «сегодня» — тоже кнопка с aria-current="date"', () => {
  render(<Harness todayKey="2026-10-16" />);
  expect(day('16 октября')).toHaveAttribute('aria-current', 'date');
  expect(day('16 октября')).toHaveClass('today');
});
