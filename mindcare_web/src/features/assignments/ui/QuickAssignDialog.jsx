import Modal from '../../../components/Modal/Modal';
import useAssignmentCreate from '../hooks/useAssignmentCreate';
import AssignmentForm from './AssignmentForm';
import styles from './QuickAssignDialog.module.css';

/**
 * Быстрая выдача задания из списка «Мои студенты» — без перехода в карточку.
 * Только создание: список заданий клиента не запрашивается (и чтение
 * содержимого в журнал не пишется). После успеха диалог закрывается и
 * вызывающий показывает подтверждение (onCreated).
 *
 * student: { student_uuid, full_name }.
 */
export default function QuickAssignDialog({ student, onClose, onCreated }) {
  const { create, submitting, formError } = useAssignmentCreate(student.student_uuid, {
    onCreated: () => onCreated?.(student),
  });
  const title = `Задание: ${student.full_name}`;

  return (
    <Modal open onClose={submitting ? () => {} : onClose} ariaLabel={title} size="md" zIndex={2200}>
      <div className={styles.body}>
        <h2 className={styles.title}>{title}</h2>
        <p className={styles.text}>
          Задание появится у клиента в разделе «Задания психолога». Список и статусы — в карточке клиента.
        </p>
        <AssignmentForm
          onCreate={create}
          submitting={submitting}
          formError={formError}
          title={null}
          bare
        />
      </div>
    </Modal>
  );
}
