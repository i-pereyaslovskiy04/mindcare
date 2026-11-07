import { useId } from 'react';
import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import Select from '../../../../components/UI/Select/Select';
import { NORM_KINDS, emptyNormGroup, missingScaleCodes } from '../lib/rulesShape';
import styles from './RulesBuilder.module.css';

/**
 * Правила обработки методики (ADR-037): шкалы (подписи, основные, пределы
 * достоверности), общие уровни основных шкал, типы, инструкция. Контролируемый:
 * value — форма из lib/rulesShape, onChange — новая форма. Согласованность с
 * вопросами проверяет backend (TestAnalysisPanel → rule_issues).
 */
export default function RulesBuilder({ value, onChange, questions, nextKey, disabled = false }) {
  const baseId = useId();
  const id = (suffix) => `${baseId}-${suffix}`;
  const set = (patch) => onChange({ ...value, ...patch });
  const patchAt = (list, idx, patch) => list.map((it, i) => (i === idx ? { ...it, ...patch } : it));
  const missing = missingScaleCodes(value, questions);
  const scaleOptions = value.scales
    .filter((s) => s.code.trim())
    .map((s) => ({ value: s.code.trim(), label: s.label.trim() || s.code.trim() }));

  if (!value.enabled) {
    return (
      <div className={styles.wrap}>
        <Checkbox
          checked={false}
          disabled={disabled}
          onChange={(checked) => set({ enabled: checked })}
          label="Задать правила обработки (подписи шкал, уровни, достоверность, типы)"
        />
      </div>
    );
  }

  const addScales = () => set({
    scales: [...value.scales, ...missing.map((code) => ({
      _key: nextKey(), code, label: code, main: true, max_valid: '', own_levels: false, levels: [],
      norms: { enabled: false, kind: 'sten', label: '', groups: [] },
    }))],
  });

  return (
    <fieldset className={styles.wrap} disabled={disabled}>
      <legend className={styles.srOnly}>Правила обработки</legend>
      <Checkbox
        checked
        disabled={disabled}
        onChange={(checked) => set({ enabled: checked })}
        label="Задать правила обработки (подписи шкал, уровни, достоверность, типы)"
      />

      <div className={styles.field}>
        <label className={styles.label} htmlFor={id('instr')}>Инструкция участнику (необязательно)</label>
        <textarea id={id('instr')} className={styles.textarea} rows={3} value={value.instruction}
          onChange={(e) => set({ instruction: e.target.value })}
          placeholder="Показывается перед вопросами; пусто — используется описание теста" />
      </div>

      <h3 className={styles.subTitle}>Шкалы</h3>
      <p className={styles.hint}>
        Порядок строк — порядок колонок в выгрузке. «Основная» — для неё считается уровень.
        «Предел достоверности» заполняют только для шкал достоверности: балл выше
        предела делает результат недостоверным.
      </p>
      {value.scales.map((s, idx) => (
        <div key={s._key} className={styles.card}>
          <div className={styles.row4}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={id(`sc-${s._key}`)}>Код</label>
              <input id={id(`sc-${s._key}`)} className={styles.input} value={s.code}
                onChange={(e) => set({ scales: patchAt(value.scales, idx, { code: e.target.value }) })} />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={id(`sl-${s._key}`)}>Подпись</label>
              <input id={id(`sl-${s._key}`)} className={styles.input} value={s.label}
                onChange={(e) => set({ scales: patchAt(value.scales, idx, { label: e.target.value }) })} />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={id(`sv-${s._key}`)}>Предел достоверности</label>
              <input id={id(`sv-${s._key}`)} className={styles.inputNum} type="number" value={s.max_valid}
                placeholder="—"
                onChange={(e) => set({ scales: patchAt(value.scales, idx, { max_valid: e.target.value }) })} />
            </div>
            <div className={styles.actions}>
              <Checkbox checked={s.main} label="Основная"
                onChange={(checked) => set({ scales: patchAt(value.scales, idx, { main: checked }) })} />
              {s.main && (
                <Checkbox checked={Boolean(s.own_levels)} label="Свои уровни"
                  onChange={(checked) => set({
                    scales: patchAt(value.scales, idx, {
                      own_levels: checked,
                      levels: checked && !(s.levels || []).length
                        ? [{ _key: nextKey(), code: '', label: '', min: '0', max: '0' }]
                        : (s.levels || []),
                    }),
                  })} />
              )}
              <Button variant="icon" size="sm" aria-label={`Выше: ${s.code || 'шкала'}`} title="Выше"
                disabled={idx === 0}
                onClick={() => {
                  const next = [...value.scales];
                  [next[idx - 1], next[idx]] = [next[idx], next[idx - 1]];
                  set({ scales: next });
                }}>
                <span aria-hidden="true">↑</span>
              </Button>
              <Button variant="icon" size="sm" tone="danger" aria-label={`Удалить шкалу ${s.code}`}
                title="Удалить шкалу"
                onClick={() => set({ scales: value.scales.filter((_, i) => i !== idx) })}>
                <Icon name="trash" size={14} />
              </Button>
            </div>
          </div>
          <Checkbox checked={Boolean(s.norms?.enabled)} label="Нормы (стандартные баллы)"
            onChange={(checked) => set({
              scales: patchAt(value.scales, idx, {
                norms: {
                  ...(s.norms || { kind: 'sten', label: '', groups: [] }),
                  enabled: checked,
                  groups: checked && !(s.norms?.groups || []).length
                    ? [emptyNormGroup(nextKey)] : (s.norms?.groups || []),
                },
              }),
            })} />
          {s.norms?.enabled && (
            <NormsEditor norms={s.norms} scaleName={s.label || s.code} nextKey={nextKey} id={id}
              prefix={`n${s._key}`}
              onChange={(norms) => set({ scales: patchAt(value.scales, idx, { norms }) })} />
          )}
          {s.main && s.own_levels && (
            <div className={styles.ownLevels}>
              <p className={styles.hint}>
                Уровни шкалы «{s.label || s.code}» — вместо общих уровней.
              </p>
              <LevelRows levels={s.levels || []} nextKey={nextKey} id={id} prefix={`s${s._key}`}
                onChange={(levels) => set({ scales: patchAt(value.scales, idx, { levels }) })} />
            </div>
          )}
        </div>
      ))}
      <div className={styles.buttons}>
        <Button variant="secondary" onClick={() => set({
          scales: [...value.scales, {
            _key: nextKey(), code: '', label: '', main: true, max_valid: '', own_levels: false, levels: [],
            norms: { enabled: false, kind: 'sten', label: '', groups: [] },
          }],
        })}>
          + Шкала
        </Button>
        {missing.length > 0 && (
          <Button variant="secondary" onClick={addScales}>
            Добавить шкалы из вопросов ({missing.join(', ')})
          </Button>
        )}
      </div>
      {value.scales.some((s) => s.max_valid !== '') && (
        <div className={styles.field}>
          <label className={styles.label} htmlFor={id('mark')}>Пометка недостоверного результата</label>
          <input id={id('mark')} className={styles.input} value={value.invalid_mark}
            onChange={(e) => set({ invalid_mark: e.target.value })} />
        </div>
      )}

      <h3 className={styles.subTitle}>Уровни основных шкал</h3>
      <p className={styles.hint}>
        Общие для основных шкал диапазоны баллов (включительно), по возрастанию.
        Если у шкалы свои пороги, отметьте у неё «Свои уровни».
      </p>
      <LevelRows levels={value.levels} onChange={(levels) => set({ levels })}
        nextKey={nextKey} id={id} prefix="common" />

      <h3 className={styles.subTitle}>Типы</h3>
      <p className={styles.hint}>
        Тип выражен, если все его шкалы набрали не меньше порога. Подходит несколько — выводятся все.
      </p>
      {value.types.length > 0 && (
        <div className={styles.fieldNarrow}>
          <label className={styles.label} htmlFor={id('thr')}>Порог типа</label>
          <input id={id('thr')} className={styles.inputNum} type="number" value={value.type_threshold}
            onChange={(e) => set({ type_threshold: e.target.value })} />
        </div>
      )}
      {value.types.map((t, idx) => (
        <div key={t._key} className={styles.card}>
          <div className={styles.field}>
            <label className={styles.label} htmlFor={id(`tn-${t._key}`)}>Название типа</label>
            <input id={id(`tn-${t._key}`)} className={styles.input} value={t.name}
              onChange={(e) => set({ types: patchAt(value.types, idx, { name: e.target.value }) })} />
          </div>
          <div className={styles.typeScales}>
            <div className={styles.field}>
              <span className={styles.label}>Шкалы типа</span>
              <MultiSelect options={scaleOptions} value={t.scales} placeholder="Выберите шкалы"
                onChange={(val) => set({ types: patchAt(value.types, idx, { scales: val }) })} />
            </div>
            <Button variant="icon" size="sm" tone="danger" aria-label={`Удалить тип ${t.name || idx + 1}`}
              title="Удалить тип"
              onClick={() => set({ types: value.types.filter((_, i) => i !== idx) })}>
              <Icon name="trash" size={14} />
            </Button>
          </div>
        </div>
      ))}
      <div className={styles.buttons}>
        <Button variant="secondary" onClick={() => set({
          types: [...value.types, { _key: nextKey(), name: '', scales: [] }],
        })}>
          + Тип
        </Button>
      </div>
    </fieldset>
  );
}

/** Строки уровней (общих или своих у шкалы): код, название, от, до. */
function LevelRows({ levels, onChange, nextKey, id, prefix }) {
  const patchAt = (idx, patch) => onChange(levels.map((it, i) => (i === idx ? { ...it, ...patch } : it)));
  return (
    <>
      {levels.map((lv, idx) => (
        <div key={lv._key} className={styles.card}>
          <div className={styles.row4}>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={id(`${prefix}-lc-${lv._key}`)}>Код (латиница)</label>
              <input id={id(`${prefix}-lc-${lv._key}`)} className={styles.input} value={lv.code} placeholder="norm"
                onChange={(e) => patchAt(idx, { code: e.target.value })} />
            </div>
            <div className={styles.field}>
              <label className={styles.label} htmlFor={id(`${prefix}-ll-${lv._key}`)}>Название</label>
              <input id={id(`${prefix}-ll-${lv._key}`)} className={styles.input} value={lv.label} placeholder="Норма"
                onChange={(e) => patchAt(idx, { label: e.target.value })} />
            </div>
            <div className={styles.pair}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-lf-${lv._key}`)}>От</label>
                <input id={id(`${prefix}-lf-${lv._key}`)} className={styles.inputNum} type="number" value={lv.min}
                  onChange={(e) => patchAt(idx, { min: e.target.value })} />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-lt-${lv._key}`)}>До</label>
                <input id={id(`${prefix}-lt-${lv._key}`)} className={styles.inputNum} type="number" value={lv.max}
                  onChange={(e) => patchAt(idx, { max: e.target.value })} />
              </div>
            </div>
            <div className={styles.actions}>
              <Button variant="icon" size="sm" tone="danger" aria-label={`Удалить уровень ${lv.label || idx + 1}`}
                title="Удалить уровень"
                onClick={() => onChange(levels.filter((_, i) => i !== idx))}>
                <Icon name="trash" size={14} />
              </Button>
            </div>
          </div>
        </div>
      ))}
      <div className={styles.buttons}>
        <Button variant="secondary" onClick={() => onChange([
          ...levels, { _key: nextKey(), code: '', label: '', min: '0', max: '0' },
        ])}>
          + Уровень
        </Button>
      </div>
    </>
  );
}

const GENDERS = [
  { value: '', label: 'Любой' }, { value: 'female', label: 'Женский' }, { value: 'male', label: 'Мужской' },
];

/**
 * Нормы шкалы (ТЗ этапа 2, §5): тип, подпись, группы (пол, возраст) с
 * таблицами «сырой балл → стандартный». Применяются только в тестировании по
 * ссылке; группа — первая подходящая по анкете участника.
 */
function NormsEditor({ norms, onChange, nextKey, id, prefix, scaleName }) {
  const set = (patch) => onChange({ ...norms, ...patch });
  const setGroup = (gi, patch) => set({
    groups: norms.groups.map((g, i) => (i === gi ? { ...g, ...patch } : g)),
  });
  const setRow = (gi, ri, patch) => setGroup(gi, {
    table: norms.groups[gi].table.map((r, i) => (i === ri ? { ...r, ...patch } : r)),
  });
  return (
    <div className={styles.ownLevels}>
      <p className={styles.hint}>
        Нормы шкалы «{scaleName}» — только для тестирования по ссылке. Группа выбирается
        по анкете участника, первая подходящая; группа без условий — для остальных.
      </p>
      <div className={styles.row4}>
        <Select label="Тип" value={norms.kind} appearance="field" options={NORM_KINDS}
          onChange={(v) => set({ kind: v })} />
        <div className={styles.field}>
          <label className={styles.label} htmlFor={id(`${prefix}-label`)}>Подпись (необязательно)</label>
          <input id={id(`${prefix}-label`)} className={styles.input} value={norms.label}
            onChange={(e) => set({ label: e.target.value })} />
        </div>
      </div>
      {norms.groups.map((g, gi) => (
        <div key={g._key} className={styles.card}>
          <div className={styles.row4}>
            <Select label={`Группа ${gi + 1}: пол`} value={g.gender} appearance="field" options={GENDERS}
              onChange={(v) => setGroup(gi, { gender: v })} />
            <div className={styles.pair}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-${g._key}-amin`)}>Возраст от</label>
                <input id={id(`${prefix}-${g._key}-amin`)} className={styles.inputNum} type="number"
                  value={g.age_min} onChange={(e) => setGroup(gi, { age_min: e.target.value })} />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-${g._key}-amax`)}>до</label>
                <input id={id(`${prefix}-${g._key}-amax`)} className={styles.inputNum} type="number"
                  value={g.age_max} onChange={(e) => setGroup(gi, { age_max: e.target.value })} />
              </div>
            </div>
            <div className={styles.actions}>
              <Button variant="icon" size="sm" tone="danger" aria-label={`Удалить группу норм ${gi + 1}`}
                title="Удалить группу"
                onClick={() => set({ groups: norms.groups.filter((_, i) => i !== gi) })}>
                <Icon name="trash" size={14} />
              </Button>
            </div>
          </div>
          {g.extra?.length > 0 && (
            <p className={styles.hint}>
              Дополнительные условия из файла: {g.extra.map((c) => `${c.field} = ${c.eq ?? ''}`).join(', ')}
            </p>
          )}
          {g.table.map((r, ri) => (
            <div key={r._key} className={styles.row4}>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-${r._key}-min`)}>Сырой от</label>
                <input id={id(`${prefix}-${r._key}-min`)} className={styles.inputNum} type="number"
                  value={r.min} onChange={(e) => setRow(gi, ri, { min: e.target.value })} />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-${r._key}-max`)}>Сырой до</label>
                <input id={id(`${prefix}-${r._key}-max`)} className={styles.inputNum} type="number"
                  value={r.max} onChange={(e) => setRow(gi, ri, { max: e.target.value })} />
              </div>
              <div className={styles.field}>
                <label className={styles.label} htmlFor={id(`${prefix}-${r._key}-val`)}>Значение</label>
                <input id={id(`${prefix}-${r._key}-val`)} className={styles.inputNum} type="number"
                  value={r.value} onChange={(e) => setRow(gi, ri, { value: e.target.value })} />
              </div>
              <div className={styles.actions}>
                <Button variant="icon" size="sm" tone="danger" aria-label="Удалить строку нормы"
                  title="Удалить строку"
                  onClick={() => setGroup(gi, { table: g.table.filter((_, i) => i !== ri) })}>
                  <Icon name="trash" size={14} />
                </Button>
              </div>
            </div>
          ))}
          <div className={styles.buttons}>
            <Button variant="secondary" onClick={() => setGroup(gi, {
              table: [...g.table, { _key: nextKey(), min: '', max: '', value: '' }],
            })}>
              + Строка
            </Button>
          </div>
        </div>
      ))}
      <div className={styles.buttons}>
        <Button variant="secondary" onClick={() => set({ groups: [...norms.groups, emptyNormGroup(nextKey)] })}>
          + Группа норм
        </Button>
      </div>
    </div>
  );
}
