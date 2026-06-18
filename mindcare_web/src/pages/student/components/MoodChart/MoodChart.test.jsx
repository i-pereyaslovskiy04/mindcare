import { render, screen } from '@testing-library/react';
import MoodChart from './MoodChart';

test('shows empty state text when data is empty array', () => {
  render(<MoodChart data={[]} />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('shows empty state when all mood_score values are null', () => {
  render(<MoodChart data={[{ l: 'Пн', v: null }, { l: 'Вт', v: null }, { l: 'Ср', v: null }]} />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('does not show empty state when at least one value is non-null', () => {
  render(<MoodChart data={[{ l: 'Пн', v: 5 }, { l: 'Вт', v: null }, { l: 'Ср', v: 7 }]} />);
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('does not show empty state when data has two non-null values', () => {
  render(<MoodChart data={[{ l: 'Пн', v: 5 }, { l: 'Вт', v: 7 }]} />);
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('does not crash with a single non-null data point', () => {
  expect(() => render(<MoodChart data={[{ l: 'Пн', v: 5 }]} />)).not.toThrow();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('shows empty state for single null data point', () => {
  expect(() => render(<MoodChart data={[{ l: 'Пн', v: null }]} />)).not.toThrow();
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('null in the middle does not crash — shows chart without empty state', () => {
  expect(() =>
    render(<MoodChart data={[{ l: 'Пн', v: 7 }, { l: 'Вт', v: null }, { l: 'Ср', v: 5 }]} />)
  ).not.toThrow();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});
