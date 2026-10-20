import TestFormPage from '../../../features/admin/tests/pages/TestFormPage';
import {
  getMyTest, createMyTest, updateMyTest, duplicateMyTest, analyzeMyTest, previewMyScore,
} from '../../../api/tests.api';

/**
 * Конструктор теста психолога (Этап F2) — та же форма/валидация/QuestionBuilder,
 * что у admin, только ownership-scoped api и урезанный набор полей: без выбора
 * статуса при создании (всегда draft — бэк это и так форсирует, форма просто не
 * предлагает выбор), без «Активен» (бессмысленно до публикации).
 * Дублирование (Этап F2.2) — включено: своя копия любого статуса источника
 * (включая published/in_review), через ownership-scoped duplicateMyTest.
 * Заодно делает осмысленным 409-баннер «есть результаты, создайте копию» —
 * до F2.2 у психолога не было работающей кнопки, и баннер скрывался.
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
  showDuplicate: true,
  duplicateFn: duplicateMyTest,
  warnOnPublishedEdit: true,
  analyzeFn: analyzeMyTest,
  previewFn: previewMyScore,
};

export default function PsychologistTestFormPage() {
  return <TestFormPage config={PSYCHOLOGIST_CONFIG} />;
}
