import { useEffect } from 'react';
import Icon from '../../components/Icon';
import styles from './SessionPopover.module.css';

export default function SessionPopover({ session, style, arrowLeft, onClose }) {
  useEffect(() => {
    const handle = e => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', handle);
    return () => window.removeEventListener('keydown', handle);
  }, [onClose]);

  return (
    <>
      <div className={styles.overlay} onClick={onClose} />
      <div className={styles.popover} style={style} role="dialog" aria-modal="true">
        <div className={styles.arrow} style={{ left: arrowLeft }} />
        <div className={styles.head}>
          <span className={styles.chip}>
            <Icon name="video" size={13} />
            Видео
          </span>
          <button className={styles.closeBtn} onClick={onClose} aria-label="Закрыть">✕</button>
        </div>
        <p className={styles.title}>{session.title}</p>
        <p className={styles.meta}>{session.psychologist}</p>
        <p className={styles.time}>{session.time}</p>
        {session.desc && <p className={styles.desc}>{session.desc}</p>}
        {session.status === 'upcoming' && (
          <button className={styles.joinBtn}>Присоединиться</button>
        )}
      </div>
    </>
  );
}
