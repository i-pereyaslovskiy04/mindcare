import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');
jest.mock('./components/MoodChart/MoodChart', () => ({
  __esModule: true,
  default: ({ data, period }) => (
    <div data-testid="mood-chart" data-period={period} data-points={data?.length ?? 0} />
  ),
}));
jest.mock('./components/Diary/MoodSelector', () => ({
  __esModule: true,
  default: ({ value, onChange }) => (
    <div>
      <input
        type="range"
        data-testid="mood-slider"
        min="1"
        max="10"
        value={value ?? 5}
        onChange={(e) => onChange(Number(e.target.value))}
      />
    </div>
  ),
}));
jest.mock('./components/Diary/DiaryEntryForm', () => ({
  __esModule: true,
  default: ({ isExistingEntry, moodSelected, onSave, saving, showSaved, saveError }) => (
    <div data-testid="diary-form">
      <span data-testid="is-existing">{String(isExistingEntry)}</span>
      <span data-testid="mood-selected">{String(moodSelected)}</span>
      <button
        data-testid="save-btn"
        type="button"
        onClick={onSave}
        disabled={!moodSelected || saving}
      >
        {isExistingEntry ? 'Обновить запись' : 'Сохранить отметку'}
      </button>
      {showSaved && <span data-testid="saved-msg">✓ Сохранено</span>}
      {saveError && <span data-testid="error-msg">{saveError}</span>}
    </div>
  ),
}));
jest.mock('./components/Diary/DiaryHistoryList', () => ({
  __esModule: true,
  default: ({ entries, hasMore, loadingMore, onLoadMore, loadMoreError, onEntryUpdate, onEntryDelete }) => {
    const today = new Date().toISOString().split('T')[0];
    return (
      <div data-testid="history-list">
        <span data-testid="entry-count">{entries.length}</span>
        <span data-testid="first-entry-mood">{entries[0]?.mood_score ?? ''}</span>
        {hasMore && (
          <button
            data-testid="load-more-btn"
            type="button"
            onClick={onLoadMore}
            disabled={loadingMore}
          >
            {loadingMore ? 'Загружаем…' : 'Загрузить ещё'}
          </button>
        )}
        {loadMoreError && <span data-testid="load-more-error">{loadMoreError}</span>}
        <button data-testid="trig-update" type="button" onClick={() => onEntryUpdate?.({ uuid: 'p1', entry_date: '2026-06-21', mood_score: 9, entry_text: 'edited', emotions: [] })}>tU</button>
        <button data-testid="trig-update-today" type="button" onClick={() => onEntryUpdate?.({ uuid: 'p-today', entry_date: today, mood_score: 9, entry_text: 'today edited', emotions: [] })}>tUT</button>
        <button data-testid="trig-delete" type="button" onClick={() => onEntryDelete?.('p1')}>tD</button>
        <button data-testid="trig-delete-today" type="button" onClick={() => onEntryDelete?.('p-today')}>tDT</button>
      </div>
    );
  },
}));

const MOCK_NO_ENTRY   = { entry_date: '2026-06-23', mood_score: null,  entry_text: '',     emotions: [] };
const MOCK_WITH_ENTRY = { entry_date: '2026-06-23', mood_score: 7,     entry_text: 'Test', emotions: ['calm'] };
const MOCK_EMOTIONS   = [{ key: 'calm', label: 'Спокойно', sort_order: 1 }];
const MOCK_ENTRIES    = { items: [], total: 0, limit: 10, offset: 0 };
const MOCK_SUMMARY    = {
  period: '14d',
  entries_count: 5,
  points: Array.from({ length: 14 }, (_, i) => ({
    date: `2026-06-${String(i + 10).padStart(2, '0')}`,
    label: String(i + 10),
    mood_score: i < 5 ? 7 : null,
  })),
};

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_NO_ENTRY);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES);
  diaryApi.saveTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY);
});

// ─── loading / error ──────────────────────────────────────────────────────────

test('shows loading state initially', () => {
  diaryApi.getTodayDiaryEntry.mockReturnValue(new Promise(() => {}));
  render(<DiaryPage />);
  expect(screen.getByText('Загружается…')).toBeInTheDocument();
  expect(screen.queryByTestId('diary-form')).not.toBeInTheDocument();
});

test('shows error message when APIs fail', async () => {
  // Use Error() without message so fallback 'Не удалось загрузить дневник.' activates
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error());
  diaryApi.getTodayDiaryEntry.mockRejectedValue(new Error());
  diaryApi.getDiaryEntries.mockRejectedValue(new Error());
  render(<DiaryPage />);
  expect(await screen.findByText(/Не удалось загрузить дневник/i)).toBeInTheDocument();
  expect(screen.queryByTestId('diary-form')).not.toBeInTheDocument();
});

test('retry button calls loadAll again', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error());
  diaryApi.getTodayDiaryEntry.mockRejectedValue(new Error());
  diaryApi.getDiaryEntries.mockRejectedValue(new Error());
  render(<DiaryPage />);
  await screen.findByText(/Не удалось загрузить дневник/i);

  // Restore after error so retry succeeds
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_NO_ENTRY);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES);

  fireEvent.click(screen.getByRole('button', { name: /повторить/i }));
  await waitFor(() =>
    expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(2)
  );
});

// ─── after load ───────────────────────────────────────────────────────────────

test('shows form and history panel after successful load', async () => {
  render(<DiaryPage />);
  expect(await screen.findByTestId('diary-form')).toBeInTheDocument();
  expect(screen.getByTestId('history-list')).toBeInTheDocument();
});

test('calls all 3 API functions on mount', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));
  expect(diaryApi.getDiaryEmotions).toHaveBeenCalledTimes(1);
  expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1);
});

test('passes isExistingEntry=false when today has no mood score', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('is-existing')).toHaveTextContent('false');
});

test('passes isExistingEntry=true when today has mood score', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
});

test('passes moodSelected=true when today entry has a mood score', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('mood-selected')).toHaveTextContent('true');
});

// ─── save flow ────────────────────────────────────────────────────────────────

test('save calls saveTodayDiaryEntry with mood, text, emotions', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith({
      mood_score: 7,
      entry_text: 'Test',
      emotions: ['calm'],
    })
  );
});

test('save refreshes history by calling getDiaryEntries twice', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() =>
    expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2)
  );
});

test('save shows error message when API fails', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  diaryApi.saveTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сервера'));
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('save-btn'));

  expect(await screen.findByTestId('error-msg')).toBeInTheDocument();
});

// ─── copy ─────────────────────────────────────────────────────────────────────

test('page title contains "самочувствия"', () => {
  render(<DiaryPage />);
  expect(screen.getByText(/самочувствия/i)).toBeInTheDocument();
});

test('pageSub does not contain "каждый день"', () => {
  render(<DiaryPage />);
  expect(screen.queryByText(/каждый день/i)).not.toBeInTheDocument();
});

test('pageSub contains "в удобном ритме"', () => {
  render(<DiaryPage />);
  expect(screen.getByText(/в удобном ритме/i)).toBeInTheDocument();
});

// ─── pagination / load more ───────────────────────────────────────────────────

const MOCK_ENTRY_ITEM = { uuid: 'e1', entry_date: '2026-06-23', mood_score: 7, entry_text: '', emotions: [] };

test('passes hasMore=true when total > items loaded', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [MOCK_ENTRY_ITEM], total: 5, limit: 10, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('load-more-btn')).toBeInTheDocument();
});

test('passes hasMore=false when total <= items loaded', async () => {
  // default MOCK_ENTRIES: items=[], total=0 → hasMore false
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument();
});

test('handleLoadMore appends new entries to the list', async () => {
  const page1 = { items: [{ uuid: 'p1', entry_date: '2026-06-23', mood_score: 7, entry_text: '', emotions: [] }], total: 2, limit: 10, offset: 0 };
  const page2 = { items: [{ uuid: 'p2', entry_date: '2026-06-22', mood_score: 5, entry_text: '', emotions: [] }], total: 2, limit: 10, offset: 10 };
  diaryApi.getDiaryEntries.mockResolvedValueOnce(page1).mockResolvedValueOnce(page2);

  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('entry-count')).toHaveTextContent('1');

  fireEvent.click(screen.getByTestId('load-more-btn'));

  await waitFor(() => expect(screen.getByTestId('entry-count')).toHaveTextContent('2'));
});

test('after save, getDiaryEntries is called with offset=0', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 10, offset: 0 });
});

test('load more error is shown when getDiaryEntries fails on load more', async () => {
  const page1 = { items: [MOCK_ENTRY_ITEM], total: 5, limit: 10, offset: 0 };
  diaryApi.getDiaryEntries.mockResolvedValueOnce(page1).mockRejectedValueOnce(new Error('network'));

  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('load-more-btn'));

  expect(await screen.findByTestId('load-more-error')).toBeInTheDocument();
});

test('load more button is disabled while loading more', async () => {
  const page1 = { items: [MOCK_ENTRY_ITEM], total: 5, limit: 10, offset: 0 };
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce(page1)
    .mockReturnValueOnce(new Promise(() => {})); // never resolves

  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('load-more-btn'));

  await waitFor(() => expect(screen.getByTestId('load-more-btn')).toBeDisabled());
});

// ─── handleEntryUpdate / handleEntryDelete ────────────────────────────────────

const TODAY = new Date().toISOString().split('T')[0];

test('handleEntryUpdate replaces entry in list', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
    total: 1, limit: 10, offset: 0,
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('7');
  fireEvent.click(screen.getByTestId('trig-update'));
  expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('9');
});

test('handleEntryDelete removes entry from list', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('trig-delete'));
  await waitFor(() => expect(screen.getByTestId('entry-count')).toHaveTextContent('0'));
});

test('handleEntryDelete of today entry resets today form state', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p-today', entry_date: TODAY, mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 });
  diaryApi.getTodayDiaryEntry.mockResolvedValue({
    entry_date: TODAY, mood_score: 7, entry_text: '', emotions: [],
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
  fireEvent.click(screen.getByTestId('trig-delete-today'));
  // Form reset is synchronous, before async reload.
  expect(screen.getByTestId('is-existing')).toHaveTextContent('false');
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

test('handleEntryUpdate of today entry syncs main form mood and isExisting', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [{ uuid: 'p-today', entry_date: TODAY, mood_score: 5, entry_text: '', emotions: [] }],
    total: 1, limit: 10, offset: 0,
  });
  diaryApi.getTodayDiaryEntry.mockResolvedValue({
    entry_date: TODAY, mood_score: 5, entry_text: '', emotions: [],
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('trig-update-today'));

  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
  expect(screen.getByTestId('mood-selected')).toHaveTextContent('true');
});

test('handleEntryDelete of non-today entry does not reset today form', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 });
  diaryApi.getTodayDiaryEntry.mockResolvedValue({
    entry_date: TODAY, mood_score: 8, entry_text: '', emotions: [],
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
  fireEvent.click(screen.getByTestId('trig-delete'));
  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

// ─── pagination fix after delete ─────────────────────────────────────────────

const MOCK_ENTRY_P2 = { uuid: 'p2', entry_date: '2026-06-20', mood_score: 5, entry_text: '', emotions: [] };

test('handleEntryDelete reloads history from server with offset=0', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 2, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [MOCK_ENTRY_P2], total: 1, limit: 10, offset: 0 });

  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 10, offset: 0 });
  await waitFor(() => expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('5'));
});

test('handleEntryDelete resets hasMore based on reloaded server total', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 2, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [MOCK_ENTRY_P2], total: 1, limit: 10, offset: 0 });

  render(<DiaryPage />);
  await screen.findByTestId('load-more-btn');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(screen.queryByTestId('load-more-btn')).not.toBeInTheDocument());
});

// ─── summary / observation ────────────────────────────────────────────────────

test('getDiarySummary called with "14d" on initial load', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('14d'));
});

test('observation block heading "Самонаблюдение" renders after load', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Самонаблюдение')).toBeInTheDocument();
});

test('period chip "14 дней" is visible', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');
  expect(screen.getByRole('button', { name: '14 дней' })).toBeInTheDocument();
});

test('period chip "Месяц" is visible', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');
  expect(screen.getByRole('button', { name: 'Месяц' })).toBeInTheDocument();
});

test('period chip "Год" is visible', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');
  expect(screen.getByRole('button', { name: 'Год' })).toBeInTheDocument();
});

test('clicking "Месяц" chip calls getDiarySummary with "month"', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');

  fireEvent.click(screen.getByRole('button', { name: 'Месяц' }));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('month'));
});

test('clicking "Год" chip calls getDiarySummary with "year"', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');

  fireEvent.click(screen.getByRole('button', { name: 'Год' }));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledWith('year'));
});

test('MoodChart is rendered inside observation block', async () => {
  render(<DiaryPage />);
  expect(await screen.findByTestId('mood-chart')).toBeInTheDocument();
});

test('MoodChart receives mapped points from summary', async () => {
  render(<DiaryPage />);
  const chart = await screen.findByTestId('mood-chart');
  expect(chart).toHaveAttribute('data-points', String(MOCK_SUMMARY.points.length));
});

test('MoodChart receives active period', async () => {
  render(<DiaryPage />);
  const chart = await screen.findByTestId('mood-chart');
  expect(chart).toHaveAttribute('data-period', '14d');
});

test('MoodChart period updates when chip is clicked', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');

  fireEvent.click(screen.getByRole('button', { name: 'Год' }));

  await waitFor(() =>
    expect(screen.getByTestId('mood-chart')).toHaveAttribute('data-period', 'year')
  );
});

test('observation block shows loading state while summary is loading', async () => {
  diaryApi.getDiarySummary.mockReturnValue(new Promise(() => {}));
  render(<DiaryPage />);
  // Wait for main load to finish (observation card appears) then check for loading text
  await screen.findByText('Самонаблюдение');
  expect(screen.getByText('Загружается…')).toBeInTheDocument();
});

test('summary error shows "Не удалось загрузить самонаблюдение"', async () => {
  diaryApi.getDiarySummary.mockRejectedValue(new Error('fail'));
  render(<DiaryPage />);
  expect(await screen.findByText(/Не удалось загрузить самонаблюдение/i)).toBeInTheDocument();
});

test('summary error retry button calls getDiarySummary again', async () => {
  diaryApi.getDiarySummary.mockRejectedValue(new Error('fail'));
  render(<DiaryPage />);
  await screen.findByText(/Не удалось загрузить самонаблюдение/i);

  diaryApi.getDiarySummary.mockResolvedValue(MOCK_SUMMARY);
  fireEvent.click(screen.getByRole('button', { name: /повторить/i }));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
});

test('save triggers getDiarySummary reload for active period', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  // findByTestId('mood-chart') guarantees both layout and summary are loaded
  await screen.findByTestId('mood-chart');

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiarySummary).toHaveBeenLastCalledWith('14d');
});

test('edit entry triggers getDiarySummary reload', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('mood-chart');

  fireEvent.click(screen.getByTestId('trig-update'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
});

test('delete entry triggers getDiarySummary reload', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 10, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 10, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('mood-chart');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
});

test('hint shows 0-entry text when entries_count is 0', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({ period: '14d', entries_count: 0, points: [] });
  render(<DiaryPage />);
  expect(await screen.findByText(/Пока нет данных для графика/i)).toBeInTheDocument();
});

test('hint shows 1-entry text when entries_count is 1', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d', entries_count: 1,
    points: [{ date: '2026-06-23', label: 'Вт', mood_score: 7 }],
  });
  render(<DiaryPage />);
  expect(await screen.findByText(/Есть первая отметка/i)).toBeInTheDocument();
});

test('hint shows 2-3-entry text when entries_count is 3', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d', entries_count: 3,
    points: [{ date: '2026-06-23', label: 'Вт', mood_score: 7 }],
  });
  render(<DiaryPage />);
  expect(await screen.findByText(/Пока мало данных для тренда/i)).toBeInTheDocument();
});

test('hint shows 4+-entry text when entries_count >= 4', async () => {
  render(<DiaryPage />); // MOCK_SUMMARY has entries_count: 5
  expect(await screen.findByText(/Можно смотреть первые изменения/i)).toBeInTheDocument();
});
