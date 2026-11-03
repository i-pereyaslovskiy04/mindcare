import { useCallback, useEffect, useRef, useState } from 'react';
import { createClientNote, getClientNotes, updateClientNote } from '../../../api/sessionNotes.api';
import useKeysetList from '../../assignments/hooks/useKeysetList';

export const CLIENT_NOTES_PAGE_SIZE = 20;

// Предел поиска актуальной версии заметки после конфликта (страниц по pageSize).
const LOCATE_MAX_PAGES = 50;

const isGone = (err) => err?.status === 404;
const AUDIT_UNAVAILABLE = 'Заметка не сохранена: не удалось зафиксировать действие в журнале. Повторите попытку позже.';
const FALLBACK = 'Не удалось сохранить заметку. Введённый текст сохранён — повторите попытку.';
const CONFLICT = 'Заметку уже изменили в другом окне. Ваша правка сохранена в форме; ниже — актуальный текст. Сохранение заменит актуальную версию вашей правкой.';
const CONFLICT_NO_CURRENT = 'Заметку уже изменили в другом окне. Ваша правка сохранена в форме, но актуальную версию загрузить не удалось — нажмите «Загрузить актуальную версию».';
const NOT_FOUND = 'Заметка недоступна или удалена. Ваша правка сохранена в форме — скопируйте её при необходимости.';

function createMessage(err) {
  switch (err?.status) {
    case 422: return 'Эта встреча недоступна для привязки. Уберите привязку или выберите другую встречу.';
    case 404: return 'Заметки недоступны: сопровождение не активно.';
    case 503: return AUDIT_UNAVAILABLE;
    default:  return FALLBACK;
  }
}

function updateMessage(err) {
  switch (err?.status) {
    case 404: return NOT_FOUND;
    case 503: return AUDIT_UNAVAILABLE;
    default:  return FALLBACK;
  }
}

const NO_DRAFTS = Object.freeze({});

/**
 * Свои заметки психолога о клиенте (ADR-035).
 *
 * Контекст запроса — поколение (ctx.gen): оно увеличивается при смене
 * studentUuid И при размонтировании. Каждый запрос запоминает поколение на
 * старте; ответ с другим поколением — устаревший: он не меняет ни форму, ни
 * ошибки, ни блокировки, не перечитывает список и не вызывает callbacks
 * вызывающего (result.stale). Это действует и при смене key карточки
 * (размонтирование), и при A → B → A (старый ответ A не относится к новому A).
 *
 * Черновики правок (drafts) живут здесь, ключ — uuid заметки, а не строка
 * списка: они переживают перезагрузку списка (в т.ч. заметку со второй
 * страницы, которой нет в первой странице после reload) и конфликт 409.
 * После 409 хук находит актуальную версию заметки (постраничный поиск) и
 * кладёт её в draft.current; baseVersion обновляется, так что следующее
 * сохранение осознанно заменяет актуальную версию правкой пользователя.
 * Успех — только по ответу сервера, без оптимистичного обновления;
 * двойная отправка исключена.
 */
export default function useClientNotes(studentUuid, { pageSize = CLIENT_NOTES_PAGE_SIZE } = {}) {
  const fetchPage = useCallback(
    ({ before }) => getClientNotes(studentUuid, { before, size: pageSize }),
    [studentUuid, pageSize],
  );
  const list = useKeysetList(fetchPage, {
    enabled: Boolean(studentUuid), resetKey: studentUuid, isFatalLoadMoreError: isGone,
  });
  const reload = list.reset;

  const [creating, setCreating] = useState(false);
  const [createError, setCreateError] = useState(null);
  const [savingUuid, setSavingUuid] = useState(null);
  const [draftState, setDraftState] = useState({ owner: studentUuid, map: NO_DRAFTS });
  const drafts = draftState.owner === studentUuid ? draftState.map : NO_DRAFTS;
  const lock = useRef(false);
  const ctx = useRef({ gen: 0 });
  const studentRef = useRef(studentUuid);
  studentRef.current = studentUuid;

  useEffect(() => {
    const context = ctx.current;   // объект не заменяется — одно поколение на хук
    context.gen += 1;
    lock.current = false;
    setCreating(false);
    setCreateError(null);
    setSavingUuid(null);
    setDraftState({ owner: studentUuid, map: NO_DRAFTS });
    return () => { context.gen += 1; };
  }, [studentUuid]);

  const patchDraft = useCallback((uuid, patch) => {
    setDraftState(prev => {
      const base = prev.owner === studentRef.current ? prev.map : NO_DRAFTS;
      if (!base[uuid]) return prev;
      return { owner: studentRef.current, map: { ...base, [uuid]: { ...base[uuid], ...patch } } };
    });
  }, []);

  const openDraft = useCallback((note) => {
    setDraftState(prev => {
      const base = prev.owner === studentRef.current ? prev.map : NO_DRAFTS;
      if (base[note.uuid]) return prev;
      return {
        owner: studentRef.current,
        map: {
          ...base,
          [note.uuid]: {
            content: note.content, noteType: note.note_type, baseVersion: note.version,
            note, current: null, error: null,
          },
        },
      };
    });
  }, []);

  const changeDraft = useCallback((uuid, patch) => patchDraft(uuid, { ...patch, error: null }), [patchDraft]);

  const discardDraft = useCallback((uuid) => {
    setDraftState(prev => {
      const base = prev.owner === studentRef.current ? prev.map : NO_DRAFTS;
      if (!base[uuid]) return prev;
      const { [uuid]: _removed, ...rest } = base;
      return { owner: studentRef.current, map: rest };
    });
  }, []);

  const create = useCallback(async ({ content, noteType, appointmentUuid }) => {
    if (lock.current || !studentUuid) return { ok: false };
    const gen = ctx.current.gen;
    const stale = () => gen !== ctx.current.gen;
    lock.current = true;
    setCreating(true);
    setCreateError(null);
    try {
      await createClientNote(studentUuid, { content, noteType, appointmentUuid });
      if (stale()) return { ok: false, stale: true };
      reload();
      return { ok: true };
    } catch (err) {
      if (stale()) return { ok: false, stale: true };
      setCreateError(createMessage(err));
      if (err?.status === 404) reload();
      return { ok: false, status: err?.status };
    } finally {
      if (!stale()) {
        lock.current = false;
        setCreating(false);
      }
    }
  }, [studentUuid, reload]);

  // Постраничный поиск актуальной версии заметки (отдельного GET по uuid нет).
  const locate = useCallback(async (noteUuid, gen) => {
    const stale = () => gen !== ctx.current.gen;
    let before;
    for (let page = 0; page < LOCATE_MAX_PAGES; page += 1) {
      // eslint-disable-next-line no-await-in-loop
      const data = await getClientNotes(studentRef.current, { before, size: pageSize });
      if (stale()) return { stale: true };
      const found = (data?.items || []).find(n => n.uuid === noteUuid);
      if (found) return { note: found };
      if (!data?.next_cursor) return { note: null };
      before = data.next_cursor;
    }
    return { note: null };
  }, [pageSize]);

  const loadCurrent = useCallback(async (noteUuid, gen) => {
    try {
      const res = await locate(noteUuid, gen);
      if (res.stale) return;
      if (res.note) {
        patchDraft(noteUuid, { current: res.note, baseVersion: res.note.version, error: CONFLICT });
      } else {
        patchDraft(noteUuid, { error: NOT_FOUND });
      }
    } catch (err) {
      if (gen !== ctx.current.gen) return;
      patchDraft(noteUuid, { error: isGone(err) ? NOT_FOUND : CONFLICT_NO_CURRENT, needsRefresh: !isGone(err) });
    }
  }, [locate, patchDraft]);

  const update = useCallback(async (noteUuid) => {
    const draft = drafts[noteUuid];
    if (lock.current || !studentUuid || !draft) return { ok: false };
    const gen = ctx.current.gen;
    const stale = () => gen !== ctx.current.gen;
    lock.current = true;
    setSavingUuid(noteUuid);
    patchDraft(noteUuid, { error: null, needsRefresh: false });
    try {
      await updateClientNote(studentUuid, noteUuid, {
        content: draft.content, noteType: draft.noteType, version: draft.baseVersion,
      });
      if (stale()) return { ok: false, stale: true };
      discardDraft(noteUuid);
      reload();
      return { ok: true };
    } catch (err) {
      if (stale()) return { ok: false, stale: true };
      if (err?.status === 409) {
        // Черновик остаётся независимо от того, есть ли строка в текущей странице.
        patchDraft(noteUuid, { error: CONFLICT_NO_CURRENT, needsRefresh: true });
        reload();
        await loadCurrent(noteUuid, gen);
      } else {
        patchDraft(noteUuid, { error: updateMessage(err) });
        if (err?.status === 404) reload();
      }
      return { ok: false, status: err?.status };
    } finally {
      if (!stale()) {
        lock.current = false;
        setSavingUuid(null);
      }
    }
  }, [drafts, studentUuid, reload, patchDraft, discardDraft, loadCurrent]);

  /** Повторная загрузка актуальной версии после конфликта (если поиск не удался). */
  const refreshDraft = useCallback(async (noteUuid) => {
    if (lock.current || !drafts[noteUuid]) return;
    const gen = ctx.current.gen;
    lock.current = true;
    setSavingUuid(noteUuid);
    patchDraft(noteUuid, { error: null, needsRefresh: false });
    try {
      await loadCurrent(noteUuid, gen);
    } finally {
      if (gen === ctx.current.gen) {
        lock.current = false;
        setSavingUuid(null);
      }
    }
  }, [drafts, patchDraft, loadCurrent]);

  let status = 'ready';
  if (list.loading && list.items.length === 0) status = 'loading';
  else if (list.error) status = list.error.status === 404 ? 'unavailable' : 'error';

  return {
    list,
    status,
    reload,
    create,
    creating,
    createError,
    drafts,
    openDraft,
    changeDraft,
    discardDraft,
    update,
    refreshDraft,
    savingUuid,
  };
}
