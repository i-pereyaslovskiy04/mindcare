import { useState, useRef, useEffect } from 'react';
import * as diaryApi from '../../../../api/diary.api';
import styles from './DiaryEntryItem.module.css';

const MOOD_WORDS = [
  '', 'Очень тяжело', 'Тяжело', 'Грустно', 'Так себе',
  'Нейтрально', 'Спокойно', 'Хорошо', 'Светло', 'Радостно', 'Прекрасно',
];

// Устаревшие ключи эмоций (деактивированы в каталоге после c3a7f8e2d1b9).
// Исторические записи дневника с этими ключами отображаются через legacy-метки
// вместо технического ключа.
const LEGACY_EMOTION_LABELS = {
  light: 'легко',
  angry: 'злобно',
};

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
  if (found) return found.label;
  return LEGACY_EMOTION_LABELS[key] ?? key;
}

export default function DiaryEntryItem({
  entry,
  emotionCatalog = [],
  onUpdate,
  onDelete,
  // Controlled from parent (DiaryHistoryList) for single-open behavior.
  // When not provided, falls back to internal state (standalone usage / tests).
  actionsOpen,
  onActionsToggle,
  onActionsClose,
}) {
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

  // Menu open: controlled from parent when actionsOpen is provided, else internal
  const isControlled = actionsOpen !== undefined;
  const [internalOpen, setInternalOpen] = useState(false);
  const menuOpen = isControlled ? actionsOpen : internalOpen;

  function toggleMenu() {
    if (isControlled) onActionsToggle?.();
    else setInternalOpen((prev) => !prev);
  }

  // Stable ref so Escape / click-outside handlers never hold stale closures
  const slotRef = useRef(null);
  const doCloseRef = useRef();
  doCloseRef.current = isControlled
    ? () => onActionsClose?.()
    : () => setInternalOpen(false);

  useEffect(() => {
    if (!menuOpen) return;
    function onKeyDown(e) {
      if (e.key === 'Escape') doCloseRef.current();
    }
    function onPointerDown(e) {
      if (slotRef.current && !slotRef.current.contains(e.target)) {
        doCloseRef.current();
      }
    }
    document.addEventListener('keydown', onKeyDown);
    document.addEventListener('pointerdown', onPointerDown);
    return () => {
      document.removeEventListener('keydown', onKeyDown);
      document.removeEventListener('pointerdown', onPointerDown);
    };
  }, [menuOpen]); // eslint-disable-line react-hooks/exhaustive-deps

  function closeMenu() {
    doCloseRef.current();
  }

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
          <div className={styles.editMoodHeader}>
            <span className={styles.editMoodLabel}>Настроение</span>
            <strong className={styles.editMoodValue}>
              {editMood}/10 · {MOOD_WORDS[editMood]}
            </strong>
          </div>
          <input
            type="range"
            min="1"
            max="10"
            value={editMood}
            onChange={(e) => setEditMood(Number(e.target.value))}
            className={styles.editMoodSlider}
            disabled={saving}
            aria-label="Настроение"
            aria-valuetext={`${editMood} из 10, ${MOOD_WORDS[editMood]}`}
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
            className={styles.cancelBtn}
            onClick={cancelEdit}
            disabled={saving}
          >
            Отмена
          </button>
          <button
            type="button"
            className={styles.saveBtn}
            onClick={handleSaveEdit}
            disabled={saving}
          >
            {saving ? 'Сохранение…' : 'Сохранить'}
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

        {/* Right: kebab + absolute dropdown menu — position:relative anchor */}
        {(onUpdate || onDelete) && (
          <div className={styles.topActionsSlot} ref={slotRef}>
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
              onClick={toggleMenu}
            >
              ⋮
            </button>

            {menuOpen && (
              <div
                className={styles.actionMenu}
                aria-label="Действия с записью"
                data-testid="entry-action-sheet"
              >
                {onUpdate && (
                  <button
                    type="button"
                    className={styles.menuAction}
                    aria-label="Редактировать запись"
                    onClick={() => { closeMenu(); openEdit(); }}
                  >
                    Редактировать
                  </button>
                )}
                {onDelete && (
                  <button
                    type="button"
                    className={`${styles.menuAction} ${styles.menuActionDanger}`}
                    aria-label="Удалить запись"
                    onClick={() => { closeMenu(); openDeleteConfirm(); }}
                  >
                    Удалить
                  </button>
                )}
              </div>
            )}
          </div>
        )}
      </div>

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
