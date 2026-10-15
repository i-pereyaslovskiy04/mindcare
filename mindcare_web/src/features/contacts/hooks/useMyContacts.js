import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { getMyContacts, saveMyContacts } from '../../../api/contacts.api';
import {
  DEFAULT_LIMITS, applyMethod, emptyRow, isDirty, rowsFromItems, toPayloadItems,
} from '../lib/draft';
import { buildMethods } from '../lib/methods';
import { errorsFromServer, messageFor, validateRows } from '../lib/rules';

const SAVE_UNAVAILABLE = 'Не удалось сохранить контакты. Повторите попытку.';

/**
 * Дополнительные контакты владельца (ADR-031): загрузка, черновик, сохранение.
 *
 * Состояния: status idle|loading|ready|loadError; saveState idle|saving|saved|
 * error|conflict. Введённое НИКОГДА не теряется: ни при ошибке, ни при
 * конфликте версий — черновик (rows) меняют только действия пользователя и
 * успешное сохранение. id строки создаётся один раз при добавлении (повтор
 * отправки несёт тот же payload — сервер ответит no-op).
 *
 * enabled=false (например, режим «под именем») — запросов нет. Ответы
 * устаревших загрузок отбрасываются.
 */
export default function useMyContacts({ enabled }) {
  const [status, setStatus] = useState('idle');
  const [loadError, setLoadError] = useState('');
  const [server, setServer] = useState(null);       // { version, items, limits, catalog, updated_at }
  const [rows, setRows] = useState([]);
  const [saveState, setSaveState] = useState('idle');
  const [saveMessage, setSaveMessage] = useState('');
  const [fieldErrors, setFieldErrors] = useState({});
  const [conflict, setConflict] = useState(null);   // { currentVersion, saved: {version, items}|null }
  const [focusTarget, setFocusTarget] = useState(null);

  const requestId = useRef(0);
  const savingRef = useRef(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; requestId.current += 1; };
  }, []);

  const limits = server?.limits ?? DEFAULT_LIMITS;
  const catalog = server?.catalog ?? null;

  const applyServer = useCallback((data) => {
    setServer(data);
    setRows(rowsFromItems(data.items));
    setFieldErrors({});
    setConflict(null);
  }, []);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setStatus('loading');
    setLoadError('');
    try {
      const data = await getMyContacts();
      if (id !== requestId.current) return;
      applyServer(data);
      setSaveState('idle');
      setSaveMessage('');
      setStatus('ready');
    } catch (err) {
      if (id !== requestId.current) return;
      setLoadError(err?.message || 'Не удалось загрузить контакты');
      setStatus('loadError');
    }
  }, [applyServer]);

  useEffect(() => {
    if (enabled) load();
    else {
      requestId.current += 1;
      setStatus('idle');
    }
  }, [enabled, load]);

  const touch = useCallback(() => {
    setSaveState((s) => (s === 'saved' || s === 'error' ? 'idle' : s));
    setSaveMessage('');
  }, []);

  const addRow = useCallback((type = 'phone') => {
    setRows((current) => (current.length >= limits.max_items ? current : [...current, emptyRow(type)]));
    touch();
  }, [limits.max_items, touch]);

  const updateRow = useCallback((id, patch) => {
    setRows((current) => current.map((row) => {
      if (row.id !== id) return row;
      const next = { ...row, ...patch };
      // Смена типа сбрасывает сервис (набор сервисов зависит от типа).
      if (patch.type && patch.type !== row.type) next.service = '';
      return next;
    }));
    setFieldErrors((current) => {
      if (!current[id]) return current;
      const rest = { ...current };
      delete rest[id];
      return rest;
    });
    touch();
  }, [touch]);

  /** Выбор «Способа связи» (ключ из buildMethods): type и service меняются вместе. */
  const changeMethod = useCallback((id, key) => {
    const method = buildMethods(catalog).find((m) => m.key === key);
    if (!method) return;
    const saved = server?.items?.find((item) => item.id === id);
    setRows((current) => current.map((row) => (row.id === id ? applyMethod(row, method, saved) : row)));
    setFieldErrors((current) => {
      if (!current[id]) return current;
      const rest = { ...current };
      delete rest[id];
      return rest;
    });
    touch();
  }, [catalog, server, touch]);

  /** Явное действие пользователя: убрать прежнюю подпись (скрытое поле), если сервер её не принял. */
  const clearLabel = useCallback((id) => {
    updateRow(id, { label: '' });
  }, [updateRow]);

  const removeRow = useCallback((id) => {
    setRows((current) => current.filter((row) => row.id !== id));
    setFieldErrors((current) => {
      const rest = { ...current };
      delete rest[id];
      return rest;
    });
    touch();
  }, [touch]);

  const revert = useCallback(() => {
    if (!server) return;
    setRows(rowsFromItems(server.items));
    setFieldErrors({});
    setSaveState('idle');
    setSaveMessage('');
  }, [server]);

  const dirty = useMemo(
    () => (server ? isDirty(rows, server.items, catalog) : false),
    [rows, server, catalog],
  );

  const doSave = useCallback(async (versionOverride) => {
    if (savingRef.current || !server) return { ok: false };
    const check = validateRows(rows, catalog, limits);
    if (check.hasErrors) {
      setFieldErrors(check.errors);
      setFocusTarget({ ...check.firstInvalid, n: Date.now() });
      setSaveState('error');
      setSaveMessage('Исправьте отмеченные поля');
      return { ok: false };
    }
    savingRef.current = true;
    setSaveState('saving');
    setSaveMessage('');
    setFieldErrors({});
    try {
      const data = await saveMyContacts({
        version: versionOverride ?? server.version,
        items: toPayloadItems(rows, catalog),
      });
      if (!mounted.current) return { ok: true };
      applyServer(data);
      setSaveState('saved');
      return { ok: true, changed: data.changed };
    } catch (err) {
      if (!mounted.current) return { ok: false };
      if (err?.status === 409 && err?.code === 'contacts_version_conflict') {
        const currentVersion = err.body?.current_version;
        setConflict({ currentVersion, saved: null });
        setSaveState('conflict');
        // Актуальное серверное состояние — только для сравнения; черновик не трогаем.
        getMyContacts()
          .then((data) => {
            if (mounted.current) {
              setConflict((c) => (c ? { ...c, saved: { version: data.version, items: data.items } } : c));
            }
          })
          .catch(() => {});
      } else if (err?.status === 422 && Array.isArray(err.body?.errors)) {
        const mapped = errorsFromServer(err.body.errors, rows, limits);
        setFieldErrors(mapped.errors);
        if (mapped.firstInvalid) setFocusTarget({ ...mapped.firstInvalid, n: Date.now() });
        setSaveState('error');
        setSaveMessage(mapped.general || 'Исправьте отмеченные поля');
      } else if (err?.status === 503) {
        setSaveState('error');
        setSaveMessage(SAVE_UNAVAILABLE);
      } else {
        setSaveState('error');
        setSaveMessage(err?.message || 'Не удалось сохранить контакты');
      }
      return { ok: false };
    } finally {
      savingRef.current = false;
    }
  }, [applyServer, catalog, limits, rows, server]);

  const save = useCallback(() => doSave(), [doSave]);

  /** Конфликт: отправить МОИ правки поверх актуальной версии. */
  const overwrite = useCallback(() => {
    const version = conflict?.saved?.version ?? conflict?.currentVersion;
    if (!Number.isInteger(version)) return Promise.resolve({ ok: false });
    return doSave(version);
  }, [conflict, doSave]);

  /** Конфликт: заменить черновик сохранённой версией (черновик теряется по явному выбору). */
  const loadSaved = useCallback(async () => {
    if (conflict?.saved && server) {
      applyServer({ ...server, version: conflict.saved.version, items: conflict.saved.items });
      setSaveState('idle');
      setSaveMessage('');
      return;
    }
    await load();
  }, [applyServer, conflict, load, server]);

  return {
    status,
    loadError,
    retryLoad: load,
    rows,
    limits,
    catalog,
    version: server?.version ?? 0,
    dirty,
    canAdd: rows.length < limits.max_items,
    fieldErrors,
    saveState,
    saveMessage,
    conflict,
    focusTarget,
    addRow,
    updateRow,
    changeMethod,
    clearLabel,
    removeRow,
    revert,
    save,
    overwrite,
    loadSaved,
    messageFor: (code, field) => messageFor(code, limits, field),
  };
}
