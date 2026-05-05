import { useState, useMemo } from 'react';
import { DOW, buildGrid, dateKey } from '../utils/calendarUtils';
import { MOCK_EVENTS } from '../data/mockEvents';
import CalendarDayCell from './CalendarDayCell';
import styles from './CalendarGrid.module.css';

export default function CalendarGrid({ year, month, sessionMap, todayKey, onDaySelect }) {
  const [selectedKey, setSelectedKey] = useState(null);

  const cells = buildGrid(year, month);

  const eventsMap = useMemo(() => {
    const map = {};
    MOCK_EVENTS.forEach(e => {
      if (!map[e.date]) map[e.date] = [];
      map[e.date].push(e.type);
    });
    return map;
  }, []);

  function handleCellClick(cell) {
    const key = dateKey(cell.year, cell.month, cell.day);
    const events = eventsMap[key] || [];
    if (!events.length) {
      setSelectedKey(null);
      onDaySelect?.(null);
      return;
    }
    const next = selectedKey === key ? null : key;
    setSelectedKey(next);
    onDaySelect?.(next);
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
              events={eventsMap[key] || []}
              onClick={() => handleCellClick(cell)}
            />
          );
        })}
      </div>
    </div>
  );
}
