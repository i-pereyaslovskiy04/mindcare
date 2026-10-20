#!/usr/bin/env node
/**
 * check-contrast.js — автотест контраста WCAG для файлов токенов тем.
 *
 * Парсит src/styles/tokens/<theme>.css, резолвит var()-цепочки
 * (coffee-light = базовый :root, темы переопределяют) и проверяет
 * заданные пары «текст/фон» по формуле относительной яркости WCAG 2.1.
 *
 * Запуск: npm run test:contrast
 * Выход 1 — если хоть одна пара ниже порога.
 *
 * Пороги (см. thresholdFor): AA 4.5 — базовый; AAA 7.0 — hc-темы и схемы ГОСТ;
 * 3.0 — только для кофейной палитры: это пары ИСХОДНОГО дизайна, доводить их
 * до AA = видимо изменить текущий сайт (нулевая визуальная регрессия).
 * Все остальные палитры (nature, classic) обязаны держать AA.
 */

const fs = require('fs');
const path = require('path');

const TOKENS_DIR = path.join(__dirname, '..', 'src', 'styles', 'tokens');
const BASE_THEME = 'coffee-light';
const THEMES = [
  'coffee-light',
  'coffee-dark',
  'nature-light',
  'nature-dark',
  'classic-light',
  'classic-dark',
  'dongu-light',
  'dongu-dark',
  'hc-light',
  'hc-dark',
];

/** В hc-темах действует AAA (7:1) и никаких унаследованных исключений. */
const AAA_MIN = 7.0;
const AA_MIN = 4.5;
const isHighContrast = (theme) => theme.startsWith('hc-');

/**
 * Пороги ниже AA (3.0 в PAIRS) — это унаследованные пары ИСХОДНОГО кофейного
 * дизайна: доводить их до 4.5 означало бы видимо изменить текущий сайт.
 * Все остальные темы (nature, classic, hc) обязаны держать минимум AA.
 */
const isLegacyPalette = (theme) => theme.startsWith('coffee-');

function thresholdFor(theme, baseMin) {
  if (isHighContrast(theme)) return AAA_MIN;
  if (isLegacyPalette(theme)) return baseMin;
  return Math.max(baseMin, AA_MIN);
}

/* [fg, bg, min, комментарий] */
const PAIRS = [
  ['text-main', 'warm-white', 4.5, 'основной текст / фон страницы'],
  ['text-main', 'cream', 4.5, 'основной текст / alt-фон секции'],
  ['text-main', 'sand', 4.5, 'основной текст / контейнер'],
  ['text-main', 'milk', 4.5, 'основной текст / контейнер milk'],
  ['text-muted', 'warm-white', 4.5, 'второстепенный текст / фон'],
  ['text-muted', 'cream', 4.5, 'второстепенный текст / alt-фон'],
  ['text-light', 'warm-white', 3.0, 'приглушённые подписи (3.0 — только coffee)'],
  ['on-surface', 'surface', 4.5, 'ролевая пара M3'],
  ['on-surface-variant', 'surface', 4.5, 'ролевая пара M3'],
  ['on-primary', 'primary', 4.5, 'текст на акцентной кнопке'],
  ['on-secondary', 'secondary', 4.5, 'текст на secondary'],
  ['milk', 'espresso', 4.5, 'Button.primary: milk на espresso'],
  ['text-on-dark', 'espresso', 4.5, 'текст на тёмных карточках'],
  ['error', 'error-bg', 4.5, 'текст ошибки на её фоне'],
  ['on-error', 'error', 4.5, 'текст на error-фоне'],
  ['success', 'success-bg', 3.0, 'success-badge (3.0 — только coffee)'],
  ['warning-text', 'warning-bg', 4.5, 'warning-плашка'],
  ['info-text', 'info-bg', 4.5, 'info-badge'],
  ['tag-text', 'tag-bg', 4.5, 'тег контента'],
  ['code-text', 'code-bg', 4.5, 'блок кода'],
  ['warm-white', 'danger', 4.5, 'Button.danger: warm-white на danger'],
  ['coffee', 'warm-white', 3.0, 'акцент/крупный текст (3.0 — только coffee)'],
  ['hero-fg', 'hero-bg', 4.5, 'заголовок героя на подложке'],
  ['hero-muted', 'hero-bg', 4.5, 'подзаголовок героя на подложке'],
  ['hero-accent', 'hero-bg', 3.0, 'акцент героя (3.0 — только coffee)'],
];

function parseVars(rawCss) {
  const css = rawCss.replace(/\/\*[\s\S]*?\*\//g, ''); // комментарии могут упоминать var()
  const vars = {};
  for (const [, name, value] of css.matchAll(/--([\w-]+)\s*:\s*([^;]+);/g)) {
    vars[name] = value.trim();
  }
  return vars;
}

function resolveValue(vars, value, depth = 0) {
  if (depth > 10) throw new Error(`Циклическая var()-ссылка: ${value}`);
  const m = value.match(/^var\(--([\w-]+)\)$/);
  if (!m) return value;
  const next = vars[m[1]];
  if (next === undefined) throw new Error(`Не найден токен --${m[1]}`);
  return resolveValue(vars, next, depth + 1);
}

function hexToRgb(value) {
  const m = value.match(/^#([0-9a-fA-F]{6})$/);
  if (!m) return null;
  const n = parseInt(m[1], 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

function luminance([r, g, b]) {
  const lin = (c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  };
  return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b);
}

function contrast(rgb1, rgb2) {
  const l1 = luminance(rgb1);
  const l2 = luminance(rgb2);
  const [hi, lo] = l1 >= l2 ? [l1, l2] : [l2, l1];
  return (hi + 0.05) / (lo + 0.05);
}

function loadTheme(name) {
  const css = fs.readFileSync(path.join(TOKENS_DIR, `${name}.css`), 'utf8');
  return parseVars(css);
}

const baseVars = loadTheme(BASE_THEME);
let failures = 0;
let checks = 0;

for (const theme of THEMES) {
  const vars = theme === BASE_THEME ? baseVars : { ...baseVars, ...loadTheme(theme) };
  const label = isHighContrast(theme)
    ? ' (AAA 7:1)'
    : isLegacyPalette(theme)
      ? ' (AA + унаследованные исключения)'
      : ' (AA 4.5:1)';
  console.log(`\n=== ${theme}${label} ===`);
  for (const [fg, bg, baseMin, note] of PAIRS) {
    const min = thresholdFor(theme, baseMin);
    let line;
    try {
      const fgHex = resolveValue(vars, vars[fg] !== undefined ? `var(--${fg})` : `--${fg}?`);
      const bgHex = resolveValue(vars, `var(--${bg})`);
      const fgRgb = hexToRgb(fgHex);
      const bgRgb = hexToRgb(bgHex);
      if (!fgRgb || !bgRgb) {
        throw new Error(`не hex-цвет (fg=${fgHex}, bg=${bgHex})`);
      }
      const ratio = contrast(fgRgb, bgRgb);
      checks += 1;
      const ok = ratio >= min;
      if (!ok) failures += 1;
      line = `${ok ? '  ok ' : 'FAIL '} --${fg} на --${bg}: ${ratio.toFixed(2)} (мин ${min}) — ${note}`;
    } catch (err) {
      failures += 1;
      line = `FAIL --${fg} на --${bg}: ${err.message}`;
    }
    console.log(line);
  }
}

/* ── Схемы режима для слабовидящих (ГОСТ Р 52872-2019) ──────────────────
   В a11y.css все токены сводятся к паре --a11y-bg / --a11y-fg, поэтому
   достаточно проверить сами схемы: текст на фоне, порог AAA. */

const a11yCss = fs.readFileSync(path.join(TOKENS_DIR, 'a11y.css'), 'utf8')
  .replace(/\/\*[\s\S]*?\*\//g, '');

const A11Y_SCHEME_NAMES = {
  bw: 'Ч/Б',
  wb: 'Б/Ч',
  blue: 'синяя',
  beige: 'бежевая',
};

console.log('\n=== a11y / ГОСТ Р 52872-2019 (AAA 7:1) ===');
for (const [key, title] of Object.entries(A11Y_SCHEME_NAMES)) {
  const block = a11yCss.match(
    new RegExp(`data-a11y-scheme='${key}'\\][^{]*\\{([^}]*)\\}`)
  );
  let line;
  try {
    if (!block) throw new Error('схема не найдена в a11y.css');
    const vars = parseVars(block[1]);
    const bg = hexToRgb(vars['a11y-bg']);
    const fg = hexToRgb(vars['a11y-fg']);
    if (!bg || !fg) throw new Error('не hex-цвет схемы');
    const ratio = contrast(fg, bg);
    checks += 1;
    const ok = ratio >= AAA_MIN;
    if (!ok) failures += 1;
    line = `${ok ? '  ok ' : 'FAIL '} схема «${title}»: ${ratio.toFixed(2)} (мин ${AAA_MIN})`;
  } catch (err) {
    failures += 1;
    line = `FAIL схема «${title}»: ${err.message}`;
  }
  console.log(line);
}

console.log(`\nПроверок: ${checks}, нарушений: ${failures}`);
if (failures > 0) {
  console.error('Контраст ниже порога — исправьте значения токенов.');
  process.exit(1);
}
