import styles from './QuestionRenderer.module.css';

/**
 * Рендер одного вопроса по типу. Без скоринговой логики — value_score не
 * приходит с бэкенда (ключ теста скрыт). Сообщает ответ наверх через onChange.
 *
 * value — текущее значение ответа на этот вопрос:
 *   single_choice   → option_id (number) | null
 *   multiple_choice → number[] (selected option ids)
 *   scale           → number | null
 *   free_text       → string
 * onChange(nextValue) — обновляет ответ в родителе.
 */
export default function QuestionRenderer({ question, index, value, onChange, invalid, total }) {
  const { question_type: type, question_text, is_required, options, config, media } = question;
  const titleId = `q-title-${question.id}`;
  const questionImages = media || [];

  return (
    <div className={[styles.card, invalid && styles.cardInvalid].filter(Boolean).join(' ')}>
      <div className={styles.head}>
        <span className={styles.num} aria-hidden="true">{index + 1}</span>
        <h3 className={styles.text} id={titleId}>
          {/* Текстовый эквивалент прогресса — не только визуальный номер (ГОСТ) */}
          <span className={styles.counter}>
            Вопрос {index + 1} из {total}.{' '}
          </span>
          {question_text}
          {is_required && (
            <>
              <span className={styles.req} aria-hidden="true"> *</span>
              <span className="visually-hidden"> (обязательный вопрос)</span>
            </>
          )}
        </h3>
      </div>

      {questionImages.map((m, i) => {
        if (m.kind === 'video') {
          return (
            <video
              key={m.uuid || i}
              className={styles.qMedia}
              src={m.url}
              controls
              preload="metadata"
              aria-label={m.caption || question_text}
            />
          );
        }
        if (m.kind === 'audio') {
          return (
            <audio
              key={m.uuid || i}
              className={styles.qAudio}
              src={m.url}
              controls
              preload="metadata"
              aria-label={m.caption || question_text}
            />
          );
        }
        return (
          <img
            key={m.uuid || i}
            className={styles.qImage}
            src={m.url}
            alt={m.caption || question_text}
          />
        );
      })}

      {type === 'single_choice' && (
        <div className={styles.options} role="radiogroup" aria-labelledby={titleId}>
          {options.map((opt) => (
            <label key={opt.id} className={styles.option}>
              <input
                type="radio"
                name={`q-${question.id}`}
                className={styles.radio}
                checked={value === opt.id}
                onChange={() => onChange(opt.id)}
              />
              <OptionContent option={opt} />
            </label>
          ))}
        </div>
      )}

      {type === 'multiple_choice' && (
        <div className={styles.options} role="group" aria-labelledby={titleId}>
          {options.map((opt) => {
            const arr = Array.isArray(value) ? value : [];
            const checked = arr.includes(opt.id);
            return (
              <label key={opt.id} className={styles.option}>
                <input
                  type="checkbox"
                  className={styles.check}
                  checked={checked}
                  onChange={() =>
                    onChange(
                      checked ? arr.filter((id) => id !== opt.id) : [...arr, opt.id],
                    )
                  }
                />
                <OptionContent option={opt} />
              </label>
            );
          })}
        </div>
      )}

      {type === 'scale' && (
        <ScaleControl
          config={config}
          value={value}
          onChange={onChange}
          labelledBy={titleId}
        />
      )}

      {type === 'free_text' && (
        <textarea
          className={styles.textarea}
          rows={4}
          value={value || ''}
          placeholder="Ваш ответ…"
          aria-labelledby={titleId}
          onChange={(e) => onChange(e.target.value)}
        />
      )}
    </div>
  );
}

/**
 * Текст варианта + необязательное изображение. Картинка декоративна: доступное
 * имя даёт текст варианта, поэтому alt="" и aria-hidden (у option_media нет
 * подписи, ГОСТ Р 52872-2019 требует именно так для дублирующей текст картинки).
 */
function OptionContent({ option }) {
  const images = option.media || [];
  return (
    <span className={styles.optBody}>
      {images.map((img, i) => (
        <img
          key={img.uuid || i}
          className={styles.optImage}
          src={img.url}
          alt=""
          aria-hidden="true"
        />
      ))}
      <span className={styles.optText}>{option.option_text}</span>
    </span>
  );
}

function ScaleControl({ config, value, onChange, labelledBy }) {
  const lo = Number.isInteger(config?.min) ? config.min : 0;
  const hi = Number.isInteger(config?.max) ? config.max : 10;
  const step = Number.isInteger(config?.step) && config.step > 0 ? config.step : 1;
  const current = value ?? lo;

  return (
    <div className={styles.scale}>
      <input
        type="range"
        className={styles.range}
        min={lo}
        max={hi}
        step={step}
        value={current}
        aria-labelledby={labelledBy}
        aria-valuetext={
          value == null ? 'не выбрано' : `${value} из ${hi}`
        }
        onChange={(e) => onChange(Number(e.target.value))}
      />
      <div className={styles.scaleRow}>
        <span className={styles.scaleEdge}>{lo}</span>
        <span className={styles.scaleValue}>{value ?? '—'}</span>
        <span className={styles.scaleEdge}>{hi}</span>
      </div>
    </div>
  );
}
