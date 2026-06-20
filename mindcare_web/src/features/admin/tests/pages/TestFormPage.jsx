import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import QuestionBuilder from '../components/QuestionBuilder';
import InterpretationBuilder from '../components/InterpretationBuilder';
import { getAdminTest, createTest, updateTest } from '../../../../api/tests.api';
import { getAdminCategories } from '../../../../api/articles.api';
import { getTagsPublic } from '../../../../api/tags.api';
import styles from './TestFormPage.module.css';

const SCORING_OPTIONS = [
  { value: 'sum',     label: 'Сумма баллов' },
  { value: 'average', label: 'Среднее значение' },
];

const EMPTY = {
  title: '',
  description: '',
  scoring: 'sum',
  time_limit_min: '',
  is_active: true,
  category_ids: [],
  tag_uuids: [],
  questions: [],
  interpretations: [],
};

// ── трансформации form ⇄ backend ──────────────────────────────────────────────

function fromBackendQuestion(q, nextKey) {
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
    },
    options: [...(q.options || [])]
      .sort((a, b) => a.option_order - b.option_order)
      .map((o) => ({ _key: nextKey(), option_text: o.option_text, value_score: o.value_score })),
  };
}

function toBackendQuestion(q, index) {
  const config = {};
  if (q.scale && q.scale.trim()) config.scale = q.scale.trim();
  if (q.question_type === 'scale') {
    config.min = Number(q.config.min);
    config.max = Number(q.config.max);
    if (q.config.step && Number(q.config.step) !== 1) config.step = Number(q.config.step);
  }
  const out = {
    question_text: q.question_text.trim(),
    question_order: index,
    question_type: q.question_type,
    is_required: q.is_required,
    config,
    options: [],
  };
  if (q.question_type === 'single_choice' || q.question_type === 'multiple_choice') {
    out.options = q.options.map((o, oi) => ({
      option_text: o.option_text.trim(),
      option_order: oi,
      value_score: Number(o.value_score) || 0,
    }));
  }
  return out;
}

function toBackendInterp(it) {
  return {
    scale_name: it.scale_name.trim() || null,
    min_score: Number(it.min_score),
    max_score: Number(it.max_score),
    label: it.label.trim(),
    recommendation: it.recommendation.trim() || null,
  };
}

export default function TestFormPage() {
  const { uuid } = useParams();
  const navigate = useNavigate();
  const isEdit = Boolean(uuid);

  const [form, setForm]         = useState(EMPTY);
  const [catOptions, setCatOptions] = useState([]);
  const [tagOptions, setTagOptions] = useState([]);
  const [loading, setLoading]   = useState(isEdit);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError]       = useState('');

  const keyRef = useRef(0);
  const nextKey = useCallback(() => `k${++keyRef.current}`, []);

  // справочники категорий/тегов
  useEffect(() => {
    Promise.all([getAdminCategories(), getTagsPublic()])
      .then(([cats, tags]) => {
        setCatOptions((cats || []).map((c) => ({ value: c.id, label: c.name })));
        setTagOptions((tags || []).map((t) => ({ value: t.uuid, label: t.name })));
      })
      .catch(() => {});
  }, []);

  // загрузка теста при редактировании
  useEffect(() => {
    if (!isEdit) return;
    let alive = true;
    setLoading(true);
    getAdminTest(uuid)
      .then((t) => {
        if (!alive) return;
        setForm({
          title: t.title || '',
          description: t.description || '',
          scoring: t.scoring || 'sum',
          time_limit_min: t.time_limit_min ?? '',
          is_active: t.is_active,
          category_ids: t.categories?.map((c) => c.id) || [],
          tag_uuids: t.tags?.map((tg) => tg.uuid) || [],
          questions: (t.questions || [])
            .sort((a, b) => a.question_order - b.question_order)
            .map((q) => fromBackendQuestion(q, nextKey)),
          interpretations: (t.interpretations || []).map((it) => ({
            _key: nextKey(),
            scale_name: it.scale_name || '',
            min_score: it.min_score,
            max_score: it.max_score,
            label: it.label || '',
            recommendation: it.recommendation || '',
          })),
        });
      })
      .catch((err) => { if (alive) setError(`Не удалось загрузить тест: ${err.message}`); })
      .finally(() => { if (alive) setLoading(false); });
    return () => { alive = false; };
  }, [isEdit, uuid, nextKey]);

  const set = (field, value) => setForm((prev) => ({ ...prev, [field]: value }));

  async function handleSubmit() {
    if (!form.title.trim()) { setError('Введите название теста'); return; }
    if (submitting) return;
    setSubmitting(true);
    setError('');

    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      scoring: form.scoring,
      time_limit_min: form.time_limit_min === '' ? null : Number(form.time_limit_min),
      is_active: form.is_active,
      category_ids: form.category_ids,
      tag_uuids: form.tag_uuids,
      questions: form.questions.map(toBackendQuestion),
      interpretations: form.interpretations.map(toBackendInterp),
    };

    try {
      if (isEdit) await updateTest(uuid, payload);
      else await createTest(payload);
      navigate('/admin/tests');
    } catch (err) {
      setError(err.message || 'Не удалось сохранить тест');
      setSubmitting(false);
    }
  }

  if (loading) {
    return <div className={styles.page}><p className={styles.muted}>Загрузка…</p></div>;
  }

  return (
    <div className={styles.page}>
      <button className={styles.back} type="button" onClick={() => navigate('/admin/tests')}>
        <Icon name="chevron-left" size={14} /> К списку тестов
      </button>

      <h1 className={styles.title}>{isEdit ? 'Редактирование теста' : 'Новый тест'}</h1>

      {error && <p className={styles.error}>{error}</p>}

      {/* ── Основное ── */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Основное</h2>

        <div className={styles.field}>
          <label className={styles.label}>Название *</label>
          <input
            className={styles.input}
            value={form.title}
            onChange={(e) => set('title', e.target.value)}
            placeholder="напр. Шкала депрессии PHQ-9"
          />
        </div>

        <div className={styles.field}>
          <label className={styles.label}>Описание</label>
          <textarea
            className={styles.textarea}
            rows={3}
            value={form.description}
            onChange={(e) => set('description', e.target.value)}
            placeholder="Краткое описание методики для студента"
          />
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <Select
              label="Метод подсчёта"
              value={form.scoring}
              options={SCORING_OPTIONS}
              onChange={(val) => set('scoring', val)}
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Лимит времени, мин (необязательно)</label>
            <input
              className={styles.input}
              type="number"
              min={0}
              value={form.time_limit_min}
              onChange={(e) => set('time_limit_min', e.target.value)}
              placeholder="без лимита"
            />
          </div>
        </div>

        <div className={styles.row}>
          <div className={styles.field}>
            <label className={styles.label}>Типы материалов</label>
            <MultiSelect
              options={catOptions}
              value={form.category_ids}
              onChange={(val) => set('category_ids', val)}
              placeholder="Не выбрано"
            />
          </div>
          <div className={styles.field}>
            <label className={styles.label}>Темы</label>
            <MultiSelect
              options={tagOptions}
              value={form.tag_uuids}
              onChange={(val) => set('tag_uuids', val)}
              placeholder="Не выбрано"
            />
          </div>
        </div>

        <div className={styles.field}>
          <Checkbox
            checked={form.is_active}
            onChange={(checked) => set('is_active', checked)}
            label="Активен — виден студентам в каталоге"
          />
        </div>
      </section>

      {/* ── Вопросы ── */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>
          Вопросы <span className={styles.sectionMeta}>· {form.questions.length}</span>
        </h2>
        <QuestionBuilder
          questions={form.questions}
          onChange={(q) => set('questions', q)}
          nextKey={nextKey}
        />
      </section>

      {/* ── Интерпретация ── */}
      <section className={styles.section}>
        <h2 className={styles.sectionTitle}>Интерпретация результатов</h2>
        <p className={styles.sectionHint}>
          Диапазоны баллов и их расшифровка. Оставьте поле «Шкала» пустым для интерпретации
          по итоговому баллу теста; укажите название шкалы для многошкальных тестов.
        </p>
        <InterpretationBuilder
          items={form.interpretations}
          onChange={(it) => set('interpretations', it)}
          nextKey={nextKey}
        />
      </section>

      <div className={styles.footer}>
        <Button variant="secondary" onClick={() => navigate('/admin/tests')} disabled={submitting}>
          Отмена
        </Button>
        <Button variant="primary" onClick={handleSubmit} loading={submitting}>
          {isEdit ? 'Сохранить изменения' : 'Создать тест'}
        </Button>
      </div>
    </div>
  );
}
