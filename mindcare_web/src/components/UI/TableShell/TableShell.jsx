import styles from './TableShell.module.css';

/**
 * Оболочка семантической таблицы: карточка-контейнер, `<table>`, подпись и
 * базовая геометрия `th`/`td`. Строки, колонки, состояния (загрузка, пусто,
 * ошибка) и действия задаёт фича — shell о данных ничего не знает.
 *
 * `caption` — доступное имя таблицы; по умолчанию скрыт визуально (заголовок
 * страницы уже виден), `captionVisible` показывает его. Остальные props
 * (`aria-*`, `id`…) уходят на `<table>`.
 *
 * Горизонтальный скролл контейнера — только страховка: фича сама держит
 * таблицу в ширине колонки (переносы, компактное представление на узкой
 * ширине).
 */
export default function TableShell({
  caption,
  captionVisible = false,
  className,
  tableClassName,
  children,
  ...tableProps
}) {
  return (
    <div className={[styles.shell, className].filter(Boolean).join(' ')}>
      <table className={[styles.table, tableClassName].filter(Boolean).join(' ')} {...tableProps}>
        {caption && (
          <caption className={captionVisible ? styles.caption : 'visually-hidden'}>
            {caption}
          </caption>
        )}
        {children}
      </table>
    </div>
  );
}
