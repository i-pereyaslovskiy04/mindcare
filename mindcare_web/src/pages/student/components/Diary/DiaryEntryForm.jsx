import { useState } from 'react';
import styles from './DiaryEntryForm.module.css';

export default function DiaryEntryForm({
  emotions = [],
  text = '',
  onTextChange,
  selectedEmotions = [],
  onEmotionToggle,
  moodSelected,
  isExistingEntry = false,
  saving,
  showSaved,
  saveError,
  onSave,
}) {
  const [showDetails, setShowDetails] = useState(() => text !== '');

  function handleSubmit(e) {
    e.preventDefault();
    if (!moodSelected || saving) return;
    onSave();
  }

  const btnLabel = showSaved
    ? '✓ Сохранено'
    : saving
    ? 'Сохранение…'
    : isExistingEntry
    ? 'Обновить запись'
    : 'Сохранить отметку';

  const btnDisabled = !moodSelected || saving;

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      {!moodSelected && (
        <p className={styles.moodHint}>
          Выберите состояние на шкале выше, чтобы сохранить отметку.
        </p>
      )}

      <div className={styles.field}>
        <div className={styles.fieldLabelRow}>
          <span className={styles.fieldLabel}>Что вы чувствуете?</span>
          <span className={styles.fieldHint}>Можно выбрать несколько.</span>
        </div>
        <div className={styles.chips}>
          {emotions.map((em) => (
            <button
              key={em.key}
              type="button"
              aria-pressed={selectedEmotions.includes(em.key)}
              className={selectedEmotions.includes(em.key) ? styles.chipActive : styles.chip}
              onClick={() => onEmotionToggle(em.key)}
              disabled={saving}
            >
              {em.label}
            </button>
          ))}
        </div>
      </div>

      <div className={styles.detailsSection}>
        <button
          type="button"
          className={styles.detailsToggle}
          onClick={() => setShowDetails((v) => !v)}
          disabled={saving}
        >
          {showDetails ? 'Скрыть подробности' : '+ Добавить подробности'}
        </button>
        {showDetails && (
          <div className={styles.detailsContent}>
            <textarea
              className={styles.textarea}
              rows={4}
              placeholder="Что повлияло на состояние? Что хочется обсудить с психологом?"
              value={text}
              onChange={(e) => onTextChange(e.target.value)}
              disabled={saving}
            />
          </div>
        )}
      </div>

      {saveError && <p className={styles.saveError}>{saveError}</p>}

      <button
        type="submit"
        className={showSaved ? styles.btnSaved : styles.btnSave}
        disabled={btnDisabled}
      >
        {btnLabel}
      </button>
    </form>
  );
}
