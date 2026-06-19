import { render, screen } from '@testing-library/react';
import MoodChart from './MoodChart';

// ─── Empty state ──────────────────────────────────────────────────────────────

test('shows empty state main message when data is empty array', () => {
  render(<MoodChart data={[]} />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('shows empty state second line prompting to make a diary entry', () => {
  render(<MoodChart data={[]} />);
  expect(screen.getByText(/сделайте запись в дневнике/i)).toBeInTheDocument();
});

test('shows empty state when all mood_score values are null (short array)', () => {
  render(<MoodChart data={[{ l: 'Пн', v: null }, { l: 'Вт', v: null }]} />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('shows empty state when all 14 points have null mood_score (full period frame)', () => {
  const allNull = Array.from({ length: 14 }, (_, i) => ({
    l: 'Пн',
    v: null,
    d: `2026-06-${String(i + 6).padStart(2, '0')}`,
  }));
  render(<MoodChart data={allNull} period="14d" />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

test('shows empty state for single null data point', () => {
  render(<MoodChart data={[{ l: 'Пн', v: null }]} />);
  expect(screen.getByText(/пока нет записей/i)).toBeInTheDocument();
});

// ─── Sparse state ─────────────────────────────────────────────────────────────

test('shows compact sparse hint when only one real point exists', () => {
  render(
    <MoodChart
      data={[{ l: 'Пн', v: null, d: '2026-06-15' }, { l: 'Пн', v: 7, d: '2026-06-19' }]}
      period="14d"
    />,
  );
  expect(screen.getByText('Мало данных для тренда')).toBeInTheDocument();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('shows compact sparse hint when two real points exist', () => {
  render(
    <MoodChart
      data={[
        { l: 'Пн', v: 6, d: '2026-06-17' },
        { l: 'Пн', v: null, d: '2026-06-18' },
        { l: 'Пн', v: 7, d: '2026-06-19' },
      ]}
      period="14d"
    />,
  );
  expect(screen.getByText('Мало данных для тренда')).toBeInTheDocument();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('sparse hint text is compact — not a long sentence about dynamics', () => {
  render(
    <MoodChart
      data={[{ l: 'Пн', v: 5, d: '2026-06-19' }]}
      period="14d"
    />,
  );
  expect(screen.getByText('Мало данных для тренда')).toBeInTheDocument();
  // Old long sentence must be gone
  expect(
    screen.queryByText(/пока мало данных для устойчивой динамики/i),
  ).not.toBeInTheDocument();
  expect(
    screen.queryByText(/пока есть только одна запись/i),
  ).not.toBeInTheDocument();
});

test('does not show sparse hint when 3+ real points exist', () => {
  render(
    <MoodChart
      data={[
        { l: 'Пн', v: 5, d: '2026-06-15' },
        { l: 'Пн', v: 6, d: '2026-06-16' },
        { l: 'Пн', v: 7, d: '2026-06-19' },
      ]}
      period="14d"
    />,
  );
  expect(screen.queryByText('Мало данных для тренда')).not.toBeInTheDocument();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

// ─── No empty state when data is present ─────────────────────────────────────

test('does not show empty state when at least one value is non-null', () => {
  render(
    <MoodChart
      data={[{ l: 'Пн', v: 5 }, { l: 'Вт', v: null }, { l: 'Ср', v: 7 }]}
    />,
  );
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('does not crash with single non-null point — shows chart with sparse hint', () => {
  expect(() =>
    render(
      <MoodChart data={[{ l: 'Пн', v: 5, d: '2026-06-15' }]} period="14d" />,
    ),
  ).not.toThrow();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
  expect(screen.getByText('Мало данных для тренда')).toBeInTheDocument();
});

test('null in the middle does not crash and shows chart without empty state', () => {
  expect(() =>
    render(
      <MoodChart
        data={[{ l: 'Пн', v: 7 }, { l: 'Вт', v: null }, { l: 'Ср', v: 5 }]}
      />,
    ),
  ).not.toThrow();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

// ─── X-axis label logic ───────────────────────────────────────────────────────

test('period=14d renders all 14 date labels in DD.MM format', () => {
  // Backend sends weekday in l and ISO date in d.
  // MoodChart must render DD.MM from d, ignoring l and "Сегодня".
  const data = Array.from({ length: 14 }, (_, i) => ({
    l: i === 13 ? 'Сегодня' : 'Пн',
    v: i >= 12 ? 7 : null,  // 2 real points → sparse
    d: `2026-06-${String(i + 6).padStart(2, '0')}`,
  }));
  render(<MoodChart data={data} period="14d" />);
  // First, middle, and last dates visible in DD.MM format
  expect(screen.getByText('06.06')).toBeInTheDocument();
  expect(screen.getByText('12.06')).toBeInTheDocument();
  expect(screen.getByText('19.06')).toBeInTheDocument();
  // Weekday abbreviation must NOT appear as label
  expect(screen.queryByText('Пн')).not.toBeInTheDocument();
  // "Сегодня" must NOT appear — use DD.MM instead
  expect(screen.queryByText('Сегодня')).not.toBeInTheDocument();
});

test('period=month thins labels to every 5th day in DD.MM format', () => {
  // 19-day month (June 1–19): show days 1, 5, 10, 15, 19 (today)
  const data = Array.from({ length: 19 }, (_, i) => ({
    l: String(i + 1),
    v: i >= 17 ? 5 : null,  // 2 real points → sparse
    d: `2026-06-${String(i + 1).padStart(2, '0')}`,
  }));
  render(<MoodChart data={data} period="month" />);
  // Shown: index 0 (01.06), 4 (05.06), 9 (10.06), 14 (15.06), 18=last (19.06)
  expect(screen.getByText('01.06')).toBeInTheDocument();
  expect(screen.getByText('05.06')).toBeInTheDocument();
  expect(screen.getByText('10.06')).toBeInTheDocument();
  expect(screen.getByText('19.06')).toBeInTheDocument();  // last
  // Thinned: day 2 (index 1), day 3 (index 2)
  expect(screen.queryByText('02.06')).not.toBeInTheDocument();
  expect(screen.queryByText('03.06')).not.toBeInTheDocument();
});

test('period=year renders all 12 month labels Jan–Dec including future months', () => {
  const labels = ['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек'];
  const data = labels.map((l, i) => ({
    l,
    v: i === 5 ? 7.5 : null,  // only June has data → 1 real point
    d: `2026-${String(i + 1).padStart(2, '0')}-01`,
  }));
  render(<MoodChart data={data} period="year" />);
  // All 12 months visible, including future (Июл–Дек)
  expect(screen.getByText('Янв')).toBeInTheDocument();
  expect(screen.getByText('Июн')).toBeInTheDocument();
  expect(screen.getByText('Дек')).toBeInTheDocument();
  // Sparse hint since only 1 real point
  expect(screen.getByText('Мало данных для тренда')).toBeInTheDocument();
});

// ─── Data types & Y-axis ─────────────────────────────────────────────────────

test('float mood_score 6.5 renders without crashing', () => {
  expect(() =>
    render(
      <MoodChart
        data={[
          { l: 'Май', v: 6.5, d: '2026-05-01' },
          { l: 'Июн', v: 7.0, d: '2026-06-01' },
        ]}
        period="year"
      />,
    ),
  ).not.toThrow();
  expect(screen.queryByText(/пока нет записей/i)).not.toBeInTheDocument();
});

test('Y-axis shows 1, 5, 10 and does not show 0 or old ticks 2 / 6', () => {
  // Single point to avoid conflicts; 14d period so x-axis shows DD.MM, not standalone numbers.
  render(
    <MoodChart
      data={[{ l: 'Пн', v: 7, d: '2026-06-10' }]}
      period="14d"
    />,
  );
  expect(screen.getByText('1')).toBeInTheDocument();   // Y-axis
  expect(screen.getByText('5')).toBeInTheDocument();   // Y-axis
  expect(screen.getByText('10')).toBeInTheDocument();  // Y-axis
  expect(screen.queryByText('0')).not.toBeInTheDocument();
  expect(screen.queryByText('2')).not.toBeInTheDocument();  // old tick
  expect(screen.queryByText('6')).not.toBeInTheDocument();  // old tick
});
