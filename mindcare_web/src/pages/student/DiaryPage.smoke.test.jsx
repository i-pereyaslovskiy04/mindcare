import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import * as diaryApi from '../../api/diary.api';
import DiaryPage from './DiaryPage';

jest.mock('../../api/diary.api');

const MOCK_EMOTIONS = [
  { key: 'calm', label: 'Спокойно', sort_order: 1 },
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

test('calls emotions, today, entries APIs on mount', async () => {
  render(<DiaryPage />);
  // All three are called simultaneously in Promise.all — wait for one, then check the others
  await waitFor(() => expect(diaryApi.getDiaryEmotions).toHaveBeenCalledTimes(1));
  expect(diaryApi.getTodayDiaryEntry).toHaveBeenCalledTimes(1);
  expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(1);
});

test('renders form and emotion chips from API after load', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Запись в дневнике')).toBeInTheDocument();
  // 'Спокойно' appears in both the form chip and history entry — use getAllByText
  expect(screen.getAllByText('Спокойно').length).toBeGreaterThan(0);
  expect(screen.getByText('Радостно')).toBeInTheDocument();
});

test('shows empty today state — Выберите настроение and dash score', async () => {
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');
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

test('submit calls saveTodayDiaryEntry with mood_score and selected emotions', async () => {
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');

  // Set mood via range slider
  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  // Select emotion chip (there may be a chip in form AND a tag in history — use first)
  const chips = screen.getAllByRole('button', { name: 'Спокойно' });
  fireEvent.click(chips[0]);

  // Click submit button (type="submit" inside form — triggers onSubmit)
  const saveBtn = screen.getByRole('button', { name: /сохранить запись/i });
  fireEvent.click(saveBtn);

  await waitFor(() =>
    expect(diaryApi.saveTodayDiaryEntry).toHaveBeenCalledWith(
      expect.objectContaining({ mood_score: 7, emotions: ['calm'] })
    )
  );
});

test('after save, getDiaryEntries is called a second time', async () => {
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить запись/i });
  fireEvent.click(saveBtn);

  await waitFor(() => expect(diaryApi.getDiaryEntries).toHaveBeenCalledTimes(2));
});

test('history entry text is shown and emotion key is mapped to label', async () => {
  render(<DiaryPage />);
  expect(await screen.findByText('Вчера был хороший день')).toBeInTheDocument();
  // 'calm' key → 'Спокойно' label from catalog (also shown in form chip)
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
      },
    ],
    total: 1,
    limit: 10,
    offset: 0,
  });
  render(<DiaryPage />);
  expect(await screen.findByText('unknown_xyz_key')).toBeInTheDocument();
});

test('shows load error message when API fails, with retry button', async () => {
  diaryApi.getDiaryEmotions.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сети'));
  diaryApi.getDiaryEntries.mockRejectedValue(new Error('Ошибка сети'));
  render(<DiaryPage />);
  // DiaryPage shows err.message directly
  expect(await screen.findByText(/ошибка/i)).toBeInTheDocument();
  expect(screen.getByRole('button', { name: /повторить/i })).toBeInTheDocument();
});

test('shows save error inline, preserves typed text on failure', async () => {
  diaryApi.saveTodayDiaryEntry.mockRejectedValue(new Error('Ошибка сохранения'));
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '7' } });

  const textarea = screen.getByPlaceholderText(/опишите своё состояние/i);
  fireEvent.change(textarea, { target: { value: 'Мой текст' } });

  const saveBtn = screen.getByRole('button', { name: /сохранить запись/i });
  fireEvent.click(saveBtn);

  expect(await screen.findByText('Ошибка сохранения')).toBeInTheDocument();
  expect(screen.getByDisplayValue('Мой текст')).toBeInTheDocument();
});

test('submit button is disabled when mood is not selected', async () => {
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');
  // mood starts as null from EMPTY_TODAY
  const submitBtn = screen.getByRole('button', { name: /сохранить/i });
  expect(submitBtn).toBeDisabled();
});

test('submit button enables after slider is moved', async () => {
  render(<DiaryPage />);
  await screen.findByText('Запись в дневнике');

  const slider = screen.getByRole('slider', { name: /настроения/i });
  fireEvent.change(slider, { target: { value: '6' } });

  await waitFor(() =>
    expect(screen.getByRole('button', { name: /сохранить запись/i })).not.toBeDisabled()
  );
});
