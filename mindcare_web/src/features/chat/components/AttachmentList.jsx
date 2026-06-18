import AttachmentCard from './AttachmentCard';
import styles from './AttachmentList.module.css';

/**
 * Вертикальный список карточек вложений внутри bubble (Stage 32d).
 * Возвращает null, если вложений нет.
 *
 * Props:
 *   attachments           — массив нормализованных attachment-объектов
 *   onDownloadAttachment  — async (attachment) => { blob, filename } | null
 */
export default function AttachmentList({ attachments, onDownloadAttachment, outgoing = false }) {
  if (!attachments || attachments.length === 0) return null;

  return (
    <div className={styles.list}>
      {attachments.map((att) => (
        <AttachmentCard
          key={att.uuid || att.originalFilename || String(Math.random())}
          attachment={att}
          onDownload={onDownloadAttachment}
          disabled={!onDownloadAttachment}
          outgoing={outgoing}
        />
      ))}
    </div>
  );
}
