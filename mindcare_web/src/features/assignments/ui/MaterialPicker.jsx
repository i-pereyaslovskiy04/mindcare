import { useEffect, useId, useRef, useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import TextField from '../../../components/UI/TextField/TextField';
import { useMaterialsLibrary } from '../../materials/hooks/useMaterialsLibrary';
import styles from './MaterialPicker.module.css';

const PICKER_PAGE_SIZE = 8;

/**
 * Выбор опубликованного материала для задания — встроенная панель формы (не
 * отдельное модальное окно: форма может сама жить в модальном окне, а
 * вложенные модалки закрывались бы одним Escape). Источник — та же публичная
 * библиотека (/api/articles), поиск серверный с debounce 300 мс, «Показать ещё».
 * При открытии фокус — в поле поиска; «Скрыть» и Escape закрывают панель и
 * возвращают фокус на кнопку, которая её открыла (через onClose вызывающего).
 */
export default function MaterialPicker({ onClose, onSelect }) {
  const library = useMaterialsLibrary({ pageSize: PICKER_PAGE_SIZE });
  const [input, setInput] = useState('');
  const debounceRef = useRef(null);
  const searchRef = useRef(null);
  const headingId = useId();
  const { setQuery } = library;

  useEffect(() => {
    searchRef.current?.focus();
    return () => clearTimeout(debounceRef.current);
  }, []);

  function handleInput(e) {
    const value = e.target.value;
    setInput(value);
    clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => setQuery(value), 300);
  }

  function handleKeyDown(e) {
    if (e.key === 'Escape') {
      // Не даём Escape закрыть внешнее модальное окно — только панель.
      e.stopPropagation();
      e.nativeEvent?.stopImmediatePropagation?.();
      onClose();
    }
  }

  return (
    <section className={styles.panel} aria-labelledby={headingId} onKeyDown={handleKeyDown}>
      <div className={styles.head}>
        <h5 id={headingId} className={styles.title}>Материал из библиотеки</h5>
        <Button type="button" variant="ghost" size="sm" onClick={onClose}>Скрыть</Button>
      </div>
      <TextField
        ref={searchRef}
        label="Поиск по названию"
        type="search"
        value={input}
        onChange={handleInput}
        autoComplete="off"
      />

      <div className={styles.results} aria-live="polite" aria-busy={library.loading}>
        {library.loading && library.items.length === 0 && (
          <p className={styles.state}>Загружаем материалы…</p>
        )}
        {library.error && (
          <div className={styles.errorBox} role="alert">
            <p className={styles.errorText}>Не удалось загрузить материалы.</p>
            <Button type="button" size="sm" variant="secondary" onClick={library.refetch}>
              Повторить
            </Button>
          </div>
        )}
        {!library.loading && !library.error && library.items.length === 0 && (
          <p className={styles.state}>Ничего не найдено.</p>
        )}
        {library.items.length > 0 && (
          <ul className={styles.list}>
            {library.items.map(item => (
              <li key={item.id} className={styles.row}>
                <div className={styles.info}>
                  <span className={styles.itemTitle}>{item.title}</span>
                  {item.category && <span className={styles.itemMeta}>{item.category}</span>}
                </div>
                <Button
                  type="button"
                  size="sm"
                  variant="secondary"
                  onClick={() => onSelect({ uuid: item.id, title: item.title })}
                  aria-label={`Выбрать «${item.title}»`}
                >
                  Выбрать
                </Button>
              </li>
            ))}
          </ul>
        )}
        {library.hasMore && !library.loading && !library.error && (
          <div className={styles.more}>
            <Button type="button" variant="ghost" size="sm" onClick={library.loadMore}>
              Показать ещё
            </Button>
          </div>
        )}
      </div>
    </section>
  );
}
