import { useId, useState } from 'react';
import Tag from '../Tag/Tag';
import styles from './TagList.module.css';

/**
 * Набор display-only меток (Tag) с переносом строк. Показывает первые
 * maxVisible; остальные — за кнопкой «+N», которая раскрывает полный список
 * на месте (мышь, клавиатура, touch) и сворачивает его обратно.
 *
 *   items      — [{ key, label }]: что и в каком порядке показать (решает фича);
 *   maxVisible — сколько меток видно до «+N» (по умолчанию все);
 *   label      — имя набора: aria-label списка («Темы»);
 *   variant    — вариант Tag (по умолчанию admin).
 *
 * Длинная метка не обрезается, а переносится внутри своей «таблетки» — её
 * полное значение всегда видно. Пустой набор — ничего не рендерит (заглушку
 * вроде «—» показывает фича). Данные не загружает и не фильтрует.
 */
export default function TagList({ items, maxVisible = Infinity, label, variant = 'admin' }) {
  const [expanded, setExpanded] = useState(false);
  const listId = useId();
  if (!items || items.length === 0) return null;

  const hiddenCount = Math.max(0, items.length - maxVisible);
  const visible = expanded || hiddenCount === 0 ? items : items.slice(0, maxVisible);

  return (
    <div className={styles.root}>
      <ul id={listId} className={styles.list} aria-label={label}>
        {visible.map((item) => (
          <li key={item.key} className={styles.item}>
            <Tag variant={variant} className={styles.tag}>{item.label}</Tag>
          </li>
        ))}
      </ul>
      {hiddenCount > 0 && (
        <button
          type="button"
          className={styles.toggle}
          aria-expanded={expanded}
          aria-controls={listId}
          aria-label={expanded ? undefined : `+${hiddenCount}: показать все, всего ${items.length}`}
          onClick={() => setExpanded((v) => !v)}
        >
          {expanded ? 'Свернуть' : `+${hiddenCount}`}
        </button>
      )}
    </div>
  );
}
