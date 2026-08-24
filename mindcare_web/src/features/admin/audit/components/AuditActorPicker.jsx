import { useEffect, useId, useRef, useState } from 'react';
import Badge from '../../../../components/UI/Badge/Badge';
import Button from '../../../../components/UI/Button/Button';
import { MIN_TERM_LENGTH, useAuditActorSearch } from '../hooks/useAuditActorSearch';
import styles from './AuditActorPicker.module.css';

/**
 * Выбор участника для точного фильтра `actor_uuid`.
 *
 * Feature-specific combobox: shared `Select` работает по статическому списку
 * опций, `MultiSelect` фильтрует локально и вешает `role="combobox"` на `div`;
 * серверного асинхронного поиска нет ни у одного shared-контрола.
 *
 * Компонент ПОЛНОСТЬЮ controlled: выбранный участник хранится в
 * `useAdminAuditLogs`, сюда приходит через `value`. Собственного состояния
 * выбора здесь нет — иначе после сброса фильтров подпись осталась бы висеть,
 * хотя `actor_uuid` уже снят. `resetKey` — сигнал очистить строку поиска и
 * выдачу.
 *
 * Наружу уходит только UUID: ни введённый текст, ни имя, ни email в запрос
 * журнала не попадают.
 */
export default function AuditActorPicker({ value, resetKey, onSelect, onClear }) {
  const { term, setTerm, results, loading, error, reset } = useAuditActorSearch();
  const [isOpen, setIsOpen] = useState(false);
  const [activeIndex, setActiveIndex] = useState(-1);

  const inputRef = useRef(null);
  const prevResetKey = useRef(resetKey);

  const baseId = useId();
  const inputId = `${baseId}-actor-input`;
  const listboxId = `${baseId}-actor-listbox`;
  const optionId = (index) => `${baseId}-actor-option-${index}`;

  // Внешний сброс (кнопка «Сбросить фильтры» или «Сбросить пользователя»)
  // очищает строку поиска и выдачу и возвращает фокус в поле.
  useEffect(() => {
    if (prevResetKey.current === resetKey) return;
    prevResetKey.current = resetKey;
    reset();
    setIsOpen(false);
    setActiveIndex(-1);
    inputRef.current?.focus();
  }, [resetKey, reset]);

  const choose = (actor) => {
    onSelect(actor);
    reset();
    setIsOpen(false);
    setActiveIndex(-1);
  };

  const handleKeyDown = (event) => {
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault();
        setIsOpen(true);
        setActiveIndex((i) => Math.min(i + 1, results.length - 1));
        break;
      case 'ArrowUp':
        event.preventDefault();
        setIsOpen(true);
        setActiveIndex((i) => Math.max(i - 1, 0));
        break;
      case 'Enter':
        if (isOpen && activeIndex >= 0 && activeIndex < results.length) {
          event.preventDefault();
          choose(results[activeIndex]);
        }
        break;
      case 'Escape':
        if (isOpen) {
          event.preventDefault();
          event.stopPropagation();
          setIsOpen(false);
          setActiveIndex(-1);
        }
        break;
      default:
        break;
    }
  };

  const showList = isOpen && term.trim().length >= MIN_TERM_LENGTH;

  return (
    <div className={styles.wrap}>
      <label className={styles.label} htmlFor={inputId}>Участник</label>

      <input
        ref={inputRef}
        id={inputId}
        type="text"
        className={styles.input}
        role="combobox"
        autoComplete="off"
        aria-expanded={showList}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={
          showList && activeIndex >= 0 ? optionId(activeIndex) : undefined
        }
        placeholder="ФИО или email"
        value={term}
        onChange={(event) => {
          setTerm(event.target.value);
          setIsOpen(true);
          setActiveIndex(-1);
        }}
        onKeyDown={handleKeyDown}
        onBlur={() => window.setTimeout(() => setIsOpen(false), 120)}
      />

      {showList && (
        <ul id={listboxId} role="listbox" aria-label="Найденные пользователи" className={styles.listbox}>
          {loading && <li className={styles.status} role="presentation">Поиск…</li>}

          {!loading && error && (
            <li className={styles.statusError} role="presentation">{error}</li>
          )}

          {!loading && !error && results.length === 0 && (
            <li className={styles.status} role="presentation">Никого не найдено</li>
          )}

          {!loading && !error && results.map((actor, index) => (
            <li
              key={actor.uuid}
              id={optionId(index)}
              role="option"
              aria-selected={index === activeIndex}
              className={`${styles.option} ${index === activeIndex ? styles.optionActive : ''}`}
              onMouseDown={(event) => { event.preventDefault(); choose(actor); }}
              onMouseEnter={() => setActiveIndex(index)}
            >
              <span className={styles.optionName}>{actor.fullName}</span>
              <span className={styles.optionEmail}>{actor.emailMasked}</span>
              {actor.isDeleted && <Badge tone="neutral">Удалён</Badge>}
            </li>
          ))}
        </ul>
      )}

      {value && (
        <div className={styles.selected}>
          <span className={styles.selectedName}>{value.fullName}</span>
          <span className={styles.selectedEmail}>{value.emailMasked}</span>
          {value.isDeleted && <Badge tone="neutral">Удалён</Badge>}
          <Button type="button" variant="secondary" size="sm" onClick={onClear}>
            Сбросить пользователя
          </Button>
        </div>
      )}
    </div>
  );
}
