import { render, screen, waitFor, fireEvent } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');
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
  default: ({ entries }) => (
    <div data-testid="history-list">
      <span data-testid="entry-count">{entries.length}</span>
    </div>
  ),
}));

const MOCK_NO_ENTRY   = { entry_date: '2026-06-23', mood_score: null,  entry_text: '',     emotions: [] };
const MOCK_WITH_ENTRY = { entry_date: '2026-06-23', mood_score: 7,     entry_text: 'Test', emotions: ['calm'] };
const MOCK_EMOTIONS   = [{ key: 'calm', label: 'Спокойно', sort_order: 1 }];
const MOCK_ENTRIES    = { items: [], total: 0, limit: 10, offset: 0 };

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(MOCK_NO_ENTRY);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES);
  diaryApi.saveTodayDiaryEntry.mockResolvedValue(MOCK_WITH_ENTRY);
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
