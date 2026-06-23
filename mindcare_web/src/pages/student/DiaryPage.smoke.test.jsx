import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');

const MOCK_EMOTIONS = [
  { key: 'calm',   label: 'Спокойно', sort_order: 1 },
  { key: 'joyful', label: 'Радостно', sort_order: 2 },
];

const EMPTY_TODAY = {
  entry_date: '2026-06-18',
  mood_score: null,
  entry_text: '',
  emotions: [],
};

const FILLED_TODAY = {
  entry_date: '2026-06-18',
  mood_score: 7,
  entry_text: 'Хороший день',
  emotions: ['calm'],
};

const MOCK_ENTRIES_RESP = {
  items: [
    {
      uuid: 'abc123',
      entry_date: '2026-06-17',
      mood_score: 5,
      entry_text: 'Вчера был хороший день',
      emotions: ['calm'],
      created_at: '2026-06-17T10:00:00',
      updated_at: '2026-06-17T10:00:00',
    },
  ],
  total: 1,
  limit: 10,
  offset: 0,
};

beforeEach(() => {
  jest.clearAllMocks();
  diaryApi.getDiaryEmotions.mockResolvedValue(MOCK_EMOTIONS);
  diaryApi.getTodayDiaryEntry.mockResolvedValue(EMPTY_TODAY);
  diaryApi.getDiaryEntries.mockResolvedValue(MOCK_ENTRIES_RESP);
  diaryApi.saveTodayDiaryEntry.mockResolvedValue(FILLED_TODAY);
});

// ─── mount + data loading ─────────────────────────────────────────────────────

test('calls emotions, today, entries APIs on mount', async () => {
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEmotions).toHaveBeenCalledTimes(1));
  expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1);
  expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1);
});

test('renders emotion chips from API after load', async () => {
  render(<DiaryPage />);
  // "Что вы чувствуете?" is the new emotion section label — appears once load is complete
  expect(await screen.findByText('Что вы чувствуете?')).toBeInTheDocument();
  expect(screen.getAllByText('Спокойно').length).toBeGreaterThan(0);
  expect(screen.getByText('Радостно')).toBeInTheDocument();
});

test('shows empty today state — Выберите настроение and dash score', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');
  expect(screen.getByText('Выберите настроение')).toBeInTheDocument();
  expect(screen.getByText('—')).toBeInTheDocument();
});

test('emotion chips from API props — custom emotion key appears as label', async () => {
  diaryApi.getDiaryEmotions.mockResolvedValue([
    { key: 'custom_key', label: 'Уникальная эмоция', sort_order: 1 },
  ]);
  render(<DiaryPage />);
  expect(await screen.findByText('Уникальная эмоция')).toBeInTheDocument();
});

// ─── save flow ────────────────────────────────────────────────────────────────

test('submit calls saveTodayDiaryEntry with mood_score and selected emotions', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  // Set mood via range slider
  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  // Select emotion chip
  const chips = screen.getAllByRole('button', { name: 'Спокойно' });
  fireEvent.click(chips[0]);

  // New entry — button label is "Сохранить отметку"
  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith(
      expect.objectContaining({ mood_score: 7, emotions: ['calm'] })
    )
  );
});

test('after save, getDiaryEntries is called a second time', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

// ─── history ─────────────────────────────────────────────────────────────────

test('history entry text is shown and emotion key is mapped to label', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Вчера был хороший день')).toBeInTheDocument();
  expect(screen.getAllByText('Спокойно').length).toBeGreaterThan(0);
});

test('unknown emotion key in history shows the key itself without crashing', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    items: [
      {
        uuid: 'u1',
        entry_date: '2026-06-17',
        mood_score: 5,
        entry_text: '',
        emotions: ['unknown_xyz_key'],
        created_at: '2026-06-17T10:00:00',
        updated_at: '2026-06-17T10:00:00',
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  render(<DiaryPage />);
  expect(await screen.findByText('unknown_xyz_key')).toBeInTheDocument();
});

// ─── error handling ───────────────────────────────────────────────────────────

test('shows load error message when API fails, with retry button', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('Ошибка сети'));
  render(<DiaryPage />);
  expect(await screen.findByText(/ошибка/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /повторить/i })).toBeInTheDocument();
});

test('shows save error inline after failed save', async () => {
  diaryApi.saveTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сохранения'));
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  // Open details so textarea is visible, then type text
  fireEvent.click(screen.getByRole('button', { name: /добавить подробности/i }));
  const textarea = screen.getByPlaceholderText(/что повлияло на состояние/i);
  fireEvent.change(textarea, { target: { value: 'Мой текст' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  fireEvent.click(saveBtn);

  expect(await screen.findByText('Ошибка сохранения')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Мой текст')).toBeInTheDocument();
});

// ─── submit button state ──────────────────────────────────────────────────────

test('submit button is disabled when mood is not selected', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');
  // mood starts as null from EMPTY_TODAY
  const submitBtn = screen.getByRole('button', { name: /сохранить отметку/i });
  expect(submitBtn).toBeDisabled();
});

test('submit button enables after slider is moved', async () => {
  render(<DiaryPage />);
  await screen.findByText('Что вы чувствуете?');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '6' } });

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /сохранить отметку/i })).not.toBeDisabled()
  );
});

// ─── load more visibility ─────────────────────────────────────────────────────

test('"Загрузить ещё" not shown when all entries fit in first page', async () => {
  // default mock: { items: [1 entry], total: 1 } → hasMore = false
  render(<DiaryPage />);
  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1));
  expect(screen.queryByRole('button', { name: /загрузить ещё/i })).not.toBeInTheDocument();
});

test('"Загрузить ещё" shown when total > items in first page', async () => {
  diaryApi.getDiaryEntries.mockResolvedValue({
    ...MOCK_ENTRIES_RESP,
    total: 5,   // 1 item loaded, 5 total → hasMore = true
  });
  render(<DiaryPage />);
  expect(await screen.findByRole('button', { name: /загрузить ещё/i })).toBeInTheDocument();
});
