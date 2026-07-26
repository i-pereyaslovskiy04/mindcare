import styles from './TestAnalysisPanel.module.css';

/**
 * Диапазон баллов методики и проблемы порогов интерпретации.
 *
 * Автор конструктора иначе не видит ни реального максимума (он считается из
 * вариантов, а не из поля max_score), ни того, что часть баллов не покрыта
 * порогами: такой результат уходит студенту без расшифровки.
 *
 * Это предупреждения, а не блокировка сохранения — см. service.analyze_test.
 */

const KIND_TEXT = {
  gap: 'не покрыт ни одним порогом — студент получит результат без расшифровки',
  out_of_range: 'недостижим: такой балл невозможно набрать',
  unknown_scale: 'ссылается на шкалу, которой нет ни у одного вопроса',
};

function scaleLabel(name) {
  return name ? `шкала «${name}»` : 'итоговый балл';
}

function rangeLabel(min, max) {
  return min === max ? `${min}` : `${min}–${max}`;
}

export default function TestAnalysisPanel({ data, loading, error }) {
  if (error) {
    return <p className={styles.muted}>Не удалось проверить пороги: {error}</p>;
  }
  if (!data || !data.score_bounds.length) {
    return loading ? <p className={styles.muted}>Проверяем пороги…</p> : null;
  }

  const { score_bounds: bounds, issues } = data;

  return (
    <div className={styles.panel}>
      <div className={styles.bounds}>
        <span className={styles.boundsLabel}>Достижимый диапазон баллов:</span>
        {bounds.map((b) => (
          <span key={b.scale_name ?? '__total__'} className={styles.bound}>
            {scaleLabel(b.scale_name)} — {rangeLabel(b.min_score, b.max_score)}
          </span>
        ))}
      </div>

      {issues.length > 0 && (
        <ul className={styles.issues} role="alert">
          {issues.map((i) => (
            <li key={`${i.kind}-${i.scale_name ?? ''}-${i.min_score}-${i.max_score}`}>
              {i.kind === 'gap' ? (
                <>Диапазон <b>{rangeLabel(i.min_score, i.max_score)}</b> ({scaleLabel(i.scale_name)}) {KIND_TEXT.gap}.</>
              ) : (
                <>Порог «{i.label}» <b>{rangeLabel(i.min_score, i.max_score)}</b> ({scaleLabel(i.scale_name)}) {KIND_TEXT[i.kind]}.</>
              )}
            </li>
          ))}
        </ul>
      )}

      {!issues.length && !loading && (
        <p className={styles.ok}>Пороги покрывают весь диапазон баллов.</p>
      )}
    </div>
  );
}
