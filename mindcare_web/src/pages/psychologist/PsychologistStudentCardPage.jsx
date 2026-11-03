import { useEffect, useState } from 'react';
import { useParams, Link } from 'react-router-dom';
import Icon from '../../components/Icon/Icon';
import Badge from '../../components/UI/Badge/Badge';
import Button from '../../components/UI/Button/Button';
import { getInitials } from '../../shared/lib/utils';
import { useStudentCard } from '../../features/psychologist/hooks/useStudentCard';
import { getPsychologistStudentChatPath } from '../../features/psychologist/chatLinks';
import StudentTestResults from '../../features/tests/ui/StudentTestResults';
import ClientMeetings from '../../features/psychologist/ui/ClientMeetings';
import ClientNotes from '../../features/psychologist/ui/ClientNotes';
import useScrollToHash, { scrollToSection } from '../../hooks/useScrollToHash';
import ClientAssignments from '../../features/assignments/ui/ClientAssignments';
import useUserContacts from '../../features/contacts/hooks/useUserContacts';
import UserContactsSection from '../../features/contacts/ui/ContactsReadOnly';
import styles from './PsychologistStudentCardPage.module.css';

function formatDate(iso) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('ru-RU', {
    day: 'numeric', month: 'long', year: 'numeric',
  });
}

function getDuration(iso) {
  if (!iso) return null;
  const days = Math.floor((Date.now() - new Date(iso).getTime()) / 86_400_000);
  if (days < 1)  return 'Сегодня';
  if (days === 1) return '1 день';
  if (days < 5)  return `${days} дня`;
  return `${days} дней`;
}

const FUTURE_ITEMS = [
  'Запрос супервизии',
];

/** Быстрые действия, прокручивающие карточку к своему разделу. */
const SECTION_ACTIONS = [
  { icon: 'calendar', label: 'Встречи с клиентом', section: 'client-meetings' },
  { icon: 'diary',    label: 'Заметки',            section: 'client-notes' },
];

/** Контакты студента (ADR-032): запрос — только когда карточка загружена; данные привязаны к uuid. */
function StudentContacts({ studentUuid }) {
  const contacts = useUserContacts(studentUuid);
  return <UserContactsSection contacts={contacts} />;
}

export default function PsychologistStudentCardPage() {
  const { studentId } = useParams();
  const numericId = parseInt(studentId, 10);
  const isValidId = !isNaN(numericId) && numericId > 0;
  const { student, loading, error, refetch } = useStudentCard(isValidId ? numericId : null);
  const chatPath = getPsychologistStudentChatPath(student, isValidId ? numericId : null);
  // Переход «Встречи с клиентом» из списка клиентов (#client-meetings).
  useScrollToHash(Boolean(student) && !loading && !error);
  // «Заметка» к конкретной встрече: привязана к uuid клиента — у другого
  // клиента не применяется (ClientNotes сверяет clientUuid).
  const [noteMeeting, setNoteMeeting] = useState(null);
  // Выбранная встреча принадлежит клиенту, для которого её выбрали: при смене
  // клиента привязка сбрасывается (не переносится ни на B, ни обратно на A).
  const currentStudentUuid = student?.student_uuid;
  useEffect(() => { setNoteMeeting(null); }, [currentStudentUuid]);

  // Снимает привязку только того клиента, чья форма просит об этом: поздний
  // колбэк прежней карточки не должен снять встречу нового клиента.
  function clearNoteMeeting(clientUuid) {
    setNoteMeeting(cur => (cur && cur.clientUuid === clientUuid ? null : cur));
  }

  function addNoteForMeeting(meeting) {
    setNoteMeeting({ clientUuid: student?.student_uuid, meeting });
    scrollToSection('client-notes');
  }

  const is404 = Boolean(
    error && (
      error.includes('404') ||
      error.toLowerCase().includes('не найден') ||
      error.toLowerCase().includes('not found')
    )
  );

  return (
    <div className={styles.page}>
      <Link to="/psychologist/students" className={styles.backLink}>
        <Icon name="chevron-left" size={16} />
        Назад к студентам
      </Link>

      <div className={styles.header}>
        <h1 className={styles.pageTitle}>Карточка <em>студента</em></h1>
        <p className={styles.pageSub}>Базовая информация о студенте и сопровождении.</p>
      </div>

      {/* Invalid ID state */}
      {!isValidId && (
        <div className={styles.stateBox}>
          <div className={styles.stateIconWrap}>
            <Icon name="bell" size={28} />
          </div>
          <div className={styles.stateTitle}>Некорректный адрес карточки</div>
          <div className={styles.stateText}>
            Проверьте ссылку или вернитесь к списку студентов.
          </div>
        </div>
      )}

      {/* Loading skeleton */}
      {isValidId && loading && (
        <>
          <div className={styles.skeletonHero}>
            <div className={styles.skeletonAvatar} />
            <div className={styles.skeletonHeroInfo}>
              <div className={`${styles.skeletonLine} ${styles.wide}`} />
              <div className={`${styles.skeletonLine} ${styles.medium}`} />
              <div className={`${styles.skeletonLine} ${styles.short}`} />
            </div>
          </div>
          <div className={styles.skeletonInfoGrid}>
            {[1, 2, 3, 4].map(i => <div key={i} className={styles.skeletonInfoCard} />)}
          </div>
        </>
      )}

      {/* Error state */}
      {isValidId && !loading && error && (
        <div className={styles.stateBox}>
          <div className={styles.stateIconWrap}>
            <Icon name="bell" size={28} />
          </div>
          <div className={styles.stateTitle}>
            {is404 ? 'Карточка недоступна' : 'Не удалось загрузить данные'}
          </div>
          <div className={styles.stateText}>
            {is404
              ? 'Студент не найден или не назначен вам.'
              : error}
          </div>
          {!is404 && (
            <Button variant="secondary" onClick={refetch}>Повторить</Button>
          )}
        </div>
      )}

      {/* Content */}
      {isValidId && !loading && !error && student && (
        <>
          {/* Hero card */}
          <div className={styles.heroCard}>
            <div className={styles.heroAvatar}>
              {getInitials(student.full_name)}
            </div>
            <div className={styles.heroInfo}>
              <div className={styles.heroBadge}>Активное сопровождение</div>
              <h2 className={styles.heroName}>{student.full_name}</h2>
              <div className={styles.heroEmail}>
                <Icon name="mail" size={14} />
                <span>{student.email}</span>
              </div>
              <div className={styles.heroMeta}>
                <span>Назначен {formatDate(student.assigned_at)}</span>
                {getDuration(student.assigned_at) && (
                  <span className={styles.heroDuration}>
                    {getDuration(student.assigned_at)}
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Info cards */}
          <div className={styles.infoGrid}>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Статус</div>
              <div className={styles.infoValue}>
                <Badge tone="success">Активен</Badge>
              </div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Назначен</div>
              <div className={styles.infoValue}>{formatDate(student.assigned_at)}</div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Сопровождение</div>
              <div className={styles.infoValue}>{getDuration(student.assigned_at) ?? '—'}</div>
            </div>
            <div className={styles.infoCard}>
              <div className={styles.infoLabel}>Контакт</div>
              <div className={`${styles.infoValue} ${styles.emailVal}`}>{student.email}</div>
            </div>
          </div>

          {/* Quick actions */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Быстрые действия</h3>
            <div className={styles.actionsGrid}>
              {chatPath && (
                <Link
                  to={chatPath}
                  className={`${styles.actionCard} ${styles.actionLink}`}
                  title="Открыть чат со студентом"
                >
                  <div className={styles.actionIcon}>
                    <Icon name="chat" size={22} />
                  </div>
                  <div className={styles.actionLabel}>Чат со студентом</div>
                </Link>
              )}
              {SECTION_ACTIONS.map(({ icon, label, section }) => (
                <button
                  key={section}
                  type="button"
                  className={`${styles.actionCard} ${styles.actionLink}`}
                  onClick={() => scrollToSection(section)}
                >
                  <div className={styles.actionIcon}>
                    <Icon name={icon} size={22} />
                  </div>
                  <div className={styles.actionLabel}>{label}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Встречи с клиентом и итоги (ADR-035) */}
          <div className={styles.section} id="client-meetings">
            <h3 className={styles.sectionTitle} tabIndex={-1} data-section-heading>
              Встречи с клиентом
            </h3>
            <ClientMeetings
              key={student.student_uuid}
              studentUuid={student.student_uuid}
              onAddNote={addNoteForMeeting}
            />
          </div>

          {/* Заметки психолога о клиенте — существующие session_notes (ADR-035) */}
          <div className={styles.section} id="client-notes">
            <h3 className={styles.sectionTitle} tabIndex={-1} data-section-heading>
              Заметки
            </h3>
            <ClientNotes
              key={student.student_uuid}
              studentUuid={student.student_uuid}
              linkedMeeting={noteMeeting}
              onClearLinkedMeeting={() => clearNoteMeeting(student.student_uuid)}
            />
          </div>

          {/* Задания клиенту (ADR-033) */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Задания</h3>
            <ClientAssignments key={student.student_uuid} studentUuid={student.student_uuid} />
          </div>

          {/* Контакты студента (ADR-032) */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Контакты</h3>
            <StudentContacts key={student.student_uuid} studentUuid={student.student_uuid} />
          </div>

          {/* Результаты психодиагностики (Этап E) */}
          <div className={styles.section}>
            <h3 className={styles.sectionTitle}>Результаты психодиагностики</h3>
            <StudentTestResults
              key={student.student_uuid}
              studentUuid={student.student_uuid}
              activeRole="psychologist"
              canViewAnswers
            />
          </div>

          {/* Future block */}
          <div className={styles.futureBlock}>
            <div className={styles.futureTitle}>Что появится в карточке позже</div>
            <ul className={styles.futureList}>
              {FUTURE_ITEMS.map(text => (
                <li key={text} className={styles.futureItem}>
                  <span className={styles.futureDot} />
                  {text}
                </li>
              ))}
            </ul>
          </div>
        </>
      )}
    </div>
  );
}
