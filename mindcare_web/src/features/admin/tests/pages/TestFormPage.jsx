import { useState, useEffect, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Select from '../../../../components/UI/Select/Select';
import Checkbox from '../../../../components/UI/Checkbox/Checkbox';
import MultiSelect from '../../../../components/UI/MultiSelect/MultiSelect';
import QuestionBuilder from '../components/QuestionBuilder';
import { fromBackendQuestion, snapshotQuestions, snapshotInterps } from '../lib/testShape';
import InterpretationBuilder from '../components/InterpretationBuilder';
import TestAnalysisPanel from '../components/TestAnalysisPanel';
import TestPreviewModal from '../components/TestPreviewModal';
import { useTestAnalysis } from '../hooks/useTestAnalysis';
import { getAdminTest, createTest, updateTest, duplicateTest } from '../../../../api/tests.api';
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
  const [locked, setLocked]     = useState(false);   // 409: у теста есть результаты
  const [duplicating, setDuplicating] = useState(false);
  const [previewOpen, setPreviewOpen] = useState(false);

  // Исходное состояние дерева при загрузке — база для dirty-tracking.
  const loadedQuestionsRef = useRef(null);
  const loadedInterpsRef   = useRef(null);

  const keyRef = useRef(0);
  const nextKey = useCallback(() => `k${++keyRef.current}`, []);

  // Диапазон баллов и дыры в порогах — считает бэкенд (единственный scoring)
  const analysis = useTestAnalysis({
    scoring: form.scoring,
    questions: form.questions,
    interpretations: form.interpretations,
  });

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
    // Переход на копию меняет только :uuid — компонент не размонтируется,
    // поэтому баннер «есть результаты» и ошибку сбрасываем вручную.
    setLocked(false);
    setError('');
    getAdminTest(uuid)
      .then((t) => {
        if (!alive) return;
        const questions = (t.questions || [])
          .sort((a, b) => a.question_order - b.question_order)
          .map((q) => fromBackendQuestion(q, nextKey));
        const interpretations = (t.interpretations || []).map((it) => ({
          _key: nextKey(),
          scale_name: it.scale_name || '',
          min_score: it.min_score,
          max_score: it.max_score,
          label: it.label || '',
          recommendation: it.recommendation || '',
        }));
        loadedQuestionsRef.current = snapshotQuestions(questions);
        loadedInterpsRef.current   = snapshotInterps(interpretations);
        setForm({
          title: t.title || '',
          description: t.description || '',
          scoring: t.scoring || 'sum',
          time_limit_min: t.time_limit_min ?? '',
          is_active: t.is_active,
          category_ids: t.categories?.map((c) => c.id) || [],
          tag_uuids: t.tags?.map((tg) => tg.uuid) || [],
          questions,
          interpretations,
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
    setLocked(false);

    const payload = {
      title: form.title.trim(),
      description: form.description.trim() || null,
      scoring: form.scoring,
      time_limit_min: form.time_limit_min === '' ? null : Number(form.time_limit_min),
      is_active: form.is_active,
      category_ids: form.category_ids,
      tag_uuids: form.tag_uuids,
    };

    // При редактировании неизменённые коллекции не отправляем: PATCH частичный,
    // а замена вопросов теста с результатами отвергается бэкендом (409).
    const questions = snapshotQuestions(form.questions);
    const interps   = snapshotInterps(form.interpretations);
    if (!isEdit || questions !== loadedQuestionsRef.current) {
      payload.questions = JSON.parse(questions);
    }
    if (!isEdit || interps !== loadedInterpsRef.current) {
      payload.interpretations = JSON.parse(interps);
    }

    try {
      if (isEdit) await updateTest(uuid, payload);
      else await createTest(payload);
      navigate('/admin/tests');
    } catch (err) {
      if (err?.status === 409) setLocked(true);
      setError(err.message || 'Не удалось сохранить тест');
      setSubmitting(false);
    }
  }

  async function handleDuplicate() {
    if (duplicating) return;
    setDuplicating(true);
    setError('');
    try {
      const copy = await duplicateTest(uuid);
      navigate(`/admin/tests/${copy.uuid}`);
    } catch (err) {
      setError(err.message || 'Не удалось создать копию теста');
      setDuplicating(false);
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

      {error && !locked && <p className={styles.error}>{error}</p>}

      {locked && (
        <div className={styles.lockedNotice} role="alert">
          <p className={styles.lockedText}>
            По этому тесту уже есть пройденные результаты, поэтому его вопросы
            изменить нельзя — иначе ответы студентов потеряли бы смысл.
            Создайте копию методики и правьте её: копия сохранится черновиком
            и не появится в каталоге, пока вы её не активируете.
          </p>
          <Button variant="primary" onClick={handleDuplicate} loading={duplicating}>
            Создать копию и править её
          </Button>
        </div>
      )}

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

        <TestAnalysisPanel
          data={analysis.data}
          loading={analysis.loading}
          error={analysis.error}
        />
      </section>

      <div className={styles.footer}>
        <Button variant="secondary" onClick={() => navigate('/admin/tests')} disabled={submitting}>
          Отмена
        </Button>
        <Button
          variant="secondary"
          onClick={() => setPreviewOpen(true)}
          disabled={form.questions.length === 0}
        >
          Предпросмотр
        </Button>
        {isEdit && (
          <Button variant="secondary" onClick={handleDuplicate} loading={duplicating}>
            Дублировать
          </Button>
        )}
        <Button variant="primary" onClick={handleSubmit} loading={submitting}>
          {isEdit ? 'Сохранить изменения' : 'Создать тест'}
        </Button>
      </div>

      {previewOpen && (
        <TestPreviewModal
          title={form.title}
          description={form.description}
          scoring={form.scoring}
          questions={form.questions}
          interpretations={form.interpretations}
          onClose={() => setPreviewOpen(false)}
        />
      )}
    </div>
  );
}
