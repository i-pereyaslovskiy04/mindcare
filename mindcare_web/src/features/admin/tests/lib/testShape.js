/**
 * Трансформации дерева теста между формой конструктора и backend-формой.
 *
 * Вынесено из TestFormPage, потому что тем же преобразованием пользуются
 * анализ порогов (POST /api/admin/tests/analyze) и предпросмотр: у всех троих
 * должно быть одно представление дерева, иначе автор увидит не то, что сохранит.
 *
 * Форма вопроса в конструкторе:
 *   { _key, question_text, question_type, is_required, scale,
 *     config: {min,max,step}, options: [{_key, option_text, value_score}] }
 */

// Типы, участвующие в подсчёте баллов (free_text — не участвует).
export const SCORED_TYPES = ['single_choice', 'multiple_choice', 'scale'];

export const hasOptions = (t) => t === 'single_choice' || t === 'multiple_choice';

// Медиа вопроса/варианта в форме: список { media_uuid, url, kind, caption }.
// url/kind нужны только фронту (превью/выбор тега); на бэк уходит media_uuid.
function mediaFromBackend(list) {
  return (list || []).map((m) => ({
    media_uuid: m.uuid,
    url: m.url,
    kind: m.kind || 'image',
    caption: m.caption || '',
  }));
}

export function fromBackendQuestion(q, nextKey) {
  const cfg = q.config || {};
  return {
    _key: nextKey(),
    question_text: q.question_text || '',
    question_type: q.question_type,
    is_required: q.is_required,
    scale: cfg.scale || '',
    config: {
      min: Number.isInteger(cfg.min) ? cfg.min : 0,
      max: Number.isInteger(cfg.max) ? cfg.max : 10,
      step: Number.isInteger(cfg.step) ? cfg.step : 1,
      weight: Number.isInteger(cfg.weight) && cfg.weight > 0 ? cfg.weight : 1,
    },
    media: mediaFromBackend(q.media),
    options: [...(q.options || [])]
      .sort((a, b) => a.option_order - b.option_order)
      .map((o) => ({
        _key: nextKey(),
        option_text: o.option_text,
        value_score: o.value_score,
        media: mediaFromBackend(o.media),
      })),
  };
}

export function toBackendQuestion(q, index) {
  const config = {};
  if (q.scale && q.scale.trim()) config.scale = q.scale.trim();
  if (q.question_type === 'scale') {
    config.min = Number(q.config.min);
    config.max = Number(q.config.max);
    if (q.config.step && Number(q.config.step) !== 1) config.step = Number(q.config.step);
  }
  // Вес (weighted scoring): по умолчанию 1 — тогда не пишем в config.
  if (Number(q.config?.weight) > 1) config.weight = Number(q.config.weight);
  const out = {
    question_text: q.question_text.trim(),
    question_order: index,
    question_type: q.question_type,
    is_required: q.is_required,
    config,
    media: mediaToBackend(q.media, true),
    options: [],
  };
  if (hasOptions(q.question_type)) {
    out.options = q.options.map((o, oi) => ({
      option_text: o.option_text.trim(),
      option_order: oi,
      value_score: Number(o.value_score) || 0,
      media: mediaToBackend(o.media, false),
    }));
  }
  return out;
}

// Медиа формы → payload MediaRef[]. caption шлём только для вопроса (у варианта
// изображение декоративно, подписи нет). Пустой список — если картинки нет.
function mediaToBackend(list, withCaption) {
  return (list || [])
    .filter((m) => m && m.media_uuid)
    .map((m) => (withCaption
      ? { media_uuid: m.media_uuid, caption: (m.caption || '').trim() || null }
      : { media_uuid: m.media_uuid }));
}

export function toBackendInterp(it) {
  return {
    scale_name: it.scale_name.trim() || null,
    min_score: Number(it.min_score),
    max_score: Number(it.max_score),
    label: it.label.trim(),
    recommendation: it.recommendation.trim() || null,
  };
}

/**
 * Снимки коллекций в backend-виде — для сравнения «менялось / не менялось».
 *
 * Вопросы теста, по которому уже есть результаты, менять нельзя (backend → 409):
 * student_answers ссылается на questions/options через ON DELETE RESTRICT.
 * Поэтому questions кладутся в PATCH только если реально изменились — иначе
 * переименование такого теста упиралось бы в 409 на ровном месте.
 */
export function snapshotQuestions(questions) {
  return JSON.stringify(questions.map(toBackendQuestion));
}

export function snapshotInterps(interpretations) {
  return JSON.stringify(interpretations.map(toBackendInterp));
}

/**
 * Готов ли вопрос к предпросмотру/анализу. Пустые заготовки шлём на бэк только
 * когда они уже осмысленны — иначе автор получит поток предупреждений, пока
 * набирает первый вопрос.
 */
export function isQuestionComplete(q) {
  if (!q.question_text.trim()) return false;
  if (!hasOptions(q.question_type)) return true;
  return q.options.length >= 2 && q.options.every((o) => o.option_text.trim());
}

/**
 * Дерево формы → вид, который принимает QuestionRenderer (тот же компонент,
 * которым тест видит студент). Отличия от backend-выдачи для прохождения:
 *
 *  - id синтезируются из позиции: у несохранённых вопросов есть только _key,
 *    а рендереру нужны числовые id для name радиогруппы и ключей вариантов;
 *  - value_score НЕ переносится — предпросмотр должен показывать ровно то, что
 *    видит студент, а ключ теста ему не отдаётся (service._strip_take).
 *
 * Порядок совпадает с тем, что уходит в toBackendQuestion (question_order = index).
 */
// Медиа формы → вид для QuestionRenderer (url уже на руках, резолв не нужен).
function mediaToPreview(list) {
  return (list || [])
    .filter((m) => m && m.url)
    .map((m) => ({
      uuid: m.media_uuid, url: m.url, kind: m.kind || 'image', caption: m.caption || null,
    }));
}

export function toPreviewQuestions(questions) {
  return questions.filter(isQuestionComplete).map((q, qi) => ({
    id: qi + 1,
    question_text: q.question_text.trim(),
    question_type: q.question_type,
    is_required: q.is_required,
    config: q.question_type === 'scale'
      ? {
        min: Number(q.config.min),
        max: Number(q.config.max),
        step: Number(q.config.step) || 1,
      }
      : {},
    media: mediaToPreview(q.media),
    options: hasOptions(q.question_type)
      ? q.options.map((o, oi) => ({
        id: (qi + 1) * 1000 + oi,
        option_text: o.option_text.trim(),
        option_order: oi,
        media: mediaToPreview(o.media),
      }))
      : [],
  }));
}

/**
 * Ответы предпросмотра → payload для POST /api/admin/tests/preview-score.
 * Индексы синтетических id обратно превращаются в позиции, потому что бэкенд
 * получает несохранённое дерево и адресует вопросы по question_order.
 */
export function toPreviewAnswers(previewQuestions, answers) {
  return previewQuestions
    .filter((q) => {
      const v = answers[q.id];
      if (q.question_type === 'multiple_choice') return Array.isArray(v) && v.length > 0;
      if (q.question_type === 'free_text') return typeof v === 'string' && v.trim().length > 0;
      return v != null;
    })
    .map((q) => {
      const v = answers[q.id];
      const base = { question_order: q.id - 1 };
      switch (q.question_type) {
        case 'single_choice':
          return { ...base, option_order: q.options.find((o) => o.id === v)?.option_order };
        case 'multiple_choice':
          return {
            ...base,
            selected_option_orders: q.options
              .filter((o) => v.includes(o.id))
              .map((o) => o.option_order),
          };
        case 'scale':
          return { ...base, scale_value: v };
        default:
          return { ...base, free_text_answer: v };
      }
    });
}
