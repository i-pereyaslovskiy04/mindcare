import Icon from '../../../../components/Icon/Icon';
import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import Tag from '../../../../components/UI/Tag/Tag';
import styles from './TestsTable.module.css';

const SKELETON_ROWS = 6;
const SCORING_LABEL = { sum: 'Сумма баллов', average: 'Среднее', weighted: 'Взвешенная сумма' };

const STATUS_LABEL = {
  draft: 'Черновик', in_review: 'На проверке',
  published: 'Опубликован', needs_changes: 'Нужны правки',
};
const STATUS_TONE = {
  draft: 'neutral', in_review: 'warning',
  published: 'success', needs_changes: 'error',
};

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

function SkeletonRow() {
  return (
    <tr>
      {Array.from({ length: 7 }, (_, i) => (
        <td key={i}><span className={styles.skeletonCell} /></td>
      ))}
    </tr>
  );
}

/**
 * Переиспользуется в /admin/tests (все тесты, полные права) и в
 * /psychologist/tests (Этап F2 — только свои, редактирование заперто на
 * draft/needs_changes). Статус-бейдж виден всегда — он часть модели тестов, а
 * не admin-специфика. Действия модерации: onPublish/onReturn — admin/supervisor
 * (роутер их и так гейтит); onSubmitForReview — автор отправляет свой
 * draft/needs_changes на проверку. `restrictEditToStatuses` (если передан) —
 * набор статусов, при которых видны «Редактировать»/«Удалить» (для psychologist
 * — только draft/needs_changes); без пропа ограничений нет (admin).
 */
export default function TestsTable({
  items, loading, error, onPreview, onEdit, onDelete,
  onPublish, onReturn, onSubmitForReview, restrictEditToStatuses,
}) {
  const canEditRow = (item) =>
    !restrictEditToStatuses || restrictEditToStatuses.includes(item.status);

  return (
    <div className={styles.wrapper}>
      <table className={styles.table}>
        <thead>
          <tr>
            <th>Название</th>
            <th>Вопросов</th>
            <th>Подсчёт</th>
            <th>Модерация</th>
            <th>Видимость</th>
            <th>Создан</th>
            <th aria-label="Действия" />
          </tr>
        </thead>
        <tbody>
          {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => <SkeletonRow key={i} />)}

          {!loading && error && (
            <tr>
              <td colSpan={7} className={styles.stateCell}>
                <span className={styles.errorText}>Ошибка загрузки: {error}</span>
              </td>
            </tr>
          )}

          {!loading && !error && items.length === 0 && (
            <tr>
              <td colSpan={7} className={styles.stateCell}>Тестов пока нет</td>
            </tr>
          )}

          {!loading && !error && items.map((item) => (
            <tr key={item.uuid} className={styles.row}>
              <td>
                <span className={styles.title}>{item.title}</span>
                {item.categories?.length > 0 && (
                  <div className={styles.tags}>
                    {item.categories.map((c) => (
                      <Tag key={c.id} variant="category">{c.name}</Tag>
                    ))}
                  </div>
                )}
                {item.created_by_name && (
                  <span className={styles.meta}>{item.created_by_name}</span>
                )}
              </td>
              <td className={styles.num}>{item.question_count}</td>
              <td className={styles.scoring}>{SCORING_LABEL[item.scoring] || item.scoring}</td>
              <td>
                <Badge tone={STATUS_TONE[item.status] || 'neutral'}>
                  {STATUS_LABEL[item.status] || item.status}
                </Badge>
              </td>
              <td>
                <Badge tone={item.is_active ? 'success' : 'warning'}>
                  {item.is_active ? 'Активен' : 'Скрыт'}
                </Badge>
              </td>
              <td className={styles.date}>{formatDate(item.created_at)}</td>
              <td className={styles.actionsCell}>
                <div className={styles.actions}>
                  {onPublish && item.status !== 'published' && (
                    <Button
                      type="button"
                      variant="icon"
                      size="sm"
                      tone="success"
                      onClick={() => onPublish(item)}
                      aria-label={`Опубликовать «${item.title}»`}
                      title="Опубликовать"
                    >
                      <Icon name="check" size={15} />
                    </Button>
                  )}
                  {onReturn && item.status === 'in_review' && (
                    <Button
                      type="button"
                      variant="icon"
                      size="sm"
                      onClick={() => onReturn(item)}
                      aria-label={`Вернуть «${item.title}» на доработку`}
                      title="Вернуть на доработку"
                    >
                      <Icon name="undo" size={15} />
                    </Button>
                  )}
                  {onSubmitForReview && (item.status === 'draft' || item.status === 'needs_changes') && (
                    <Button
                      type="button"
                      variant="icon"
                      size="sm"
                      tone="success"
                      onClick={() => onSubmitForReview(item)}
                      aria-label={`Отправить «${item.title}» на модерацию`}
                      title="Отправить на модерацию"
                    >
                      <Icon name="send" size={15} />
                    </Button>
                  )}
                  <Button
                    type="button"
                    variant="icon"
                    size="sm"
                    onClick={() => onPreview(item)}
                    aria-label={`Предпросмотр «${item.title}»`}
                    title="Предпросмотр"
                  >
                    <Icon name="eye" size={15} />
                  </Button>
                  {canEditRow(item) && (
                    <Button
                      variant="icon"
                      size="sm"
                      onClick={() => onEdit(item)}
                      aria-label={`Редактировать «${item.title}»`}
                      title="Редактировать"
                    >
                      <Icon name="edit" size={15} />
                    </Button>
                  )}
                  {canEditRow(item) && (
                    <Button
                      variant="icon"
                      size="sm"
                      tone="danger"
                      onClick={() => onDelete(item)}
                      aria-label={`Удалить «${item.title}»`}
                      title="Удалить"
                    >
                      <Icon name="trash" size={15} />
                    </Button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
