import TableShell from '../TableShell/TableShell';
import styles from './ResponsiveTable.module.css';

const SKELETON_ROWS = 7;
const SKELETON_ITEMS = 4;

/**
 * Адаптивное представление списка записей: одни данные — три режима по
 * ширине колонки контента (container query, не viewport; границы — в
 * ResponsiveTable.module.css):
 *   wide    — семантическая таблица (TableShell);
 *   compact — список строк: основное + вторичное | статус | действие ⋮,
 *             под ними детали одной строкой;
 *   mobile  — та же строка вертикальнее: основное и ⋮, статус, детали и
 *             основное действие. Это же — fallback без container queries.
 * Компонент отвечает только за раскладку. Что показать, решает фича:
 *
 *   label     — подпись таблицы (caption) и списка (aria-label);
 *   items, getKey;
 *   loading, error (готовый текст), emptyText — состояния;
 *   isMuted(item)  — приглушить данные записи (действия не приглушаются);
 *   identity  — { header, primary(item), secondary?(item) }: первая колонка
 *               и заголовок записи списка (h2);
 *   status    — { header, width?, render(item) }: метки — вторая колонка и
 *               область статуса записи;
 *   columns   — [{ key, header, width?, render(item) }]: прочие колонки
 *               таблицы (только wide);
 *   meta(item) — [{ label, value }]: детали записи списка (dl);
 *   actions   — { primary?(item), menu?(item) }: основное действие и меню
 *               «⋮» (готовые элементы фичи; права и обработчики — в фиче).
 *
 * Обе раскладки в DOM, скрытая — display: none (вне дерева доступности);
 * переключение ширины не делает запросов и не сбрасывает состояние.
 */
export default function ResponsiveTable({
  label, items, getKey, loading = false, error = null, emptyText,
  isMuted, identity, status, columns = [], meta, actions = {},
}) {
  const props = { label, items, getKey, loading, error, emptyText, isMuted, identity, status, columns, meta, actions };
  return (
    <div className={styles.root}>
      <div className={styles.wide}><WideTable {...props} /></div>
      <div className={styles.list}><RecordList {...props} /></div>
    </div>
  );
}

function ActionsArea({ item, actions }) {
  return (
    <div className={styles.actions}>
      {actions.primary && <div className={styles.actionPrimary}>{actions.primary(item)}</div>}
      {actions.menu && <div className={styles.actionMenu}>{actions.menu(item)}</div>}
    </div>
  );
}

function WideTable({
  label, items, getKey, loading, error, emptyText, isMuted, identity, status, columns, actions,
}) {
  const hasActions = Boolean(actions.primary || actions.menu);
  const colCount = 1 + (status ? 1 : 0) + columns.length + (hasActions ? 1 : 0);

  return (
    <TableShell caption={label} tableClassName={styles.table}>
      <thead>
        <tr>
          <th scope="col" className={styles.identityCol}>{identity.header}</th>
          {status && <th scope="col" style={{ width: status.width }}>{status.header}</th>}
          {columns.map((col) => (
            <th key={col.key} scope="col" style={{ width: col.width }}>{col.header}</th>
          ))}
          {hasActions && (
            <th scope="col" className={styles.actionsCol}>
              <span className="visually-hidden">Действия</span>
            </th>
          )}
        </tr>
      </thead>
      <tbody>
        {loading && Array.from({ length: SKELETON_ROWS }, (_, i) => (
          <tr key={i}>
            {Array.from({ length: colCount }, (__, j) => (
              <td key={j}><span className={styles.skeletonCell} /></td>
            ))}
          </tr>
        ))}

        {!loading && error && (
          <tr><td colSpan={colCount} className={`${styles.stateCell} ${styles.errorText}`}>{error}</td></tr>
        )}

        {!loading && !error && items.length === 0 && (
          <tr><td colSpan={colCount} className={styles.stateCell}>{emptyText}</td></tr>
        )}

        {!loading && !error && items.map((item) => (
          <tr key={getKey(item)} className={`${styles.row}${isMuted?.(item) ? ` ${styles.muted}` : ''}`}>
            <td>
              <span className={styles.primary}>{identity.primary(item)}</span>
              {identity.secondary && <span className={styles.secondary}>{identity.secondary(item)}</span>}
            </td>
            {status && <td><div className={styles.statusContent}>{status.render(item)}</div></td>}
            {columns.map((col) => <td key={col.key}>{col.render(item)}</td>)}
            {hasActions && (
              <td className={styles.actionsCell}><ActionsArea item={item} actions={actions} /></td>
            )}
          </tr>
        ))}
      </tbody>
    </TableShell>
  );
}

function RecordList({
  label, items, getKey, loading, error, emptyText, isMuted, identity, status, meta, actions,
}) {
  if (loading) {
    return (
      <ul className={styles.records} aria-busy="true" aria-label={label}>
        {Array.from({ length: SKELETON_ITEMS }, (_, i) => (
          <li key={i} className={styles.skeletonRecord}>
            <span className={styles.skeletonLine} />
            <span className={`${styles.skeletonLine} ${styles.skeletonShort}`} />
          </li>
        ))}
      </ul>
    );
  }

  if (error) return <p className={`${styles.state} ${styles.errorText}`}>{error}</p>;
  if (items.length === 0) return <p className={styles.state}>{emptyText}</p>;

  return (
    <ul className={styles.records} aria-label={label}>
      {items.map((item) => {
        const rows = meta ? meta(item) : [];
        return (
          <li key={getKey(item)} className={`${styles.record}${isMuted?.(item) ? ` ${styles.muted}` : ''}`}>
            <div className={styles.identity}>
              <h2 className={styles.primary}>{identity.primary(item)}</h2>
              {identity.secondary && <span className={styles.secondary}>{identity.secondary(item)}</span>}
            </div>
            {status && <div className={`${styles.statusArea} ${styles.statusContent}`}>{status.render(item)}</div>}
            {rows.length > 0 && (
              <dl className={styles.meta}>
                {rows.map((row) => (
                  <div key={row.label} className={styles.metaRow}>
                    <dt>{row.label}</dt>
                    <dd>{row.value}</dd>
                  </div>
                ))}
              </dl>
            )}
            {actions.primary && <div className={styles.recordPrimary}>{actions.primary(item)}</div>}
            {actions.menu && <div className={styles.recordMenu}>{actions.menu(item)}</div>}
          </li>
        );
      })}
    </ul>
  );
}
