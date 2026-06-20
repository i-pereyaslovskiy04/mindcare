import { useState } from 'react';
import { DOW, buildGrid, dateKey } from '../utils/calendarUtils';
import CalendarDayCell from './CalendarDayCell';
import styles from './CalendarGrid.module.css';

const POPUP_W = 280;

export default function CalendarGrid({
  year,
  month,
  sessionMap,
  todayKey,
  onDaySelect,
  containerRef,
  eventsMap = {},
}) {
  const [selectedKey, setSelectedKey] = useState(null);

  const cells = buildGrid(year, month);

  function handleCellClick(cell, e) {
    const key = dateKey(cell.year, cell.month, cell.day);
    const events = eventsMap[key] || [];
    if (!events.length) {
      setSelectedKey(null);
      onDaySelect?.(null, null);
      return;
    }
    const next = selectedKey === key ? null : key;
    setSelectedKey(next);

    let pos = null;
    if (next && e?.currentTarget && containerRef?.current) {
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
    onDaySelect?.(next, pos);
  }

  return (
    <div className={styles.wrapper}>
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
              isSelected={selectedKey === key}
              events={(eventsMap[key] || []).map(ev => ev.type)}
              onClick={(e) => handleCellClick(cell, e)}
            />
          );
        })}
      </div>
    </div>
  );
}
