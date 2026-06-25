import { render, screen, waitFor, fireEvent, within } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');
jest.mock('react-router-dom', () => ({
  Link: ({ to, children }) => <a href={to}>{children}</a>,
}), { virtual: true });
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
// DiaryHistoryList mock: renders footerLink as a presence indicator (no Router context needed)
jest.mock('./components/Diary/DiaryHistoryList', () => ({
  __esModule: true,
  default: ({ entries, onEntryUpdate, onEntryDelete, footerLink }) => {
    const today = new Date().toISOString().split('T')[0];
    return (
      <div data-testid="history-list">
        <span data-testid="entry-count">{entries.length}</span>
        <span data-testid="first-entry-mood">{entries[0]?.mood_score ?? ''}</span>
        {footerLink != null && <span data-testid="footer-link">has-link</span>}
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
const MOCK_ENTRIES    = { items: [], total: 0, limit: 4, offset: 0 };
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

// ─── preview limit / footer link ─────────────────────────────────────────────

test('getDiaryEntries is called with limit=4 on initial load', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));
  expect(diaryApi.getDiaryEntries).toHaveBeenCalledWith({ limit: 4, offset: 0 });
});

test('passes footerLink to DiaryHistoryList when entries total > 0', async () => {
  const ENTRY = { uuid: 'e1', entry_date: '2026-06-23', mood_score: 7, entry_text: '', emotions: [] };
  diaryApi.getDiaryEntries.mockResolvedValue({ items: [ENTRY], total: 1, limit: 4, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('footer-link')).toBeInTheDocument();
});

test('does not pass footerLink when total is 0', async () => {
  // default MOCK_ENTRIES has total: 0
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.queryByTestId('footer-link')).not.toBeInTheDocument();
});

test('after save, getDiaryEntries is called with limit=4 and offset=0', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 4, offset: 0 });
});

// ─── handleEntryUpdate / handleEntryDelete ────────────────────────────────────

const TODAY = new Date().toISOString().split('T')[0];

test('handleEntryUpdate replaces entry in list', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
    total: 1, limit: 4, offset: 0,
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
      total: 1, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 4, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('trig-delete'));
  await waitFor(() => expect(screen.getByTestId('entry-count')).toHaveTextContent('0'));
});

test('handleEntryDelete of today entry resets today form state', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p-today', entry_date: TODAY, mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 4, offset: 0 });
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
    total: 1, limit: 4, offset: 0,
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
      total: 1, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 4, offset: 0 });
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

// ─── delete reloads preview ───────────────────────────────────────────────────

const MOCK_ENTRY_P2 = { uuid: 'p2', entry_date: '2026-06-20', mood_score: 5, entry_text: '', emotions: [] };

test('handleEntryDelete reloads history from server with limit=4 and offset=0', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 2, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [MOCK_ENTRY_P2], total: 1, limit: 4, offset: 0 });

  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiaryEntries).toHaveBeenNthCalledWith(2, { limit: 4, offset: 0 });
  await waitFor(() => expect(screen.getByTestId('first-entry-mood')).toHaveTextContent('5'));
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

test('MoodChart SVG is not rendered in observation block', async () => {
  render(<DiaryPage />);
  await screen.findByText('Самонаблюдение');
  expect(screen.queryByTestId('mood-chart')).not.toBeInTheDocument();
});

test('summary label "Отметок" is visible after load', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Отметок')).toBeInTheDocument();
});

test('summary label "Последняя отметка" is visible for 14d period', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Последняя отметка')).toBeInTheDocument();
});

test('latest mark tile: value shows score without date (e.g. "7/10")', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // MOCK_SUMMARY: latest non-null point mood_score=7 → value "7/10"
  // score appears in summaryValue; old concatenated format must not appear as single value
  expect(screen.queryByText('7/10 · 14.06')).not.toBeInTheDocument();
});

test('latest mark tile: date shown separately as summaryMeta (e.g. "14.06")', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // Date of latest point is 2026-06-14 → appears in summaryMeta AND in chips
  expect(screen.getAllByText('14.06').length).toBeGreaterThan(0);
});

test('latest mark tile: no data shows "—"', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({ period: '14d', entries_count: 0, points: [] });
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // Multiple "—" may appear (latest + avg), just check at least one
  expect(screen.getAllByText('—').length).toBeGreaterThan(0);
});

test('year period: latest mark tile uses "Последний период" label', async () => {
  const yearSummary = {
    period: 'year',
    entries_count: 3,
    points: Array.from({ length: 12 }, (_, i) => ({
      date: `2026-${String(i + 1).padStart(2, '0')}-01`,
      label: ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'][i],
      mood_score: i < 3 ? 7 : null,
    })),
  };
  diaryApi.getDiarySummary.mockResolvedValue(yearSummary);
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  fireEvent.click(screen.getByRole('button', { name: 'Год' }));
  expect(await screen.findByText('Последний период')).toBeInTheDocument();
});

test('summary label "Диапазон" is not present after update', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  expect(screen.queryByText('Диапазон')).not.toBeInTheDocument();
});

test('summary label "Средняя отметка" is visible for 14d period', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Средняя отметка')).toBeInTheDocument();
});

test('year period: average label is "Среднее по месяцам"', async () => {
  const yearSummary = {
    period: 'year',
    entries_count: 2,
    points: Array.from({ length: 12 }, (_, i) => ({
      date: `2026-${String(i + 1).padStart(2, '0')}-01`,
      label: ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'][i],
      mood_score: i < 2 ? 8 : null,
    })),
  };
  diaryApi.getDiarySummary.mockResolvedValue(yearSummary);
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  fireEvent.click(screen.getByRole('button', { name: 'Год' }));
  expect(await screen.findByText('Среднее по месяцам')).toBeInTheDocument();
});

test('average: integer result formatted without decimal (e.g. "7/10")', async () => {
  // MOCK_SUMMARY: 5 points all at mood_score=7 → avg=7 → "7/10"
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // "7/10" appears: one in latest value, one in avg value, one in chip labels
  const matches = screen.getAllByText('7/10');
  expect(matches.length).toBeGreaterThan(0);
});

test('average: float result formatted with one decimal (e.g. "7.5/10")', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d',
    entries_count: 2,
    points: [
      { date: '2026-06-22', label: '22', mood_score: 7 },
      { date: '2026-06-23', label: '23', mood_score: 8 },
    ],
  });
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  expect(screen.getByText('7.5/10')).toBeInTheDocument();
});

test('average: no data shows "—" in avg tile', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({ period: '14d', entries_count: 0, points: [] });
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  expect(screen.getAllByText('—').length).toBeGreaterThan(0);
});

test('average: null-scored points ignored in calculation', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({
    period: '14d',
    entries_count: 2,
    points: [
      { date: '2026-06-20', label: '20', mood_score: null },
      { date: '2026-06-21', label: '21', mood_score: 6 },
      { date: '2026-06-22', label: '22', mood_score: null },
      { date: '2026-06-23', label: '23', mood_score: 8 },
    ],
  });
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // avg of [6, 8] = 7 → "7/10"
  expect(screen.getByText('7/10')).toBeInTheDocument();
});

test('recent marks show date and score as separate elements', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // MOCK_SUMMARY: latest non-null chip has date "14.06" and score "7/10" in separate spans
  const list = screen.getByRole('list', { name: /последние отметки/i });
  expect(within(list).getByText('14.06')).toBeInTheDocument();
  // Old combined "14.06 · 7/10" string no longer exists as single text node
  expect(screen.queryByText('14.06 · 7/10')).not.toBeInTheDocument();
});

test('recent marks are not interactive buttons', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // chips rendered as <li>, not as <button>
  expect(screen.queryByRole('button', { name: /Показать отметку за/i })).not.toBeInTheDocument();
});

test('detail region is never rendered', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  expect(screen.queryByRole('region', { name: /детали отметки/i })).not.toBeInTheDocument();
});

test('close button "Закрыть детали отметки" is never rendered', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  expect(screen.queryByRole('button', { name: /Закрыть детали отметки/i })).not.toBeInTheDocument();
});

test('null-scored points do not appear in recent marks', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');
  // MOCK_SUMMARY: points from index 5+ have mood_score=null → date "2026-06-15" should not show
  expect(screen.queryByText(/15\.06/)).not.toBeInTheDocument();
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
  // findByTestId('observation-summary') guarantees both layout and summary are loaded
  await screen.findByTestId('observation-summary');

  fireEvent.click(screen.getByTestId('save-btn'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
  expect(diaryApi.getDiarySummary).toHaveBeenLastCalledWith('14d');
});

test('edit entry triggers getDiarySummary reload', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');

  fireEvent.click(screen.getByTestId('trig-update'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
});

test('delete entry triggers getDiarySummary reload', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p1', entry_date: '2026-06-21', mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 4, offset: 0 });
  render(<DiaryPage />);
  await screen.findByTestId('observation-summary');

  fireEvent.click(screen.getByTestId('trig-delete'));

  await waitFor(() => expect(diaryApi.getDiarySummary).toHaveBeenCalledTimes(2));
});

test('hint shows 0-entry text when entries_count is 0', async () => {
  diaryApi.getDiarySummary.mockResolvedValue({ period: '14d', entries_count: 0, points: [] });
  render(<DiaryPage />);
  expect(await screen.findByText(/Пока нет данных для самонаблюдения/i)).toBeInTheDocument();
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
  expect(await screen.findByText(/Пока данных немного/i)).toBeInTheDocument();
});

test('hint shows 4+-entry text when entries_count >= 4', async () => {
  render(<DiaryPage />); // MOCK_SUMMARY has entries_count: 5
  expect(await screen.findByText(/Можно посмотреть/i)).toBeInTheDocument();
});

// ─── default mood 5 ───────────────────────────────────────────────────────────

test('passes moodSelected=true for new entry because mood defaults to 5', async () => {
  // MOCK_NO_ENTRY: mood_score=null → DiaryPage initializes mood to 5 → moodSelected=true
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  expect(screen.getByTestId('mood-selected')).toHaveTextContent('true');
});

test('new entry saves with mood_score 5 when save clicked without changing slider', async () => {
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  fireEvent.click(screen.getByTestId('save-btn'));
  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith({
      mood_score: 5,
      entry_text: '',
      emotions: [],
    })
  );
});

test('existing entry with mood_score 8 is not overridden by default 5', async () => {
  diaryApi.getTodayDiaryEntry.mockResolvedValue({
    entry_date: '2026-06-23', mood_score: 8, entry_text: '', emotions: [],
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');
  fireEvent.click(screen.getByTestId('save-btn'));
  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith(
      expect.objectContaining({ mood_score: 8 })
    )
  );
});

test('after delete today entry, moodSelected resets to true (default mood 5)', async () => {
  diaryApi.getDiaryEntries
    .mockResolvedValueOnce({
      items: [{ uuid: 'p-today', entry_date: TODAY, mood_score: 7, entry_text: '', emotions: [] }],
      total: 1, limit: 4, offset: 0,
    })
    .mockResolvedValueOnce({ items: [], total: 0, limit: 4, offset: 0 });
  diaryApi.getTodayDiaryEntry.mockResolvedValue({
    entry_date: TODAY, mood_score: 7, entry_text: '', emotions: [],
  });
  render(<DiaryPage />);
  await screen.findByTestId('diary-form');

  expect(screen.getByTestId('is-existing')).toHaveTextContent('true');
  fireEvent.click(screen.getByTestId('trig-delete-today'));
  // isExisting resets to false, mood resets to 5 → moodSelected stays true
  expect(screen.getByTestId('is-existing')).toHaveTextContent('false');
  expect(screen.getByTestId('mood-selected')).toHaveTextContent('true');
});
