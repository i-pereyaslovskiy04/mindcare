import { useState, useEffect } from 'react';
import * as diaryApi from '../../../../api/diary.api';
import styles from './DiaryEntryItem.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

function formatDate(iso) {
  // Use local Date constructor (not ISO string) to avoid UTC→local timezone shift
  const [year, month, day] = iso.split('-').map(Number);
  return new Date(year, month - 1, day).toLocaleDateString('ru-RU', {
    weekday: 'short',
    day: 'numeric',
    month: 'short',
  });
}

function getMoodColor(v) {
  if (v <= 3) return 'var(--error)';
  if (v <= 5) return '#D4891A';
  if (v <= 7) return '#8B6F47';
  return 'var(--success)';
}

function getEmotionLabel(key, catalog) {
  const found = catalog.find((e) => e.key === key);
  return found ? found.label : key;
}

export default function DiaryEntryItem({ entry, emotionCatalog = [], onUpdate, onDelete }) {
  const { uuid, entry_date, mood_score, emotions, entry_text } = entry;

  // Edit state
  const [editMode, setEditMode] = useState(false);
  const [editMood, setEditMood] = useState(mood_score);
  const [editText, setEditText] = useState(entry_text ?? '');
  const [editEmotions, setEditEmotions] = useState(emotions ?? []);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // Delete state
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState(null);

  // Action menu (kebab) state — shared between desktop and mobile
  const [menuOpen, setMenuOpen] = useState(false);

  useEffect(() => {
    if (!menuOpen) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') setMenuOpen(false);
    }
    document.addEventListener('keydown', onKeyDown);
    return () => document.removeEventListener('keydown', onKeyDown);
  }, [menuOpen]);

  function openEdit() {
    setEditMood(mood_score);
    setEditText(entry_text ?? '');
    setEditEmotions(emotions ?? []);
    setSaveError(null);
    setConfirmDelete(false);
    setEditMode(true);
  }

  function cancelEdit() {
    setEditMode(false);
    setSaveError(null);
  }

  async function handleSaveEdit() {
    if (saving) return;
    setSaving(true);
    setSaveError(null);
    try {
      const updated = await diaryApi.updateDiaryEntry(uuid, {
        mood_score: editMood,
        entry_text: editText,
        emotions: editEmotions,
      });
      setEditMode(false);
      onUpdate?.(updated);
    } catch (err) {
      setSaveError(err.message || 'Не удалось сохранить запись. Попробуйте ещё раз.');
    } finally {
      setSaving(false);
    }
  }

  function toggleEditEmotion(key) {
    setEditEmotions((prev) =>
      prev.includes(key) ? prev.filter((k) => k !== key) : [...prev, key]
    );
  }

  function openDeleteConfirm() {
    setConfirmDelete(true);
    setDeleteError(null);
    setEditMode(false);
  }

  function cancelDelete() {
    setConfirmDelete(false);
    setDeleteError(null);
  }

  async function handleConfirmDelete() {
    if (deleting) return;
    setDeleting(true);
    setDeleteError(null);
    try {
      await diaryApi.deleteDiaryEntry(uuid);
      onDelete?.(uuid);
    } catch (err) {
      setDeleteError(err.message || 'Не удалось удалить запись. Попробуйте ещё раз.');
      setDeleting(false);
    }
  }

  // ── Edit mode ────────────────────────────────────────────────────────────────
  if (editMode) {
    return (
      <div className={styles.item}>
        <div className={styles.editHeader}>
          <span className={styles.date}>{formatDate(entry_date)}</span>
          <span className={styles.editLabel}>Редактирование</span>
        </div>

        <div className={styles.editMoodRow}>
          <span className={styles.editFieldLabel}>Настроение: {editMood}/10</span>
          <input
            type="range"
            min="1"
            max="10"
            value={editMood}
            onChange={(e) => setEditMood(Number(e.target.value))}
            className={styles.editMoodSlider}
            disabled={saving}
            aria-label="Настроение"
          />
        </div>

        {emotionCatalog.length > 0 && (
          <div className={styles.editEmotionRow}>
            {emotionCatalog.map((em) => (
              <button
                key={em.key}
                type="button"
                aria-pressed={editEmotions.includes(em.key)}
                className={
                  editEmotions.includes(em.key)
                    ? styles.editEmotionChipActive
                    : styles.editEmotionChip
                }
                onClick={() => toggleEditEmotion(em.key)}
                disabled={saving}
              >
                {em.label}
              </button>
            ))}
          </div>
        )}

        <textarea
          className={styles.editTextarea}
          rows={3}
          placeholder="Что повлияло на состояние?"
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
          disabled={saving}
        />

        {saveError && <p className={styles.editError}>{saveError}</p>}

        <div className={styles.editActions}>
          <button
            type="button"
            className={styles.saveBtn}
            onClick={handleSaveEdit}
            disabled={saving}
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
          </button>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={cancelEdit}
            disabled={saving}
          >
            Отмена
          </button>
        </div>
      </div>
    );
  }

  // ── Delete confirm mode ──────────────────────────────────────────────────────
  if (confirmDelete) {
    return (
      <div className={styles.item}>
        <div className={styles.top}>
          <span className={styles.date}>{formatDate(entry_date)}</span>
        </div>
        <p className={styles.deleteConfirmText}>
          Удалить запись за {formatDate(entry_date)}?
          <br />
          Это действие скроет её из дневника.
        </p>
        {deleteError && <p className={styles.deleteError}>{deleteError}</p>}
        <div className={styles.editActions}>
          <button
            type="button"
            className={styles.deleteBtnConfirm}
            onClick={handleConfirmDelete}
            disabled={deleting}
          >
            {deleting ? 'Удаление…' : 'Удалить'}
          </button>
          <button
            type="button"
            className={styles.cancelBtn}
            onClick={cancelDelete}
            disabled={deleting}
          >
            Отмена
          </button>
        </div>
      </div>
    );
  }

  // ── Read mode ────────────────────────────────────────────────────────────────
  return (
    <div className={styles.item}>
      <div className={styles.top}>
        {/* Left: date + mood badge */}
        <div className={styles.topMeta}>
          <span className={styles.date}>{formatDate(entry_date)}</span>
          <span className={styles.moodBadge} style={{ color: getMoodColor(mood_score) }}>
            {mood_score}/10 · {MOOD_WORDS[mood_score]}
          </span>
        </div>

        {/* Right: single kebab button — opacity-hidden on desktop, shown on hover/focus/open */}
        {(onUpdate || onDelete) && (
          <div className={styles.topActionsSlot}>
            <button
              type="button"
              className={
                menuOpen
                  ? `${styles.kebabButton} ${styles.kebabButtonOpen}`
                  : styles.kebabButton
              }
              aria-label="Действия с записью"
              aria-haspopup="menu"
              aria-expanded={menuOpen}
              onClick={() => setMenuOpen((prev) => !prev)}
            >
              ⋮
            </button>
          </div>
        )}
      </div>

      {/* Action menu — compact on desktop (right-aligned), full-width inline on mobile */}
      {menuOpen && (
        <div
          className={styles.actionSheet}
          role="region"
          aria-label="Действия с записью"
          data-testid="entry-action-sheet"
        >
          {onUpdate && (
            <button
              type="button"
              className={styles.sheetAction}
              onClick={() => { setMenuOpen(false); openEdit(); }}
            >
              Редактировать запись
            </button>
          )}
          {onDelete && (
            <button
              type="button"
              className={`${styles.sheetAction} ${styles.sheetActionDanger}`}
              onClick={() => { setMenuOpen(false); openDeleteConfirm(); }}
            >
              Удалить запись
            </button>
          )}
          <button
            type="button"
            className={styles.sheetCancel}
            onClick={() => setMenuOpen(false)}
          >
            Отмена
          </button>
        </div>
      )}

      {emotions && emotions.length > 0 && (
        <div className={styles.emotionRow}>
          {emotions.map((key) => (
            <span key={key} className={styles.emotionTag}>
              {getEmotionLabel(key, emotionCatalog)}
            </span>
          ))}
        </div>
      )}

      {entry_text && <p className={styles.note}>{entry_text}</p>}
    </div>
  );
}
