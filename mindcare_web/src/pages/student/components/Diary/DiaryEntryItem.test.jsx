import { render, screen } from '@testing-library/react';
import DiaryEntryItem from './DiaryEntryItem';

const entry = (date, mood, text = '', emotions = []) => ({
  uuid: 'test-uuid',
  entry_date: date,
  mood_score: mood,
  entry_text: text,
  emotions,
});

test('formats date using local timezone — day number matches ISO date', () => {
  render(<DiaryEntryItem entry={entry('2026-06-19', 7)} emotionCatalog={[]} />);
  // "19" must appear in date string regardless of browser timezone
  expect(screen.getByText(/19/)).toBeInTheDocument();
});

test('renders mood score and word from MOOD_WORDS', () => {
  render(<DiaryEntryItem entry={entry('2026-06-19', 8)} emotionCatalog={[]} />);
  expect(screen.getByText(/8\/10/)).toBeInTheDocument();
  expect(screen.getByText(/Светло/)).toBeInTheDocument();
});

test('maps emotion key to label via catalog', () => {
  const catalog = [{ key: 'calm', label: 'Спокойно', sort_order: 1 }];
  render(<DiaryEntryItem entry={entry('2026-06-19', 6, '', ['calm'])} emotionCatalog={catalog} />);
  expect(screen.getByText('Спокойно')).toBeInTheDocument();
});

test('shows raw key when emotion is not in catalog', () => {
  render(<DiaryEntryItem entry={entry('2026-06-19', 5, '', ['unknown_key'])} emotionCatalog={[]} />);
  expect(screen.getByText('unknown_key')).toBeInTheDocument();
});

test('renders entry text', () => {
  render(<DiaryEntryItem entry={entry('2026-06-19', 6, 'Сегодня был хороший день')} emotionCatalog={[]} />);
  expect(screen.getByText('Сегодня был хороший день')).toBeInTheDocument();
});
