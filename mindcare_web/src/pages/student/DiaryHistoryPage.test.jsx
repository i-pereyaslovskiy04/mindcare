import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryHistoryPage from './DiaryHistoryPage';

jest.mock('../../api/diary.api');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children }) => <a href={to}>{children}</a>,
}), { virtual: true });
jest.mock('./components/Diary/DiaryHistoryList', () => ({
  __esModule: true,
  default: ({ entries, hasMore, loadingMore, onLoadMore, loadMoreError, onEntryUpdate, onEntryDelete, hideTitle }) => (
    <div data-testid="history-list">
      <span data-testid="entry-count">{entries.length}</span>
      <span data-testid="hide-title">{String(hideTitle)}</span>
      <span data-testid="first-entry-mood">{entries[0]?.mood_score ?? ''}</span>
      {hasMore && (
        <button data-testid="load-more-btn" type="button" onClick={onLoadMore} disabled={loadingMore}>
          {loadingMore ? 'Загружаем…' : 'Загрузить ещё'}
        </button>
      )}
      {loadMoreError && <span data-testid="load-more-error">{loadMoreError}</span>}
      <button
        data-testid="trig-update"
        type="button"
        onClick={() => onEntryUpdate?.({ uuid: 'u1', entry_date: '2026-06-21', mood_score: 9, entry_text: 'edited', emotions: [] })}
      >
        tU
      </button>
      <button data-testid="trig-delete" type="button" onClick={() => onEntryDelete?.('u1')}>
        tD
      </button>
    </div>
  ),
}));

const MOCK_EMOTIONS = [{ key: 'calm', label: 'Спокойно', sort_order: 1 }];
const MOCK_ENTRIES_EMPTY = { items: [], total: 0, limit: 10, offset: 0 };
const ENTRY_1 = { uuid: 'u1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] };

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES_EMPTY);
});

// ─── header / structure ───────────────────────────────────────────────────────

test('renders heading "История записей"', async () => {
  render(<DiaryHistoryPage />);
  expect(await screen.findByRole('heading', { name: /история записей/i })).toBeInTheDocument();
});

test('renders breadcrumb text', async () => {
  render(<DiaryHistoryPage />);
  expect(await screen.findByText(/Личный кабинет \/ Дневник состояния \/ История/i)).toBeInTheDocument();
});

test('renders back link "Вернуться к дневнику"', async () => {
  render(<DiaryHistoryPage />);
  expect(await screen.findByRole('link', { name: /Вернуться к дневнику/i })).toBeInTheDocument();
});

test('renders page description', async () => {
  render(<DiaryHistoryPage />);
  expect(await screen.findByText(/Здесь собраны все ваши записи/i)).toBeInTheDocument();
});

// ─── loading / error ──────────────────────────────────────────────────────────

test('shows loading state initially', () => {
  diaryApi.getDiaryEntries.mockReturnValue(new Promise(() => {}));
  render(<DiaryHistoryPage />);
  expect(screen.getByText('Загружается…')).toBeInTheDocument();
  expect(screen.queryByTestId('history-list')).not.toBeInTheDocument();
});

test('shows error message on load failure', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('сетевая ошибка'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('сетевая ошибка'));
  render(<DiaryHistoryPage />);
  expect(await screen.findByText(/сетевая ошибка/i)).toBeInTheDocument();
});

test('shows retry button on load failure', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('fail'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('fail'));
  render(<DiaryHistoryPage />);
  expect(await screen.findByRole('button', { name: /повторить/i })).toBeInTheDocument();
});

test('retry button reloads the page', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('fail'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('fail'));
  render(<DiaryHistoryPage />);
  await screen.findByRole('button', { name: /повторить/i });

  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES_EMPTY);

  fireEvent.click(screen.getByRole('button', { name: /повторить/i }));
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

// ─── initial data load ────────────────────────────────────────────────────────

test('calls getDiaryEntries with limit=10 and offset=0 on mount', async () => {
  render(<DiaryHistoryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));
  expect(diaryApi.getDiaryEntries).toHaveBeenCalledWith({ limit: 10, offset: 0 });
});

test('passes hideTitle=true to DiaryHistoryList', async () => {
  render(<DiaryHistoryPage />);
  await screen.findByTestId('history-list');
  expect(screen.getByTestId('hide-title')).toHaveTextContent('true');
});

test('empty state: DiaryHistoryList receives 0 entries', async () => {
  render(<DiaryHistoryPage />);
  await screen.findByTestId('history-list');
  expect(screen.getByTestId('entry-count')).toHaveTextContent('0');
});

test('passes hasMore=true when total > items loaded', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [ENTRY_1], total: 5, limit: 10, offset: 0 });
  render(<DiaryHistoryPage />);
  expect(await screen.findByTestId('load-more-btn')).toBeInTheDocument();
});

test('passes hasMore=false when all items fit in first page', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [ENTRY_1], total: 1, limit: 10, offset: 0 });
  render(<DiaryHistoryPage />);
  await screen.findByTestId('history-list');
  expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument();
});

// ─── load more ────────────────────────────────────────────────────────────────

test('load more calls getDiaryEntries with next offset', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({ items: [ENTRY_1], total: 15, limit: 10, offset: 0 })
    .mockResolvedValueOnce({ items: [], total: 15, limit: 10, offset: 10 });

  render(<DiaryHistoryPage />);
  fireEvent.click(await screen.findByTestId('load-more-btn'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 10, offset: 10 });
});

test('load more appends entries to the list', async () => {
  const ENTRY_2 = { uuid: 'u2', entry_date: '2026-06-20', mood_score: 5, entry_text: '', emotions: [] };
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({ items: [ENTRY_1], total: 2, limit: 10, offset: 0 })
    .mockResolvedValueOnce({ items: [ENTRY_2], total: 2, limit: 10, offset: 10 });

  render(<DiaryHistoryPage />);
  expect(await screen.findByTestId('entry-count')).toHaveTextContent('1');

  fireEvent.click(screen.getByTestId('load-more-btn'));

  await waitFor(() => expect(screen.getByTestId('entry-count')).toHaveTextContent('2'));
});

test('load more error is shown when getDiaryEntries fails on load more', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({ items: [ENTRY_1], total: 5, limit: 10, offset: 0 })
    .mockRejectedValueOnce(new Error('network'));

  render(<DiaryHistoryPage />);
  fireEvent.click(await screen.findByTestId('load-more-btn'));

  expect(await screen.findByTestId('load-more-error')).toBeInTheDocument();
});

// ─── edit / delete ────────────────────────────────────────────────────────────

test('handleEntryUpdate replaces entry in list', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [ENTRY_1], total: 1, limit: 10, offset: 0 });
  render(<DiaryHistoryPage />);
  await screen.findByTestId('history-list');

  expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('7');
  fireEvent.click(screen.getByTestId('trig-update'));
  expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('9');
});

test('handleEntryDelete removes entry and reloads from offset=0', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({ items: [ENTRY_1], total: 1, limit: 10, offset: 0 })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 });

  render(<DiaryHistoryPage />);
  await screen.findByTestId('history-list');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 10, offset: 0 });
  await waitFor(() => expect(screen.getByTestId('entry-count')).toHaveTextContent('0'));
});
