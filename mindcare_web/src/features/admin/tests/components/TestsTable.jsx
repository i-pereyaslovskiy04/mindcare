import Button from '../../../../components/UI/Button/Button';
import Badge from '../../../../components/UI/Badge/Badge';
import ResponsiveTable from '../../../../components/UI/ResponsiveTable/ResponsiveTable';
import ActionsMenu from '../../../../components/UI/ActionsMenu/ActionsMenu';
import TagList from '../../../../components/UI/TagList/TagList';
import { getTestActions } from '../lib/testActions';
import styles from './TestsTable.module.css';

const SCORING_LABEL = { sum: 'Сумма баллов', average: 'Среднее', weighted: 'Взвешенная сумма' };

const STATUS_LABEL = {
  draft: 'Черновик', in_review: 'На проверке',
  published: 'Опубликован', needs_changes: 'Нужны правки',
};
const STATUS_TONE = {
  draft: 'neutral', in_review: 'warning',
  published: 'success', needs_changes: 'error',
};

// Типов материалов видно до «+N».
const TYPES_VISIBLE = 2;

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU');
}

const scoringLabel = (item) => SCORING_LABEL[item.scoring] || item.scoring;

function Types({ item }) {
  return (
    <TagList
      items={item.categories.map((c) => ({ key: c.id, label: c.name }))}
      maxVisible={TYPES_VISIBLE}
      label="Тип"
      variant="category"
    />
  );
}

/**
 * Список тестов на shared ResponsiveTable — один компонент для /admin/tests,
 * /supervisor/tests (context 'moderator') и /psychologist/tests (context
 * 'author', только свои тесты). Здесь только содержимое, раскладку wide /
 * compact / mobile задаёт ResponsiveTable; какие действия доступны и какое
 * из них основное — доменная матрица lib/testActions.js.
 *   wide — Тест (название, автор · создан) | Модерация и видимость |
 *          Параметры (тип, вопросов, подсчёт) | действия;
 *   compact/mobile — параметры уходят строкой деталей.
 * Бейджи модерации и видимости — два разных смысла, оба подписаны текстом.
 * pending — { [actionId]: uuid } выполняющихся действий (см. testActions).
 */
export default function TestsTable({
  items, loading, error, context, pending,
  onPreview, onEdit, onDelete, onPublish, onReturn, onSubmitForReview, onToggleActive,
}) {
  const actionsOf = (item) => getTestActions(item, {
    context, pending, onPreview, onEdit, onDelete, onPublish, onReturn, onSubmitForReview, onToggleActive,
  });

  return (
    <ResponsiveTable
      label="Тесты"
      items={items}
      getKey={(item) => item.uuid}
      loading={loading}
      error={error ? `Ошибка загрузки: ${error}` : null}
      emptyText="Тестов пока нет"
      identity={{
        header: 'Тест',
        primary: (item) => item.title,
        secondary: (item) => (
          <>
            {item.created_by_name && (
              <>
                {item.created_by_name}
                <span aria-hidden="true"> · </span>
              </>
            )}
            <span className={styles.nowrap}>создан {formatDate(item.created_at)}</span>
          </>
        ),
      }}
      status={{
        header: 'Модерация и видимость',
        render: (item) => (
          <>
            <Badge tone={STATUS_TONE[item.status] || 'neutral'}>
              {STATUS_LABEL[item.status] || item.status}
            </Badge>
            <Badge tone={item.is_active ? 'success' : 'warning'}>
              {item.is_active ? 'Активен' : 'Скрыт'}
            </Badge>
          </>
        ),
      }}
      columns={[
        {
          key: 'params',
          header: 'Параметры',
          width: '13rem',
          render: (item) => (
            <div className={styles.params}>
              {item.categories?.length > 0 && <Types item={item} />}
              <span className={styles.paramsText}>
                <span className={styles.nowrap}>Вопросов: {item.question_count}</span>
                <span aria-hidden="true"> · </span>
                <span className={styles.nowrap}>{scoringLabel(item)}</span>
              </span>
            </div>
          ),
        },
      ]}
      meta={(item) => [
        ...(item.categories?.length > 0 ? [{ label: 'Тип', value: <Types item={item} /> }] : []),
        { label: 'Вопросов', value: item.question_count },
        { label: 'Подсчёт', value: scoringLabel(item) },
      ]}
      actions={{
        primary: (item) => {
          const { primary } = actionsOf(item);
          if (!primary) return null;
          return (
            <Button
              type="button"
              variant={primary.variant}
              size="sm"
              onClick={primary.onSelect}
              disabled={primary.disabled}
              aria-busy={primary.disabled || undefined}
              aria-label={`${primary.label} «${item.title}»`}
            >
              {primary.label}
            </Button>
          );
        },
        menu: (item) => (
          <ActionsMenu
            triggerLabel={`Другие действия: «${item.title}»`}
            items={actionsOf(item).menu}
          />
        ),
      }}
    />
  );
}
