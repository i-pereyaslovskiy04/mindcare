import { render, screen } from '@testing-library/react';
import DiaryHistoryList from './DiaryHistoryList';

const CATALOG = [{ key: 'calm', label: 'Спокойно', sort_order: 1 }];

const ENTRIES = [
  {
    uuid: 'entry-1',
    entry_date: '2026-06-23',
    mood_score: 7,
    entry_text: 'Хорошее настроение',
    emotions: ['calm'],
    created_at: '2026-06-23T10:00:00',
    updated_at: '2026-06-23T10:00:00',
  },
  {
    uuid: 'entry-2',
    entry_date: '2026-06-22',
    mood_score: 5,
    entry_text: '',
    emotions: [],
    created_at: '2026-06-22T10:00:00',
    updated_at: '2026-06-22T10:00:00',
  },
];

// ─── empty state ─────────────────────────────────────────────────────────────

test('shows "Здесь появятся ваши записи." when entries list is empty', () => {
  render(<DiaryHistoryList entries={[]} emotionCatalog={CATALOG} />);
  expect(screen.getByText('Здесь появятся ваши записи.')).toBeInTheDocument();
});

test('does not show old "Сделайте первую запись!" text', () => {
  render(<DiaryHistoryList entries={[]} emotionCatalog={CATALOG} />);
  expect(screen.queryByText(/сделайте первую запись/i)).not.toBeInTheDocument();
});

test('does not show empty state when entries exist', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.queryByText(/здесь появятся/i)).not.toBeInTheDocument();
});

// ─── populated state ──────────────────────────────────────────────────────────

test('shows section title "История записей"', () => {
  render(<DiaryHistoryList entries={[]} emotionCatalog={CATALOG} />);
  expect(screen.getByText('История записей')).toBeInTheDocument();
});

test('renders all provided entries', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  // DiaryEntryItem renders mood score as "7/10" and "5/10"
  expect(screen.getByText(/7\/10/)).toBeInTheDocument();
  expect(screen.getByText(/5\/10/)).toBeInTheDocument();
});

test('renders entry text when provided', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.getByText('Хорошее настроение')).toBeInTheDocument();
});

test('renders emotion label via catalog', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.getByText('Спокойно')).toBeInTheDocument();
});
