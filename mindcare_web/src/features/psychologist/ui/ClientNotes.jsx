import { useEffect, useId, useRef, useState } from 'react';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import Select from '../../../components/UI/Select/Select';
import useClientNotes from '../hooks/useClientNotes';
import { formatMeetingWhen } from '../lib/meetingFormat';
import styles from './ClientNotes.module.css';

const CONTENT_MAX = 50000;

export const NOTE_TYPE_OPTIONS = [
  { value: 'general',   label: 'Общая' },
  { value: 'diagnosis', label: 'Диагностическая' },
  { value: 'plan',      label: 'План работы' },
  { value: 'followup',  label: 'Динамика' },
];
const NOTE_TYPE_LABELS = Object.fromEntries(NOTE_TYPE_OPTIONS.map(o => [o.value, o.label]));

const _momentFmt = new Intl.DateTimeFormat('ru-RU', {
  timeZone: 'Europe/Moscow', day: 'numeric', month: 'long', year: 'numeric',
  hour: '2-digit', minute: '2-digit',
});
const formatMoment = (iso) => (iso ? _momentFmt.format(new Date(iso)) : '');

/** Черновик формы привязан к uuid клиента: чужой черновик не показывается. */
function useOwnedState(owner, initial) {
  const [state, setState] = useState({ owner, value: initial });
  const value = state.owner === owner ? state.value : initial;
  const set = (next) => setState({ owner, value: typeof next === 'function' ? next(value) : next });
  return [value, set];
}

/**
 * Редактор заметки. Состояние черновика — в useClientNotes (draft), а не в
 * строке списка: перезагрузка списка и конфликт версий его не теряют.
 */
function NoteEditor({ draft, onChange, onSave, onCancel, onRefresh, saving }) {
  const textId = useId();
  const typeLabelId = useId();
  const errorId = useId();
  return (
    <form
      className={styles.editor}
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (draft.content.trim()) onSave();
      }}
    >
      <label htmlFor={textId} className={styles.label}>Текст заметки</label>
      <textarea
        id={textId}
        className={styles.textarea}
        value={draft.content}
        onChange={e => onChange({ content: e.target.value })}
        maxLength={CONTENT_MAX}
        rows={4}
        aria-describedby={draft.error ? errorId : undefined}
        disabled={saving}
      />
      <div className={styles.row}>
        <div className={styles.field}>
          <span id={typeLabelId} className={styles.label}>Тип</span>
          <Select
            value={draft.noteType}
            options={NOTE_TYPE_OPTIONS}
            onChange={(noteType) => onChange({ noteType })}
            labelledBy={typeLabelId}
            disabled={saving}
          />
        </div>
        <div className={styles.actions}>
          <Button type="button" variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
            Отмена
          </Button>
          <Button type="submit" size="sm" loading={saving} disabled={!draft.content.trim()}>
            Сохранить
          </Button>
        </div>
      </div>
      {draft.error && <p id={errorId} className={styles.error} role="alert">{draft.error}</p>}
      {draft.needsRefresh && (
        <div>
          <Button type="button" variant="secondary" size="sm" onClick={onRefresh} disabled={saving}>
            Загрузить актуальную версию
          </Button>
        </div>
      )}
      {draft.current && (
        <div className={styles.current}>
          <p className={styles.label}>Актуальная версия заметки</p>
          <p className={styles.text}>{draft.current.content}</p>
        </div>
      )}
    </form>
  );
}

function NoteItem({ note, draft, onEdit, onChange, onSave, onCancel, onRefresh, saving, orphan = false }) {
  return (
    <li className={styles.item}>
      <div className={styles.itemHead}>
        <Badge tone="neutral">{NOTE_TYPE_LABELS[note.note_type] || 'Заметка'}</Badge>
        <span className={styles.meta}>
          {formatMoment(note.created_at)}
          {note.version > 1 && ` · изменено ${formatMoment(note.updated_at)}`}
        </span>
      </div>
      {orphan && (
        <p className={styles.meta}>
          Заметка не входит в загруженную часть списка — нажмите «Показать ещё», чтобы увидеть её среди остальных.
        </p>
      )}
      {note.appointment && (
        <p className={styles.meta}>
          К встрече: {formatMeetingWhen(note.appointment.starts_at)}
        </p>
      )}
      {draft ? (
        <NoteEditor
          draft={draft}
          onChange={onChange}
          onSave={onSave}
          onCancel={onCancel}
          onRefresh={onRefresh}
          saving={saving}
        />
      ) : (
        <>
          <p className={styles.text}>{note.content}</p>
          <div className={styles.itemFoot}>
            <Button type="button" variant="ghost" size="sm" onClick={onEdit}>Изменить</Button>
          </div>
        </>
      )}
    </li>
  );
}

/**
 * «Заметки» в карточке клиента (ADR-035): существующие session_notes —
 * только свои заметки психолога об этом клиенте. Без удаления и без
 * публикации клиенту. linkedMeeting = { clientUuid, meeting } — заметка к
 * конкретной встрече (из блока «Встречи с клиентом», любой страницы);
 * применяется, только если clientUuid совпадает с текущим клиентом.
 */
export default function ClientNotes({ studentUuid, linkedMeeting = null, onClearLinkedMeeting }) {
  const {
    list, status, reload, create, creating, createError,
    drafts, openDraft, changeDraft, discardDraft, update, refreshDraft, savingUuid,
  } = useClientNotes(studentUuid);
  const [content, setContent] = useOwnedState(studentUuid, '');
  const [noteType, setNoteType] = useOwnedState(studentUuid, 'general');
  const textRef = useRef(null);
  const textId = useId();
  const typeLabelId = useId();
  const errorId = useId();

  const meeting = linkedMeeting && linkedMeeting.clientUuid === studentUuid
    ? linkedMeeting.meeting : null;
  const meetingUuid = meeting?.uuid || null;

  useEffect(() => {
    if (meetingUuid) textRef.current?.focus();
  }, [meetingUuid]);

  async function submit(e) {
    e.preventDefault();
    if (!content.trim()) return;
    const result = await create({ content, noteType, appointmentUuid: meetingUuid });
    // Устаревший результат (другой клиент / размонтирование) ничего не меняет:
    // ни форму, ни привязку встречи нового клиента.
    if (result.ok && !result.stale) {
      setContent('');
      setNoteType('general');
      onClearLinkedMeeting?.();
    }
  }

  const listUuids = new Set(list.items.map(n => n.uuid));
  const orphanDrafts = Object.values(drafts).filter(d => !listUuids.has(d.note.uuid));

  function renderItem(note, orphan = false) {
    return (
      <NoteItem
        key={note.uuid}
        note={note}
        orphan={orphan}
        draft={drafts[note.uuid] || null}
        onEdit={() => openDraft(note)}
        onChange={(patch) => changeDraft(note.uuid, patch)}
        onSave={() => update(note.uuid)}
        onCancel={() => discardDraft(note.uuid)}
        onRefresh={() => refreshDraft(note.uuid)}
        saving={savingUuid === note.uuid}
      />
    );
  }

  if (status === 'unavailable') {
    return <p className={styles.muted}>Заметки недоступны: сопровождение не активно.</p>;
  }

  return (
    <div className={styles.wrap}>
      <form className={styles.form} onSubmit={submit} noValidate>
        {meeting && (
          <div className={styles.linked}>
            <span>К встрече: {formatMeetingWhen(meeting.starts_at, meeting.ends_at)}</span>
            <Button type="button" variant="ghost" size="sm" onClick={onClearLinkedMeeting}
              disabled={creating}>
              Убрать
            </Button>
          </div>
        )}
        <label htmlFor={textId} className={styles.label}>Новая заметка</label>
        <textarea
          id={textId}
          ref={textRef}
          className={styles.textarea}
          value={content}
          onChange={e => setContent(e.target.value)}
          maxLength={CONTENT_MAX}
          rows={4}
          aria-describedby={createError ? errorId : undefined}
          disabled={creating}
        />
        <div className={styles.row}>
          <div className={styles.field}>
            <span id={typeLabelId} className={styles.label}>Тип</span>
            <Select
              value={noteType}
              options={NOTE_TYPE_OPTIONS}
              onChange={setNoteType}
              labelledBy={typeLabelId}
              disabled={creating}
            />
          </div>
          <Button type="submit" size="sm" loading={creating} disabled={!content.trim()}>
            Сохранить заметку
          </Button>
        </div>
        {createError && <p id={errorId} className={styles.error} role="alert">{createError}</p>}
        <p className={styles.hint}>
          Заметки видны вам; супервизор может открыть заметку — просмотр фиксируется в журнале.
          Клиенту заметки не показываются.
        </p>
      </form>

      {status === 'loading' && <p className={styles.muted} role="status">Загружаем заметки…</p>}
      {status === 'error' && (
        <div className={styles.errorBox} role="alert">
          <p className={styles.error}>Не удалось загрузить заметки.</p>
          <Button type="button" size="sm" variant="secondary" onClick={reload}>Повторить</Button>
        </div>
      )}
      {status === 'ready' && list.items.length === 0 && (
        <p className={styles.muted}>Заметок пока нет.</p>
      )}
      {orphanDrafts.length > 0 && (
        <section aria-label="Несохранённые правки">
          <h4 className={styles.groupTitle}>Несохранённые правки</h4>
          <ul className={styles.list}>
            {orphanDrafts.map(draft => renderItem(draft.current || draft.note, true))}
          </ul>
        </section>
      )}
      {list.items.length > 0 && status !== 'error' && (
        <ul className={styles.list} aria-label="Заметки о клиенте">
          {list.items.map(note => renderItem(note))}
        </ul>
      )}
      {list.loadMoreError && (
        <p className={styles.error} role="alert">
          Не удалось загрузить следующие заметки. Нажмите «Показать ещё».
        </p>
      )}
      {list.hasMore && !list.error && (
        <div className={styles.more}>
          <Button type="button" variant="secondary" size="sm" onClick={list.loadMore}
            loading={list.loadingMore}>
            Показать ещё
          </Button>
        </div>
      )}
    </div>
  );
}
