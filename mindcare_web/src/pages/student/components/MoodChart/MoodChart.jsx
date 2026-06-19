import styles from './MoodChart.module.css';

const W = 600;
const PAD = { l: 30, r: 20, t: 14, b: 26 };
const MIN = 1;
const MAX = 10;

function yScale(v, h) {
  return PAD.t + (h - PAD.t - PAD.b) * (1 - (v - MIN) / (MAX - MIN));
}

// Returns the label to render on the x-axis.
// 14d / month → DD.MM from the date field (e.g. "19.06"); no "Сегодня" — user wants dates.
// year        → month name from backend label ("Янв", "Фев", …).
// Falls back to item.l when date field is absent (test stubs without d).
function getDisplayLabel(item, period) {
  if (period === 'year') return item.l;
  if (item.d) {
    const [, month, day] = item.d.split('-').map(Number);
    return `${String(day).padStart(2, '0')}.${String(month).padStart(2, '0')}`;
  }
  return item.l;
}

// Controls which x-axis labels are rendered to avoid crowding.
// 14d:   show all 14 (each label is 5 chars "DD.MM", fits at ~42px step in 600px viewBox).
// month: show days 1, 5, 10, 15, 20, 25, … + last (today).
// year:  show all 12 months.
function getShowLabel(index, dataLength, period) {
  if (period === 'year') return true;
  if (period === 'month') {
    // index 0 = day 1; (index+1) % 5 === 0 = days 5, 10, 15, 20, 25, 30; last = today.
    return index === 0 || (index + 1) % 5 === 0 || index === dataLength - 1;
  }
  // 14d: show every label
  return true;
}

function formatDotTooltip(c, period) {
  if (c.v == null) return 'Записи нет';
  if (period === 'year') return `${c.l}: среднее ${c.v}/10`;
  return `${c.l}: состояние ${c.v}/10`;
}

export default function MoodChart({ data, period = '14d', height = 160 }) {
  const safeData = data || [];
  const realPointsCount = safeData.filter((d) => d.v != null).length;
  const hasNoData = safeData.length === 0 || realPointsCount === 0;
  const isSparse = !hasNoData && realPointsCount < 3;

  if (hasNoData) {
    return (
      <div className={styles.emptyState}>
        <div>Пока нет записей для построения графика.</div>
        <div className={styles.emptyStateSub}>
          Сделайте запись в дневнике, чтобы увидеть динамику.
        </div>
      </div>
    );
  }

  const h = height;
  const xStep =
    safeData.length > 1
      ? (W - PAD.l - PAD.r) / (safeData.length - 1)
      : (W - PAD.l - PAD.r) / 2;

  const coords = safeData.map((item, i) => ({
    x: PAD.l + i * xStep,
    y: item.v != null ? yScale(item.v, h) : null,
    l: getDisplayLabel(item, period),
    v: item.v,
  }));

  // Line path — gaps at null points, no fake connections.
  let linePath = '';
  let inSegment = false;
  for (const c of coords) {
    if (c.y == null) { inSegment = false; continue; }
    linePath += inSegment ? ` L${c.x},${c.y}` : `M${c.x},${c.y}`;
    inSegment = true;
  }

  const dotPoints = coords.filter((c) => c.y != null);

  return (
    <div
      className={styles.wrap}
      style={{ height }}
      role="img"
      aria-label="График динамики настроения"
    >
      <svg viewBox={`0 0 ${W} ${h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="moodAreaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8B6F47" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#8B6F47" stopOpacity="0" />
          </linearGradient>
        </defs>

        {/* Light grid lines */}
        {[2, 5, 8].map((v) => (
          <line
            key={v}
            x1={PAD.l} x2={W - PAD.r}
            y1={yScale(v, h)} y2={yScale(v, h)}
            stroke="#D8CDBF" strokeDasharray="3 4" strokeWidth="1"
          />
        ))}

        {/* Data line — skips null gaps */}
        <path
          d={linePath}
          stroke="#8B6F47" strokeWidth="2" fill="none"
          strokeLinecap="round" strokeLinejoin="round"
        />

        {/* Dots on real data points with native tooltip */}
        {dotPoints.map((c, i) => (
          <circle
            key={i}
            cx={c.x} cy={c.y} r="3.5"
            fill="#FAF7F2" stroke="#4A3728" strokeWidth="1.6"
          >
            <title>{formatDotTooltip(c, period)}</title>
          </circle>
        ))}

        {/* X-axis labels — thinned per period */}
        {coords.map((c, i) =>
          getShowLabel(i, coords.length, period) ? (
            <text
              key={i}
              x={c.x} y={h - 8}
              textAnchor="middle" fontSize="10" fill="#8A7260"
              fontFamily="Nunito, sans-serif"
            >
              {c.l}
            </text>
          ) : null,
        )}

        {/* Y-axis labels: clear 1 / 5 / 10 scale (mood score 1–10) */}
        {[1, 5, 10].map((v) => (
          <text
            key={v}
            x={PAD.l - 6} y={yScale(v, h) + 3}
            textAnchor="end" fontSize="9" fill="#8A7260"
            fontFamily="Nunito, sans-serif"
          >
            {v}
          </text>
        ))}

        {/* Compact sparse hint — overlaid top-right, no extra vertical space */}
        {isSparse && (
          <text
            x={W - PAD.r} y={PAD.t + 12}
            textAnchor="end" fontSize="9" fill="#B0A090"
            fontFamily="Nunito, sans-serif" fontStyle="italic"
          >
            Мало данных для тренда
          </text>
        )}
      </svg>
    </div>
  );
}
