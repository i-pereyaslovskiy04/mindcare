/**
 * A11yPanel — панель настроек режима для слабовидящих (ГОСТ Р 52872-2019).
 * Закреплена под шапкой, видна только когда режим включён.
 *
 * Все контролы — кнопки с aria-pressed (выбор из набора), полностью
 * доступны с клавиатуры. Feature-specific UI: shared FilterChip/Toggle не
 * подходят — в режиме a11y запрещены брендовые цвета и декоративные стили,
 * панель обязана рендериться в схеме ГОСТ (фон/текст из data-a11y-scheme).
 */

import { useContext } from 'react';
import { A11yContext } from './A11yContext';
import styles from './A11yPanel.module.css';

const FONT_SCALE_OPTIONS = [
  { value: 1, short: 'A', label: 'Обычный размер шрифта (100%)' },
  { value: 1.5, short: 'A+', label: 'Крупный размер шрифта (150%)' },
  { value: 2, short: 'A++', label: 'Очень крупный размер шрифта (200%)' },
];

const SCHEME_OPTIONS = [
  { value: 'bw', short: 'Ч/Б', label: 'Чёрным по белому' },
  { value: 'wb', short: 'Б/Ч', label: 'Белым по чёрному' },
  { value: 'blue', short: 'Синяя', label: 'Тёмно-синим по голубому' },
  { value: 'beige', short: 'Бежевая', label: 'Коричневым по бежевому' },
];

const SPACING_OPTIONS = [
  { value: 'normal', short: 'Обычный', label: 'Обычный межбуквенный интервал' },
  { value: 'medium', short: 'Средний', label: 'Средний межбуквенный интервал' },
  { value: 'large', short: 'Большой', label: 'Большой межбуквенный интервал' },
];

const LEADING_OPTIONS = [
  { value: '1.5', short: '1.5', label: 'Межстрочный интервал 1.5' },
  { value: '2', short: '2', label: 'Межстрочный интервал 2' },
];

const FONT_OPTIONS = [
  { value: 'sans', short: 'Без засечек', label: 'Шрифт без засечек' },
  { value: 'serif', short: 'С засечками', label: 'Шрифт с засечками' },
];

const IMAGE_OPTIONS = [
  { value: 'show', short: 'Показать', label: 'Показывать изображения' },
  { value: 'hide', short: 'Скрыть', label: 'Скрыть изображения (останется описание)' },
  { value: 'gray', short: 'Ч/Б', label: 'Изображения в оттенках серого' },
];

function Group({ legend, options, current, onSelect }) {
  return (
    <div className={styles.group} role="group" aria-label={legend}>
      <span className={styles.legend}>{legend}</span>
      <div className={styles.options}>
        {options.map(({ value, short, label }) => (
          <button
            key={String(value)}
            type="button"
            className={`${styles.option} ${current === value ? styles.optionActive : ''}`}
            aria-pressed={current === value}
            aria-label={label}
            title={label}
            onClick={() => onSelect(value)}
          >
            {short}
          </button>
        ))}
      </div>
    </div>
  );
}

export default function A11yPanel() {
  const ctx = useContext(A11yContext);
  if (!ctx || !ctx.settings.enabled) return null;

  const { settings, update, reset } = ctx;

  return (
    <section className={styles.panel} aria-label="Настройки версии для слабовидящих">
      <Group
        legend="Размер шрифта"
        options={FONT_SCALE_OPTIONS}
        current={settings.fontScale}
        onSelect={(fontScale) => update({ fontScale })}
      />
      <Group
        legend="Цветовая схема"
        options={SCHEME_OPTIONS}
        current={settings.scheme}
        onSelect={(scheme) => update({ scheme })}
      />
      <Group
        legend="Межбуквенный интервал"
        options={SPACING_OPTIONS}
        current={settings.spacing}
        onSelect={(spacing) => update({ spacing })}
      />
      <Group
        legend="Межстрочный интервал"
        options={LEADING_OPTIONS}
        current={settings.leading}
        onSelect={(leading) => update({ leading })}
      />
      <Group
        legend="Шрифт"
        options={FONT_OPTIONS}
        current={settings.font}
        onSelect={(font) => update({ font })}
      />
      <Group
        legend="Изображения"
        options={IMAGE_OPTIONS}
        current={settings.images}
        onSelect={(images) => update({ images })}
      />
      <button type="button" className={styles.reset} onClick={reset}>
        Сбросить настройки
      </button>
    </section>
  );
}
