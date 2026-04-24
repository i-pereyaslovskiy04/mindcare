// Shared SVG icons used across multiple components.
// Local-only icons stay in their component files.

export const TelegramIcon = ({ width = 14, height = 14, color = '#2AABEE' }) => (
  <svg width={width} height={height} viewBox="0 0 14 14" fill="none">
    <path
      d="M1 7L12 1.5l-2.8 10L5.5 9 2.5 11l1-4.5L1 7z"
      stroke={color}
      strokeWidth="1.2"
      fill="none"
      strokeLinejoin="round"
    />
  </svg>
);

export const VKIcon = ({ width = 14, height = 14, color = '#4680C2' }) => (
  <svg width={width} height={height} viewBox="0 0 14 14" fill="none">
    <path
      d="M1 3.5h3l3.5 5 3.5-5H14L7 11 1 3.5z"
      stroke={color}
      strokeWidth="1.1"
      fill="none"
      strokeLinejoin="round"
    />
  </svg>
);

export const YandexIcon = ({ width = 14, height = 14, color = '#FC3F1D' }) => (
  <svg width={width} height={height} viewBox="0 0 14 14" fill="none">
    <circle cx="7" cy="7" r="5.5" stroke={color} strokeWidth="1.2" fill="none" />
    <path
      d="M7 3.5v7M4.5 5.5L7 3.5l2.5 2"
      stroke={color}
      strokeWidth="1.1"
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);

export const ArrowRightIcon = ({ width = 13, height = 13, strokeWidth = 1.4 }) => (
  <svg width={width} height={height} viewBox="0 0 13 13" fill="none">
    <path
      d="M2 6.5h9M7.5 3l3 3.5-3 3"
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
    />
  </svg>
);
