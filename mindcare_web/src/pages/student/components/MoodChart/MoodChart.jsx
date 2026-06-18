import styles from './MoodChart.module.css';

const W = 600;
const PAD = { l: 30, r: 20, t: 14, b: 26 };
const MIN = 1;
const MAX = 10;

function yScale(v, h) {
  return PAD.t + (h - PAD.t - PAD.b) * (1 - (v - MIN) / (MAX - MIN));
}

export default function MoodChart({ data, height = 160 }) {
  if (!data || data.length === 0) {
    return (
      <div className={styles.emptyState}>
        Пока нет записей для построения графика.
      </div>
    );
  }

  const h = height;
  const xStep = data.length > 1
    ? (W - PAD.l - PAD.r) / (data.length - 1)
    : (W - PAD.l - PAD.r) / 2;

  const coords = data.map((d, i) => ({
    x: PAD.l + i * xStep,
    y: d.v != null ? yScale(d.v, h) : null,
    l: d.l,
  }));

  // Segmented line path — skips null points
  let linePath = '';
  let inSegment = false;
  for (const c of coords) {
    if (c.y == null) {
      inSegment = false;
      continue;
    }
    linePath += inSegment ? ` L${c.x},${c.y}` : `M${c.x},${c.y}`;
    inSegment = true;
  }

  const hasData = linePath.length > 0;

  if (!hasData) {
    return (
      <div className={styles.emptyState}>
        Пока нет записей для построения графика.
      </div>
    );
  }

  const dotPoints = coords.filter((c) => c.y != null);

  return (
    <div className={styles.wrap} style={{ height }}>
      <svg viewBox={`0 0 ${W} ${h}`} preserveAspectRatio="none">
        <defs>
          <linearGradient id="moodAreaFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#8B6F47" stopOpacity="0.22" />
            <stop offset="100%" stopColor="#8B6F47" stopOpacity="0" />
          </linearGradient>
        </defs>

        {[3, 5, 7, 9].map((v) => (
          <line
            key={v}
            x1={PAD.l} x2={W - PAD.r}
            y1={yScale(v, h)} y2={yScale(v, h)}
            stroke="#D8CDBF"
            strokeDasharray="3 4"
            strokeWidth="1"
          />
        ))}

        <path
          d={linePath}
          stroke="#8B6F47"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {dotPoints.map((c, i) => (
          <circle
            key={i}
            cx={c.x} cy={c.y}
            r="3.5"
            fill="#FAF7F2"
            stroke="#4A3728"
            strokeWidth="1.6"
          />
        ))}

        {data.map((d, i) => (
          <text
            key={i}
            x={PAD.l + i * xStep}
            y={h - 8}
            textAnchor="middle"
            fontSize="10"
            fill="#8A7260"
            fontFamily="Nunito, sans-serif"
          >
            {d.l}
          </text>
        ))}

        {[2, 6, 10].map((v) => (
          <text
            key={v}
            x={PAD.l - 6}
            y={yScale(v, h) + 3}
            textAnchor="end"
            fontSize="9"
            fill="#8A7260"
            fontFamily="Nunito, sans-serif"
          >
            {v}
          </text>
        ))}
      </svg>
    </div>
  );
}
