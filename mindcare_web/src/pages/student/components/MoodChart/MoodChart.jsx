import styles from './MoodChart.module.css';

const W = 600;
const PAD = { l: 30, r: 20, t: 14, b: 26 };
const MIN = 1;
const MAX = 10;

function yScale(v, h) {
  return PAD.t + (h - PAD.t - PAD.b) * (1 - (v - MIN) / (MAX - MIN));
}

export default function MoodChart({ data, height = 160 }) {
  const h = height;
  const xStep = (W - PAD.l - PAD.r) / (data.length - 1);
  const points = data.map((d, i) => [PAD.l + i * xStep, yScale(d.v, h)]);

  const linePath = points
    .map((p, i) => (i === 0 ? `M${p[0]},${p[1]}` : `L${p[0]},${p[1]}`))
    .join(' ');

  const areaPath = `${linePath} L${points[points.length - 1][0]},${h - PAD.b} L${points[0][0]},${h - PAD.b} Z`;

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

        <path d={areaPath} fill="url(#moodAreaFill)" />
        <path
          d={linePath}
          stroke="#8B6F47"
          strokeWidth="2"
          fill="none"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {points.map((p, i) => (
          <circle
            key={i}
            cx={p[0]} cy={p[1]}
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
