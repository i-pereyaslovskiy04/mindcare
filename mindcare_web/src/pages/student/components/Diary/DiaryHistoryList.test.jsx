import { render, screen, fireEvent } from '@testing-library/react';
import * as diaryApi from '../../../../api/diary.api';
import DiaryHistoryList from './DiaryHistoryList';

jest.mock('../../../../api/diary.api');

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.updateDiaryEntry.mockResolvedValue({});
  diaryApi.deleteDiaryEntry.mockResolvedValue(undefined);
});

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

// ─── onEntryUpdate / onEntryDelete prop pass-through ─────────────────────────

test('entry items show kebab buttons when onEntryUpdate and onEntryDelete provided', () => {
  render(
    <DiaryHistoryList
      entries={ENTRIES}
      emotionCatalog={CATALOG}
      onEntryUpdate={jest.fn()}
      onEntryDelete={jest.fn()}
    />
  );
  expect(screen.getAllByRole('button', { name: /действия с записью/i }).length).toBeGreaterThan(0);
});

test('no action buttons on items when onEntryUpdate and onEntryDelete not provided', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.queryByRole('button', { name: /действия с записью/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /редактировать запись/i })).not.toBeInTheDocument();
  expect(screen.queryByRole('button', { name: /удалить запись/i })).not.toBeInTheDocument();
});

// ─── load more ────────────────────────────────────────────────────────────────

test('does not show "Загрузить ещё" button when hasMore=false (default)', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.queryByRole('button', { name: /загрузить ещё/i })).not.toBeInTheDocument();
});

test('shows "Загрузить ещё" button when hasMore=true', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} hasMore onLoadMore={jest.fn()} />);
  expect(screen.getByRole('button', { name: /загрузить ещё/i })).toBeInTheDocument();
});

test('"Загрузить ещё" button calls onLoadMore on click', () => {
  const mockLoadMore = jest.fn();
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} hasMore onLoadMore={mockLoadMore} />);
  fireEvent.click(screen.getByRole('button', { name: /загрузить ещё/i }));
  expect(mockLoadMore).toHaveBeenCalledTimes(1);
});

test('button shows "Загружаем…" and is disabled when loadingMore=true', () => {
  render(
    <DiaryHistoryList
      entries={ENTRIES}
      emotionCatalog={CATALOG}
      hasMore
      loadingMore
      onLoadMore={jest.fn()}
    />
  );
  const btn = screen.getByRole('button', { name: /загружаем/i });
  expect(btn).toBeInTheDocument();
  expect(btn).toBeDisabled();
});

test('shows load more error message when loadMoreError is set', () => {
  render(
    <DiaryHistoryList
      entries={ENTRIES}
      emotionCatalog={CATALOG}
      loadMoreError="Не удалось загрузить записи. Попробуйте ещё раз."
    />
  );
  expect(screen.getByText(/не удалось загрузить записи/i)).toBeInTheDocument();
});

test('error message is not shown when loadMoreError is null', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.queryByText(/не удалось загрузить записи/i)).not.toBeInTheDocument();
});

// ─── footerLink / hideTitle ───────────────────────────────────────────────────

test('renders footerLink node when provided', () => {
  render(
    <DiaryHistoryList
      entries={ENTRIES}
      emotionCatalog={CATALOG}
      footerLink={<span>Смотреть всю историю</span>}
    />
  );
  expect(screen.getByText('Смотреть всю историю')).toBeInTheDocument();
});

test('does not render footerLink slot when footerLink is not provided', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.queryByText('Смотреть всю историю')).not.toBeInTheDocument();
});

test('hides section title when hideTitle=true', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} hideTitle />);
  expect(screen.queryByText('История записей')).not.toBeInTheDocument();
});

test('shows section title by default (hideTitle=false)', () => {
  render(<DiaryHistoryList entries={ENTRIES} emotionCatalog={CATALOG} />);
  expect(screen.getByText('История записей')).toBeInTheDocument();
});
