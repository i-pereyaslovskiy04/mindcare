import Modal from '../../../components/Modal/Modal';
import useUserContacts from '../hooks/useUserContacts';
import UserContactsSection from './ContactsReadOnly';
import styles from './UserContactsDialog.module.css';

/**
 * Диалог «Контакты» пользователя для сотрудника (ADR-032). Монтируется только
 * пока диалог нужен: запрос выполняется при открытии, а данные исчезают вместе
 * с закрытием (на странице не остаются). Привязан к uuid, под который загружен.
 */
export default function UserContactsDialog({ userUuid, name, onClose }) {
  const contacts = useUserContacts(userUuid);
  return (
    <Modal
      open
      onClose={onClose}
      ariaLabel={`Контакты: ${name}`}
      size="md"
    >
      <div className={styles.body}>
        <h2 className={styles.title}>Контакты · {name}</h2>
        <UserContactsSection contacts={contacts} />
      </div>
    </Modal>
  );
}
