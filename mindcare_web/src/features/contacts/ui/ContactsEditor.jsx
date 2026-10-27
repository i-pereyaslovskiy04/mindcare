import { useEffect, useMemo } from 'react';
import Button from '../../../components/UI/Button/Button';
import Icon from '../../../components/Icon/Icon';
import Select from '../../../components/UI/Select/Select';
import TextField from '../../../components/UI/TextField/TextField';
import {
  buildMethods, methodKey, methodOf, offeredMethods, valueSpec,
} from '../lib/methods';
import styles from './ContactsEditor.module.css';

const NO_ITEMS = [];

// Видимый счётчик «Добавлено N из M» — только когда до предела осталось не
// больше двух контактов; иначе тот же текст остаётся скрытым live-сообщением.
const COUNTER_VISIBLE_MARGIN = 2;

export const rowDomId = (prefix, id) => `${prefix}-row-${id}`;
export const fieldDomId = (prefix, id, field) => `${prefix}-${id}-${field}`;

// Ошибки type/service относятся к единому селектору «Способ связи».
const FIELD_ALIASES = { type: 'method', service: 'method' };

function describeItem(item, methods) {
  const method = methodOf(methods, item.type, item.service);
  return [method?.label ?? item.type, item.label, item.value].filter(Boolean).join(' · ');
}

function Skeleton({ children, role = 'status' }) {
  return <p className={styles.state} role={role}>{children}</p>;
}

/**
 * Редактор дополнительных контактов владельца (ADR-032). Данные и действия
 * приходят из useMyContacts. Обычный контакт — компактная строка: «Способ связи»
 * (единый выбор вместо пары тип+сервис) | значение | «Удалить»; у вариантов
 * «Другой …» добавляется обязательное «Название». Для нового контакта
 * предлагается короткий список способов (offeredMethods); текущий и сохранённый
 * способ строки остаются выбираемыми, даже если их нет в списке. Прежняя необязательная подпись
 * в интерфейсе скрыта, но в данных сохраняется. Введённое не теряется ни при
 * ошибке, ни при конфликте версий; ошибки привязаны к полю (aria-invalid/
 * describedby), после неудачной проверки фокус уходит на первое ошибочное поле.
 */
export default function ContactsEditor({ contacts, audienceNote, idPrefix = 'contacts' }) {
  const {
    status, loadError, retryLoad, rows, limits, catalog, savedItems = NO_ITEMS, dirty, canAdd, fieldErrors,
    saveState, saveMessage, conflict, focusTarget,
    addRow, updateRow, changeMethod, clearLabel, removeRow, revert, save, overwrite, loadSaved,
  } = contacts;
  const saving = saveState === 'saving';
  const methods = useMemo(() => buildMethods(catalog), [catalog]);
  const savedById = useMemo(
    () => new Map(savedItems.map((item) => [item.id, item])),
    [savedItems],
  );

  /** Варианты селектора строки: короткий список + её текущий и сохранённый способ. */
  const optionsFor = (row) => {
    const saved = savedById.get(row.id);
    const keep = [methodKey(row.type, row.service || null)];
    if (saved) keep.push(methodKey(saved.type, saved.service || null));
    return offeredMethods(methods, keep).map((method) => ({ value: method.key, label: method.label }));
  };

  useEffect(() => {
    if (!focusTarget) return;
    const field = FIELD_ALIASES[focusTarget.field] ?? focusTarget.field;
    const el = document.getElementById(fieldDomId(idPrefix, focusTarget.id, field))
      || document.getElementById(rowDomId(idPrefix, focusTarget.id));
    el?.focus();
  }, [focusTarget, idPrefix]);

  if (status === 'idle' || status === 'loading') {
    return <Skeleton>Загрузка контактов…</Skeleton>;
  }
  if (status === 'loadError') {
    return (
      <div className={styles.loadError}>
        <p role="alert" className={styles.alert}>{loadError}</p>
        <Button type="button" variant="secondary" onClick={retryLoad}>Повторить</Button>
      </div>
    );
  }

  return (
    <form
      className={styles.form}
      noValidate
      onSubmit={(e) => { e.preventDefault(); save(); }}
    >
      <p className={styles.note}>{audienceNote}</p>
      <p
        className={rows.length >= limits.max_items - COUNTER_VISIBLE_MARGIN ? styles.counter : 'visually-hidden'}
        aria-live="polite"
      >
        Добавлено {rows.length} из {limits.max_items}
      </p>

      {rows.length === 0 && (
        <p className={styles.empty}>Дополнительных контактов пока нет.</p>
      )}

      <ul className={styles.list}>
        {rows.map((row, index) => {
          const errors = fieldErrors[row.id] || {};
          const method = methodOf(methods, row.type, row.service);
          const spec = valueSpec(method);
          const needsName = method ? method.requiresName : (row.type === 'other' || row.service === 'other');
          const number = index + 1;
          return (
            <li key={row.id} className={styles.item}>
              <div
                role="group"
                aria-label={`Контакт ${number}`}
                id={rowDomId(idPrefix, row.id)}
                tabIndex={-1}
                className={styles.row}
              >
                <Select
                  id={fieldDomId(idPrefix, row.id, 'method')}
                  appearance="field"
                  label="Способ связи"
                  placeholder="Выберите способ связи"
                  value={method?.key ?? ''}
                  displayLabel={method ? undefined : [row.type, row.service].filter(Boolean).join(' / ')}
                  options={optionsFor(row)}
                  onChange={(key) => changeMethod(row.id, key)}
                  disabled={saving}
                  error={errors.service || errors.type}
                  className={styles.methodField}
                />
                <TextField
                  id={fieldDomId(idPrefix, row.id, 'value')}
                  appearance="field"
                  label={spec.label}
                  hint={spec.hint}
                  placeholder={spec.placeholder}
                  type={spec.inputType}
                  inputMode={spec.inputMode}
                  autoComplete="off"
                  value={row.value}
                  maxLength={limits.value_max}
                  onChange={(e) => updateRow(row.id, {
                    value: spec.format ? spec.format(e.target.value) : e.target.value,
                  })}
                  disabled={saving}
                  error={errors.value}
                  className={styles.valueField}
                />
                {/* «Удалить» выровнена по контролам строки: распорка повторяет
                    высоту подписи поля и растёт вместе со шрифтом. */}
                <div className={styles.deleteCell}>
                  <span className={styles.deleteSpacer} aria-hidden="true">{'\u00a0'}</span>
                  <Button
                    type="button"
                    variant="icon"
                    tone="danger"
                    onClick={() => removeRow(row.id)}
                    disabled={saving}
                    aria-label={`Удалить контакт ${number}`}
                    title="Удалить контакт"
                    className={styles.deleteButton}
                  >
                    <Icon name="trash" size={15} />
                  </Button>
                </div>
                {needsName && (
                  <TextField
                    id={fieldDomId(idPrefix, row.id, 'label')}
                    appearance="field"
                    label="Название"
                    placeholder="Например: Discord"
                    autoComplete="off"
                    value={row.label}
                    maxLength={limits.label_max}
                    onChange={(e) => updateRow(row.id, { label: e.target.value })}
                    disabled={saving}
                    error={errors.label}
                    className={styles.nameField}
                  />
                )}

                {errors.hiddenLabel && (
                  <div className={styles.rowAlert} role="alert">
                    <p className={styles.rowAlertText}>
                      Сервер не принял прежнюю подпись этого контакта: «{row.label}».
                      {' '}{errors.hiddenLabel}. Подпись не нужна для связи - её можно удалить.
                    </p>
                    <Button
                      id={fieldDomId(idPrefix, row.id, 'label')}
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={() => clearLabel(row.id)}
                      disabled={saving}
                    >
                      Удалить прежнюю подпись
                    </Button>
                  </div>
                )}
              </div>
            </li>
          );
        })}
      </ul>

      <div className={styles.addRow}>
        <Button type="button" variant="secondary" onClick={() => addRow()} disabled={!canAdd || saving}>
          <Icon name="plus" size={14} /> Добавить контакт
        </Button>
        {!canAdd && (
          <span className={styles.limitHint}>
            Достигнут предел: не более {limits.max_items} дополнительных контактов.
          </span>
        )}
      </div>

      {/* Зона сохранения отделена от списка и «Добавить контакт»: результат
          сохранения, конфликт версий и кнопки — вместе, под тонкой линией. */}
      <div className={styles.saveZone}>
        {saveState === 'saved' && (
          <p className={styles.success} role="status">Контакты сохранены.</p>
        )}
        {saveState === 'error' && saveMessage && (
          <p className={styles.alert} role="alert">{saveMessage}</p>
        )}

        {saveState === 'conflict' && conflict && (
          <div className={styles.conflict} role="alert">
            <p className={styles.conflictText}>
              Контакты были изменены в другом окне или на другом устройстве.
              Ваши правки сохранены в форме - выберите, что сделать.
            </p>
            {conflict.saved && (
              <details className={styles.saved}>
                <summary>Что сейчас сохранено ({conflict.saved.items.length})</summary>
                {conflict.saved.items.length === 0 ? (
                  <p>Список пуст.</p>
                ) : (
                  <ul>
                    {conflict.saved.items.map((item) => (
                      <li key={item.id}>{describeItem(item, methods)}</li>
                    ))}
                  </ul>
                )}
              </details>
            )}
            <div className={styles.conflictActions}>
              <Button type="button" variant="primary" onClick={overwrite} loading={saving}>
                Перезаписать моими правками
              </Button>
              <Button type="button" variant="secondary" onClick={loadSaved} disabled={saving}>
                Загрузить сохранённые
              </Button>
            </div>
          </div>
        )}

        <div className={styles.actions}>
          <Button type="submit" variant="primary" loading={saving} disabled={!dirty || saveState === 'conflict'}>
            Сохранить контакты
          </Button>
          <Button type="button" variant="secondary" onClick={revert} disabled={!dirty || saving}>
            Отменить изменения
          </Button>
          {dirty && saveState !== 'saving' && (
            <span className={styles.dirty}>Есть несохранённые изменения</span>
          )}
        </div>
      </div>
    </form>
  );
}
