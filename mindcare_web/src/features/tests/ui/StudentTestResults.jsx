import Button from '../../../components/UI/Button/Button';
import useStaffTestResults from '../hooks/useStaffTestResults';
import useStaffResultView from '../hooks/useStaffResultView';
import { OptionContent, QuestionMedia } from './QuestionRenderer';
import styles from './StudentTestResults.module.css';

function formatDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function pct(score, max) {
  if (score == null || !max) return null;
  return Math.round((score / max) * 100);
}

/**
 * Тело результата: итог/шкалы/интерпретации (тот же состав, что ResultDetailPage)
 * + для сотрудника — снимок правил методики: достоверность и типы (ADR-037).
 */
function ResultBody({ result }) {
  const overall = pct(result.total_score, result.max_possible);
  const summary = result.rule_summary;
  const labels = result.scale_labels || {};
  return (
    <div className={styles.body}>
      {result.total_score != null && (
        <div className={styles.scoreLine}>
          <span className={styles.scoreLabel}>Итоговый балл</span>
          <span className={styles.scoreVal}>
            {result.total_score}
            {result.max_possible != null && <span className={styles.scoreMax}> / {result.max_possible}</span>}
            {overall != null && <span className={styles.pct}> ({overall}%)</span>}
          </span>
        </div>
      )}
      {summary && (
        <dl className={styles.rules}>
          {summary.is_valid != null && (
            <div className={styles.ruleRow}>
              <dt>Достоверность</dt>
              <dd className={summary.is_valid ? undefined : styles.invalid}>
                {summary.is_valid ? 'достоверно' : 'недостоверно'}
              </dd>
            </div>
          )}
          <div className={styles.ruleRow}>
            <dt>Тип</dt>
            <dd>{summary.types.length ? summary.types.join('; ') : 'не выражен'}</dd>
          </div>
        </dl>
      )}
      {result.recommendations && <p className={styles.rec}>{result.recommendations}</p>}
      {result.scales?.length > 0 && (
        <ul className={styles.scales}>
          {result.scales.map((s) => (
            <li key={s.scale_name} className={styles.scale}>
              <span className={styles.scaleName}>{labels[s.scale_name] || s.scale_name}</span>
              <span className={styles.scaleScore}>
                {s.score}{s.max_score != null && ` / ${s.max_score}`}
              </span>
              {s.label && <span className={styles.scaleTag}>{s.label}</span>}
              {s.interpretation && <p className={styles.rec}>{s.interpretation}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

/** Сохранённый ответ на вопрос: выбранные варианты, значение шкалы, текст. */
function AnswerValue({ item }) {
  const hasRange = item.scale_min != null && item.scale_max != null;
  return (
    <div className={styles.answer}>
      {item.options.length > 0 && (
        <ul className={styles.chosen}>
          {item.options.map((option, i) => (
            <li key={`${option.option_text}-${i}`} className={styles.chosenItem}>
              <OptionContent option={option} />
            </li>
          ))}
        </ul>
      )}
      {item.scale_value != null && (
        <p className={styles.answerText}>
          Значение: {item.scale_value}
          {hasRange && <span className={styles.scaleRange}> (шкала {item.scale_min}–{item.scale_max})</span>}
        </p>
      )}
      {item.free_text && <p className={styles.freeText}>{item.free_text}</p>}
    </div>
  );
}

/** Ответы прохождения: вопросы в порядке теста, пропуск — «Нет ответа». */
function ResultAnswers({ data }) {
  return (
    <div className={styles.answers}>
      <p className={styles.answersNote}>
        Вопросы показаны в порядке теста; порядок показа клиенту не сохраняется.
      </p>
      <ol className={styles.answerList}>
        {data.items.map((item) => (
          <li key={item.position} className={styles.answerItem}>
            <p className={styles.question}>
              <span className={styles.qNum}>{item.position}.</span> {item.question_text}
            </p>
            <QuestionMedia media={item.media} label={item.question_text} />
            {item.answered
              ? <AnswerValue item={item} />
              : <p className={styles.noAnswer}>Нет ответа</p>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function ResultPanel({ view, canViewAnswers }) {
  const { detail, answers } = view;
  if (detail.error) return <p className={styles.muted} role="alert">{detail.error}</p>;
  if (!detail.data) return <p className={styles.muted}>Загрузка…</p>;
  return (
    <>
      <ResultBody result={detail.data} />
      {canViewAnswers && (
        <div className={styles.answersBlock}>
          {answers.data ? (
            <>
              <ResultAnswers data={answers.data} />
              <Button type="button" variant="ghost" size="sm" onClick={view.hideAnswers}>
                Скрыть ответы
              </Button>
            </>
          ) : (
            <>
              {answers.error && <p className={styles.muted} role="alert">{answers.error}</p>}
              <Button
                type="button"
                variant="secondary"
                size="sm"
                loading={answers.loading}
                onClick={view.loadAnswers}
              >
                Показать ответы
              </Button>
            </>
          )}
        </div>
      )}
    </>
  );
}

/**
 * Результаты психодиагностики клиента для staff (Этап E, ADR-016).
 * Список — metadata, страницами («Показать ещё»); раскрытие строки грузит
 * полный результат, canViewAnswers (психолог клиента) — и ответы. Чтение
 * результата и ответов фиксируется backend'ом в журнале (503 — данных нет).
 * Потеря доступа (403/404) очищает весь раздел. activeRole → X-Active-Role.
 */
export default function StudentTestResults({ studentUuid, activeRole, canViewAnswers = false }) {
  const list = useStaffTestResults(studentUuid, activeRole);
  const view = useStaffResultView(studentUuid, activeRole, { onAccessLost: list.invalidate });

  if (list.status === 'unavailable') {
    return <p className={styles.muted}>Результаты клиента недоступны.</p>;
  }
  if (list.status === 'error') {
    return (
      <div className={styles.stateRow}>
        <p className={styles.muted} role="alert">Не удалось загрузить результаты.</p>
        <Button type="button" variant="secondary" size="sm" onClick={list.refetch}>
          Повторить
        </Button>
      </div>
    );
  }
  if (list.status === 'loading') return <p className={styles.muted}>Загрузка…</p>;
  if (list.items.length === 0) return <p className={styles.muted}>Пройденных тестов нет.</p>;

  return (
    <>
      <ul className={styles.list}>
        {list.items.map((it) => {
          const open = view.openUuid === it.uuid;
          return (
            <li key={it.uuid} className={styles.item}>
              <button
                type="button"
                className={styles.row}
                onClick={() => view.toggle(it.uuid)}
                aria-expanded={open}
              >
                <span className={styles.title}>{it.test_title || 'Тест'}</span>
                <span className={styles.date}>{formatDate(it.submitted_at)}</span>
              </button>
              {open && (
                <div className={styles.detail}>
                  <ResultPanel view={view} canViewAnswers={canViewAnswers} />
                </div>
              )}
            </li>
          );
        })}
      </ul>
      {list.loadMoreError && (
        <p className={styles.muted} role="alert">
          Не удалось загрузить ещё результаты. Повторите попытку.
        </p>
      )}
      {list.hasMore && (
        <div className={styles.more}>
          <Button
            type="button"
            variant="secondary"
            size="sm"
            loading={list.loadingMore}
            onClick={list.loadMore}
          >
            Показать ещё
          </Button>
        </div>
      )}
    </>
  );
}
