/**
 * Черновик дополнительных контактов (ADR-032).
 *
 * Строка черновика: { id, type, service, value, label }. `id` — UUID, который
 * клиент создаёт ОДИН раз при добавлении строки и больше не меняет (он же
 * React-key): повтор отправки после потерянного ответа несёт тот же payload,
 * и сервер видит «ничего не изменилось». Сервер id не генерирует.
 */
import { needsName } from './methods';

export const DEFAULT_LIMITS = { max_items: 10, label_max: 80, value_max: 500 };

export function newContactId() {
  const c = window.crypto;
  if (c && typeof c.randomUUID === 'function') return c.randomUUID();
  // Запасной вариант (старые браузеры / тестовая среда): UUIDv4.
  const bytes = new Uint8Array(16);
  if (c && typeof c.getRandomValues === 'function') c.getRandomValues(bytes);
  else for (let i = 0; i < 16; i += 1) bytes[i] = Math.floor(Math.random() * 256);
  bytes[6] = (bytes[6] & 0x0f) | 0x40;
  bytes[8] = (bytes[8] & 0x3f) | 0x80;
  const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
}

export function emptyRow(type = 'phone') {
  return { id: newContactId(), type, service: '', value: '', label: '' };
}

export function rowsFromItems(items) {
  return (items || []).map((item) => ({
    id: item.id,
    type: item.type,
    service: item.service || '',
    value: item.value || '',
    label: item.label || '',
  }));
}

/** Тип требует сервис (мессенджер/соцсеть) — по каталогу backend. */
export function serviceKindOf(catalog, type) {
  return catalog?.types?.find((t) => t.code === type)?.service_kind ?? null;
}

/** Payload для PUT: trim, пустая подпись → null, сервис только где он нужен. */
export function toPayloadItems(rows, catalog) {
  return rows.map((row) => ({
    id: row.id,
    type: row.type,
    service: serviceKindOf(catalog, row.type) ? (row.service || null) : null,
    value: (row.value || '').trim(),
    label: (row.label || '').trim() || null,
  }));
}

/** Нормализованный вид серверных элементов для сравнения с черновиком. */
export function itemsForCompare(items) {
  return (items || []).map((item) => ({
    id: item.id,
    type: item.type,
    service: item.service || null,
    value: item.value,
    label: item.label || null,
  }));
}

export function isDirty(rows, serverItems, catalog) {
  return JSON.stringify(toPayloadItems(rows, catalog))
    !== JSON.stringify(itemsForCompare(serverItems));
}

/**
 * Выбор способа связи в строке: `type` и `service` задаются вместе, поэтому прежний
 * `service` не может остаться у несовместимого типа. Значение при РЕАЛЬНОЙ смене
 * способа очищается: оно относится к смыслу прежнего способа (номер телефона —
 * не имя в Telegram), а несовместимый текст в новом поле выглядит сломанной
 * формой. Выбор уже выбранного способа строку не меняет; загрузка и rerender
 * applyMethod не вызывают. Вернуть прежнее значение можно «Отменить изменения».
 * Название неизвестного сервиса, введённое в этой сессии, при переходе на обычный
 * способ не переносится (возвращается СОХРАНЁННАЯ подпись или пусто); сохранённая
 * подпись не стирается никогда. savedItem — элемент с тем же id из последнего
 * ответа сервера.
 */
export function applyMethod(row, method, savedItem) {
  if (row.type === method.type && (row.service || '') === (method.service || '')) return row;
  const next = {
    ...row, type: method.type, service: method.service || '', value: '',
  };
  if (needsName(row) && !needsName(next) && (row.label || '') !== (savedItem?.label || '')) {
    next.label = savedItem?.label || '';
  }
  return next;
}
