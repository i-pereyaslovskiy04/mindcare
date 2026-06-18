import styles from './DiaryEntryForm.module.css';

export default function DiaryEntryForm({
  emotions = [],
  text = '',
  onTextChange,
  selectedEmotions = [],
  onEmotionToggle,
  moodSelected,
  saving,
  showSaved,
  saveError,
  onSave,
}) {
  function handleSubmit(e) {
    e.preventDefault();
    if (!moodSelected || saving) return;
    onSave();
  }

  const btnDisabled = !moodSelected || saving;

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      <h2 className={styles.title}>Запись в дневнике</h2>

      {!moodSelected && (
        <p className={styles.moodHint}>
          Выберите настроение на шкале выше, чтобы сохранить запись.
        </p>
      )}

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Что происходит?</label>
        <textarea
          className={styles.textarea}
          rows={5}
          placeholder="Опишите своё состояние, события дня или мысли…"
          value={text}
          onChange={(e) => onTextChange(e.target.value)}
          disabled={saving}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Эмоции</label>
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

      {saveError && <p className={styles.saveError}>{saveError}</p>}

      <button
        type="submit"
        className={showSaved ? styles.btnSaved : styles.btnSave}
        disabled={btnDisabled}
      >
        {showSaved ? '✓ Сохранено' : saving ? 'Сохранение…' : 'Сохранить запись'}
      </button>
    </form>
  );
}
