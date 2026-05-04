import { useState } from 'react';
import styles from './DiaryEntryForm.module.css';

const EMOTIONS = [
  'спокойно', 'радостно', 'тревожно', 'грустно', 'устало',
  'злобно', 'вдохновлённо', 'растерянно', 'легко', 'сосредоточенно',
];

export default function DiaryEntryForm({ onSave }) {
  const [note, setNote] = useState('');
  const [selected, setSelected] = useState([]);
  const [saved, setSaved] = useState(false);

  function toggleEmotion(em) {
    setSelected((prev) =>
      prev.includes(em) ? prev.filter((e) => e !== em) : [...prev, em]
    );
  }

  function handleSubmit(e) {
    e.preventDefault();
    onSave({ note: note.trim(), emotions: selected });
    setNote('');
    setSelected([]);
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  }

  return (
    <form className={styles.card} onSubmit={handleSubmit}>
      <h2 className={styles.title}>Запись в дневнике</h2>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Что происходит?</label>
        <textarea
          className={styles.textarea}
          rows={5}
          placeholder="Опишите своё состояние, события дня или мысли…"
          value={note}
          onChange={(e) => setNote(e.target.value)}
        />
      </div>

      <div className={styles.field}>
        <label className={styles.fieldLabel}>Эмоции</label>
        <div className={styles.chips}>
          {EMOTIONS.map((em) => (
            <button
              key={em}
              type="button"
              className={selected.includes(em) ? styles.chipActive : styles.chip}
              onClick={() => toggleEmotion(em)}
            >
              {em}
            </button>
          ))}
        </div>
      </div>

      <button type="submit" className={saved ? styles.btnSaved : styles.btnSave}>
        {saved ? '✓ Сохранено' : 'Сохранить запись'}
      </button>
    </form>
  );
}
