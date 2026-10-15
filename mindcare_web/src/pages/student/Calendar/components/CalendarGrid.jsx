import { DOW, buildGrid, dateKey } from '../utils/calendarUtils';
import CalendarDayCell from './CalendarDayCell';
import styles from './CalendarGrid.module.css';

const POPUP_W = 280;

/**
 * Сетка месяца. Полностью controlled — состояние хранит CalendarPage:
 * `selectedKey` — выбранный день (кольцо), `openKey` — день открытого окна
 * «События дня». Нажатие дня отдаёт наверх `onDayClick(key, pos)` с позицией
 * окна; клик мимо дней — `onDismiss()`.
 */
export default function CalendarGrid({
  year,
  month,
  sessionMap,
  todayKey,
  selectedKey = null,
  openKey = null,
  onDayClick,
  onDismiss,
  containerRef,
  eventsMap = {},
  popupId,
}) {
  const cells = buildGrid(year, month);

  function handleCellClick(cell, e) {
    const key = dateKey(cell.year, cell.month, cell.day);

    let pos = null;
    if (e?.currentTarget && containerRef?.current) {
      const cellRect = e.currentTarget.getBoundingClientRect();
      const contRect = containerRef.current.getBoundingClientRect();
      const cellCenterX = cellRect.left + cellRect.width / 2 - contRect.left;
      const popupLeft = Math.max(8, Math.min(cellCenterX - POPUP_W / 2, contRect.width - POPUP_W - 8));
      pos = {
        top: cellRect.bottom - contRect.top + 10,
        left: popupLeft,
        arrowLeft: cellCenterX - popupLeft,
      };
    }
    onDayClick?.(key, pos);
  }

  // Клик мышью мимо дней месяца (день соседнего месяца, заголовки дней
  // недели) закрывает окно. С клавиатуры окно закрывают «✕» и Escape.
  function handleGridClick(e) {
    if (openKey && !e.target.closest('button')) onDismiss?.();
  }

  return (
    // eslint-disable-next-line jsx-a11y/click-events-have-key-events, jsx-a11y/no-static-element-interactions
    <div className={styles.wrapper} onClick={handleGridClick}>
      <div className={styles.grid}>
        {DOW.map(d => (
          <div key={d} className={styles.dowCell}>{d}</div>
        ))}
        {cells.map((cell, i) => {
          const key = dateKey(cell.year, cell.month, cell.day);
          return (
            <CalendarDayCell
              key={i}
              cell={cell}
              isToday={key === todayKey}
              dotStatus={sessionMap[key]?.status || null}
              isSelected={cell.current && selectedKey === key}
              isOpen={cell.current && openKey === key}
              events={(eventsMap[key] || []).map(ev => ev.type)}
              popupId={popupId}
              onClick={(e) => handleCellClick(cell, e)}
            />
          );
        })}
      </div>
    </div>
  );
}
