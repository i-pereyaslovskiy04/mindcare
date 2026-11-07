import { useId } from 'react';
import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import { missingScaleCodes } from '../lib/rulesShape';
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
