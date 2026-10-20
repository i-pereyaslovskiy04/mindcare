import Icon from '../../../components/Icon/Icon';
import styles from './DragDropOverlay.module.css';

/**
 * Semi-transparent overlay shown while dragging files over ChatWindow.
 * position: absolute; pointer-events: none — events pass through to ChatWindow.
 */
export default function DragDropOverlay({ visible }) {
  if (!visible) return null;

  return (
    <div className={styles.overlay} role="status" aria-live="polite">
      <Icon name="file" size={36} aria-hidden="true" className={styles.icon} />
      <p className={styles.title}>Перетащите файлы сюда</p>
      <p className={styles.subtitle}>Они будут добавлены к сообщению</p>
    </div>
  );
}
