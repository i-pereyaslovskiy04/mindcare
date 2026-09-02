import { useState } from 'react';
import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import ImageUpload from '../../../../components/UI/ImageUpload/ImageUpload';
import MediaUpload from '../../../../components/UI/MediaUpload/MediaUpload';
import { SCORED_TYPES, hasOptions } from '../lib/testShape';
import styles from './QuestionBuilder.module.css';

const isAv = (m) => m.kind === 'audio' || m.kind === 'video';

const TYPE_OPTIONS = [
  { value: 'single_choice',   label: 'Один вариант' },
  { value: 'multiple_choice', label: 'Несколько вариантов' },
  { value: 'scale',           label: 'Шкала' },
  { value: 'free_text',       label: 'Свободный ответ' },
];

/**
 * Список медиа (0..N) вопроса или варианта. Элемент —
 * { media_uuid, url, kind, caption }. Изображения — через ImageUpload,
 * аудио/видео — через MediaUpload. Уже прикреплённые элементы видны всегда
 * (заменяются/удаляются); пустые слоты добавления НЕ рендерятся по умолчанию —
 * иначе редактор тестов захламляется dropzone на каждый вопрос/вариант без
 * медиа. Слоты открываются кнопкой-переключателем «+ Добавить …» и остаются
 * открытыми, пока их явно не свернуть — так можно прикрепить несколько файлов
 * подряд. withCaption — только вопрос (у варианта картинка декоративна).
 * allowAv — прикрепление аудио/видео (только вопрос, MVP).
 */
function MediaList({ list, onChange, withCaption, allowAv, label }) {
  const items = list || [];
  const [adding, setAdding] = useState(false);

  const update = (i, val) => {
    if (!val) return onChange(items.filter((_, k) => k !== i));  // удаление
    return onChange(items.map((m, k) => (
      k === i
        ? { ...m, media_uuid: val.uuid, url: val.url, kind: val.kind || m.kind || 'image' }
        : m
    )));
  };
  const add = (val) => {
    if (val) onChange([...items, {
      media_uuid: val.uuid, url: val.url, kind: val.kind || 'image', caption: '',
    }]);
  };
  const setCaption = (i, caption) => onChange(items.map((m, k) => (
    k === i ? { ...m, caption } : m
  )));

  return (
    <div className={styles.mediaList}>
      {items.map((m, i) => (
        <div key={m.media_uuid} className={styles.mediaItem}>
          {isAv(m) ? (
            <MediaUpload
              label={`Медиа ${i + 1}`}
              value={{ uuid: m.media_uuid, url: m.url, kind: m.kind }}
              onChange={(val) => update(i, val)}
            />
          ) : (
            <ImageUpload
              label={`${label} ${i + 1}`}
              value={{ uuid: m.media_uuid, url: m.url }}
              onChange={(val) => update(i, val)}
            />
          )}
          {withCaption && (
            <input
              className={styles.input}
              placeholder="Подпись / альтернативный текст (screen reader)"
              value={m.caption || ''}
              onChange={(e) => setCaption(i, e.target.value)}
            />
          )}
        </div>
      ))}

      {adding ? (
        <>
          <ImageUpload
            key="__add_img"
            label={items.length ? 'Добавить изображение' : label}
            value={null}
            onChange={add}
          />
          {allowAv && (
            <MediaUpload key="__add_av" label="Добавить аудио/видео" value={null} onChange={add} />
          )}
          <button
            type="button"
            className={styles.addMediaToggle}
            onClick={() => setAdding(false)}
          >
            Свернуть
          </button>
        </>
      ) : (
        <button
          type="button"
          className={styles.addMediaToggle}
          onClick={() => setAdding(true)}
        >
          + {allowAv ? 'Добавить медиа' : 'Добавить изображение'}
        </button>
      )}
    </div>
  );
}

/**
 * Редактор списка вопросов теста. Полностью контролируемый: получает questions и
 * onChange(newQuestions). Каждый вопрос — { _key, question_text, question_type,
 * is_required, scale, config:{min,max,step,weight}, media:[...],
 * options:[{_key, option_text, value_score, media:[...]}] }.
 *
 * scoring — метод подсчёта теста; поле «Вес» показывается только при 'weighted'.
 * nextKey — генератор стабильных ключей для новых строк (из родителя).
 */
export default function QuestionBuilder({ questions, onChange, nextKey, scoring = 'sum' }) {
  const patchQuestion = (idx, patch) => {
    onChange(questions.map((q, i) => (i === idx ? { ...q, ...patch } : q)));
  };

  const addQuestion = () => {
    onChange([
      ...questions,
      {
        _key: nextKey(),
        question_text: '',
        question_type: 'single_choice',
        is_required: true,
        scale: '',
        config: { min: 0, max: 10, step: 1, weight: 1 },
        media: [],
        options: [
          { _key: nextKey(), option_text: '', value_score: 0, media: [] },
          { _key: nextKey(), option_text: '', value_score: 1, media: [] },
        ],
      },
    ]);
  };

  const removeQuestion = (idx) => onChange(questions.filter((_, i) => i !== idx));

  const moveQuestion = (idx, dir) => {
    const j = idx + dir;
    if (j < 0 || j >= questions.length) return;
    const next = [...questions];
    [next[idx], next[j]] = [next[j], next[idx]];
    onChange(next);
  };

  const patchOption = (qIdx, oIdx, patch) => {
    const q = questions[qIdx];
    const options = q.options.map((o, i) => (i === oIdx ? { ...o, ...patch } : o));
    patchQuestion(qIdx, { options });
  };

  const addOption = (qIdx) => {
    const q = questions[qIdx];
    patchQuestion(qIdx, {
      options: [...q.options, { _key: nextKey(), option_text: '', value_score: 0, media: [] }],
    });
  };

  const removeOption = (qIdx, oIdx) => {
    const q = questions[qIdx];
    patchQuestion(qIdx, { options: q.options.filter((_, i) => i !== oIdx) });
  };

  // Правило «все шкалы или ни одной»: если шкала указана лишь у части вопросов,
  // подсчёт молча выбросит остальные и итоговый балл станет пустым. Бэкенд это
  // отвергает (422) — предупреждаем до сохранения.
  const scored = questions.filter((q) => SCORED_TYPES.includes(q.question_type));
  const withoutScale = scored.filter((q) => !q.scale.trim());
  const partialScales = withoutScale.length > 0 && withoutScale.length !== scored.length;
  const usedScales = [...new Set(scored.map((q) => q.scale.trim()).filter(Boolean))];
  const showWeight = scoring === 'weighted';

  return (
    <div className={styles.wrap}>
      {partialScales && (
        <p className={styles.scaleWarning} role="alert">
          Шкала указана не у всех вопросов, участвующих в подсчёте
          ({scored.length - withoutScale.length} из {scored.length}). Либо
          заполните её везде, либо очистите везде: иначе вопросы без шкалы
          выпадут из подсчёта.
        </p>
      )}

      {usedScales.length > 0 && (
        <datalist id="qb-scale-names">
          {usedScales.map((name) => <option key={name} value={name} />)}
        </datalist>
      )}

      {questions.map((q, qIdx) => (
        <div key={q._key} className={styles.qCard}>
          <div className={styles.qHead}>
            <span className={styles.qNum}>Вопрос {qIdx + 1}</span>
            <div className={styles.qHeadActions}>
              <Button variant="icon" size="sm" aria-label="Выше" title="Переместить выше"
                disabled={qIdx === 0} onClick={() => moveQuestion(qIdx, -1)}>
                <Icon name="chevron-left" size={14} className={styles.rotUp} />
              </Button>
              <Button variant="icon" size="sm" aria-label="Ниже" title="Переместить ниже"
                disabled={qIdx === questions.length - 1} onClick={() => moveQuestion(qIdx, 1)}>
                <Icon name="chevron-right" size={14} className={styles.rotDown} />
              </Button>
              <Button variant="icon" size="sm" tone="danger" aria-label="Удалить вопрос" title="Удалить вопрос"
                onClick={() => removeQuestion(qIdx)}>
                <Icon name="trash" size={14} />
              </Button>
            </div>
          </div>

          <textarea
            className={styles.qText}
            rows={2}
            placeholder="Текст вопроса"
            value={q.question_text}
            onChange={(e) => patchQuestion(qIdx, { question_text: e.target.value })}
          />

          <div className={styles.qMedia}>
            <span className={styles.fieldLabel}>Медиа вопроса (изображения, аудио, видео — необязательно)</span>
            <MediaList
              list={q.media}
              withCaption
              allowAv
              label="Изображение вопроса"
              onChange={(media) => patchQuestion(qIdx, { media })}
            />
          </div>

          <div className={styles.qRow}>
            <Select
              label="Тип ответа"
              value={q.question_type}
              options={TYPE_OPTIONS}
              onChange={(val) => patchQuestion(qIdx, { question_type: val })}
            />
            <div className={styles.field}>
              <label className={styles.fieldLabel}>Шкала (для многошкальных)</label>
              <input
                className={styles.input}
                placeholder="напр. Тревога — или пусто"
                list="qb-scale-names"
                value={q.scale}
                onChange={(e) => patchQuestion(qIdx, { scale: e.target.value })}
              />
            </div>
          </div>

          <div className={styles.qFlags}>
            <Checkbox
              checked={q.is_required}
              onChange={(checked) => patchQuestion(qIdx, { is_required: checked })}
              label="Обязательный вопрос"
            />
            {showWeight && q.question_type !== 'free_text' && (
              <div className={styles.field}>
                <label className={styles.fieldLabel}>Вес вопроса</label>
                <input
                  className={styles.scaleInput}
                  type="number"
                  min={1}
                  value={q.config.weight ?? 1}
                  onChange={(e) => patchQuestion(qIdx, {
                    config: { ...q.config, weight: Math.max(1, Number(e.target.value) || 1) },
                  })}
                />
              </div>
            )}
          </div>

          {/* Варианты ответа — для choice-типов */}
          {hasOptions(q.question_type) && (
            <div className={styles.options}>
              <div className={styles.optionsHead}>
                <span>Вариант</span>
                <span className={styles.scoreLabel}>Балл</span>
                <span />
              </div>
              {q.options.map((o, oIdx) => (
                <div key={o._key} className={styles.optionBlock}>
                  <div className={styles.optionRow}>
                    <input
                      className={styles.input}
                      placeholder={`Вариант ${oIdx + 1}`}
                      value={o.option_text}
                      onChange={(e) => patchOption(qIdx, oIdx, { option_text: e.target.value })}
                    />
                    <input
                      className={styles.scoreInput}
                      type="number"
                      value={o.value_score}
                      onChange={(e) =>
                        patchOption(qIdx, oIdx, { value_score: Number(e.target.value) })}
                    />
                    <Button variant="icon" size="sm" tone="danger" aria-label="Удалить вариант" title="Удалить вариант"
                      disabled={q.options.length <= 2}
                      onClick={() => removeOption(qIdx, oIdx)}>
                      <Icon name="x" size={14} />
                    </Button>
                  </div>
                  <div className={styles.optionMedia}>
                    <MediaList
                      list={o.media}
                      label="Картинка варианта"
                      onChange={(media) => patchOption(qIdx, oIdx, { media })}
                    />
                  </div>
                </div>
              ))}
              <button type="button" className={styles.addOption} onClick={() => addOption(qIdx)}>
                + Добавить вариант
              </button>
            </div>
          )}

          {/* Диапазон шкалы — для scale */}
          {q.question_type === 'scale' && (
            <div className={styles.scaleRow}>
              <div className={styles.field}>
                <label className={styles.fieldLabel}>Минимум</label>
                <input
                  className={styles.scaleInput}
                  type="number"
                  value={q.config.min}
                  onChange={(e) =>
                    patchQuestion(qIdx, { config: { ...q.config, min: Number(e.target.value) } })}
                />
              </div>
              <div className={styles.field}>
                <label className={styles.fieldLabel}>Максимум</label>
                <input
                  className={styles.scaleInput}
                  type="number"
                  value={q.config.max}
                  onChange={(e) =>
                    patchQuestion(qIdx, { config: { ...q.config, max: Number(e.target.value) } })}
                />
              </div>
              <div className={styles.field}>
                <label className={styles.fieldLabel}>Шаг</label>
                <input
                  className={styles.scaleInput}
                  type="number"
                  min={1}
                  value={q.config.step}
                  onChange={(e) =>
                    patchQuestion(qIdx, { config: { ...q.config, step: Number(e.target.value) } })}
                />
              </div>
            </div>
          )}

          {q.question_type === 'free_text' && (
            <p className={styles.hint}>Свободный ответ не участвует в подсчёте баллов.</p>
          )}
        </div>
      ))}

      <Button variant="secondary" onClick={addQuestion}>+ Добавить вопрос</Button>
    </div>
  );
}
