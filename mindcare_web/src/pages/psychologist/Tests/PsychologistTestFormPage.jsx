import TestFormPage from '../../../features/admin/tests/pages/TestFormPage';
import {
  getMyTest, createMyTest, updateMyTest, analyzeMyTest, previewMyScore,
} from '../../../api/tests.api';

/**
 * Конструктор теста психолога (Этап F2) — та же форма/валидация/QuestionBuilder,
 * что у admin, только ownership-scoped api и урезанный набор полей: без выбора
 * статуса при создании (всегда draft — бэк это и так форсирует, форма просто не
 * предлагает выбор), без «Активен» (бессмысленно до публикации), без
 * дублирования (вне цикла F2 — тест с результатами психологу недоступен).
 * warnOnPublishedEdit (Этап F2.1) — предупреждающий баннер при редактировании
 * СВОЕГО published-теста: сохранение снимет его с публикации (status → draft) и
 * потребует повторной модерации; основное предупреждение — диалог-подтверждение
 * ДО входа в форму (PsychologistTestsPage), баннер здесь — на случай прямого
 * перехода по ссылке.
 */
const PSYCHOLOGIST_CONFIG = {
  mode: 'psychologist',
  api: { get: getMyTest, create: createMyTest, update: updateMyTest },
  backPath: '/psychologist/tests',
  showStatusSelect: false,
  showIsActiveToggle: false,
  showDuplicate: false,
  warnOnPublishedEdit: true,
  analyzeFn: analyzeMyTest,
  previewFn: previewMyScore,
};

export default function PsychologistTestFormPage() {
  return <TestFormPage config={PSYCHOLOGIST_CONFIG} />;
}
