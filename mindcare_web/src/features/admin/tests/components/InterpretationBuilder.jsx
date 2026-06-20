import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import styles from './InterpretationBuilder.module.css';

/**
 * Редактор порогов интерпретации. Контролируемый: items + onChange.
 * item — { _key, scale_name, min_score, max_score, label, recommendation }.
 * scale_name пусто = интерпретация по итоговому баллу теста; иначе — по шкале.
 */
export default function InterpretationBuilder({ items, onChange, nextKey }) {
  const patch = (idx, p) => onChange(items.map((it, i) => (i === idx ? { ...it, ...p } : it)));
  const remove = (idx) => onChange(items.filter((_, i) => i !== idx));
  const add = () =>
    onChange([
      ...items,
      { _key: nextKey(), scale_name: '', min_score: 0, max_score: 0, label: '', recommendation: '' },
    ]);

  return (
    <div className={styles.wrap}>
      {items.map((it, idx) => (
        <div key={it._key} className={styles.card}>
          <div className={styles.head}>
            <span className={styles.num}>Порог {idx + 1}</span>
            <Button variant="icon" size="sm" tone="danger" aria-label="Удалить порог"
              onClick={() => remove(idx)}>
              <Icon name="trash" size={14} />
            </Button>
          </div>

          <div className={styles.grid}>
            <div className={styles.field}>
              <label className={styles.label}>Шкала (пусто = итог)</label>
              <input
                className={styles.input}
                placeholder="напр. Тревога"
                value={it.scale_name}
                onChange={(e) => patch(idx, { scale_name: e.target.value })}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>От</label>
              <input
                className={styles.inputNum}
                type="number"
                value={it.min_score}
                onChange={(e) => patch(idx, { min_score: Number(e.target.value) })}
              />
            </div>
            <div className={styles.field}>
              <label className={styles.label}>До</label>
              <input
                className={styles.inputNum}
                type="number"
                value={it.max_score}
                onChange={(e) => patch(idx, { max_score: Number(e.target.value) })}
              />
            </div>
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Название уровня</label>
            <input
              className={styles.input}
              placeholder="напр. Высокий уровень"
              value={it.label}
              onChange={(e) => patch(idx, { label: e.target.value })}
            />
          </div>

          <div className={styles.field}>
            <label className={styles.label}>Рекомендация (необязательно)</label>
            <textarea
              className={styles.textarea}
              rows={2}
              placeholder="Текст, который увидит студент при попадании в этот диапазон"
              value={it.recommendation}
              onChange={(e) => patch(idx, { recommendation: e.target.value })}
            />
          </div>
        </div>
      ))}

      <Button variant="secondary" onClick={add}>+ Добавить порог интерпретации</Button>
    </div>
  );
}
