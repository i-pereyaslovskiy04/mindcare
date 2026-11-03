import { useNavigate } from 'react-router-dom';
import Tabs, { tabButtonId, tabPanelId } from '../../../components/UI/Tabs/Tabs';
import { useAuth } from '../../../features/auth/AuthContext';
import useMyStudentVerification from '../../../features/studentVerification/hooks/useMyStudentVerification';
import { canUseVerificationSelfService } from '../../../features/studentVerification/lib/status';
import useAccountProfile from '../../../features/accountSettings/hooks/useAccountProfile';
import useSettingsSection from '../../../features/accountSettings/hooks/useSettingsSection';
import {
  SECTION_CONTACTS, SECTION_PERSONAL, SECTION_SECURITY, SETTINGS_SECTIONS,
} from '../../../features/accountSettings/lib/sections';
import PersonalSection from '../../../features/accountSettings/ui/PersonalSection';
import ContactsSection from '../../../features/accountSettings/ui/ContactsSection';
import SecuritySection from '../../../features/accountSettings/ui/SecuritySection';
import HelpBlock from '../../../features/accountSettings/ui/HelpBlock';
import styles from './SettingsPage.module.css';

const TABS_PREFIX = 'settings';

function Panel({ id, active, children }) {
  return (
    <div
      role="tabpanel"
      id={tabPanelId(TABS_PREFIX, id)}
      aria-labelledby={tabButtonId(TABS_PREFIX, id)}
      hidden={active !== id}
      className={styles.panel}
    >
      {children}
    </div>
  );
}

/**
 * Настройки аккаунта: три раздела — «Личные данные», «Контакты», «Безопасность».
 * Страница только компонует: данные и действия — в features/accountSettings,
 * features/contacts, features/studentVerification. Панели смонтированы всегда
 * (неактивные скрыты атрибутом hidden), поэтому черновики форм переживают смену
 * раздела; запрос дополнительных контактов выполняется при первом открытии.
 */
export default function SettingsPage() {
  const {
    user, refreshUser, isImpersonating, deactivateOwnAccount, clearSession,
  } = useAuth();
  const navigate = useNavigate();
  const account = useAccountProfile({ refreshUser });
  const { active, select, visited } = useSettingsSection();

  const roles = user?.roles || [];
  const isPureStudent = roles.length === 1 && roles[0] === 'student';
  // Самоотключение — только чистому студенту вне «под именем» (ADR-028, ADR-024).
  const canSelfDeactivate = isPureStudent && !isImpersonating;

  // Подтверждение студента ДонГУ (ADR-029): статус, не роль; self-service — чистый student.
  const verificationEnabled = canUseVerificationSelfService(roles, isImpersonating);
  const verification = useMyStudentVerification(verificationEnabled);
  const isVerifiedStudent = verification.data?.status === 'approved';
  const showVerificationImpersonationNote = isImpersonating && isPureStudent;

  const hasPassword = (account.profile.has_password ?? user?.has_password) !== false;

  // Сессии на сервере уже отозваны: сначала публичная страница, затем очистка
  // клиентской авторизации (порядок как в useLogout; logout дал бы 401).
  const endSession = (message) => {
    navigate('/', { replace: true, state: { openAuth: 'login', message } });
    clearSession();
  };

  return (
    <div className={styles.page}>
      <h1 className={styles.pageTitle}>
        Настройки <em>аккаунта</em>
      </h1>
      <p className={styles.pageSub}>
        Личные данные, способы связи и безопасность аккаунта.
      </p>

      <Tabs
        tabs={SETTINGS_SECTIONS}
        active={active}
        onChange={select}
        label="Разделы настроек"
        idPrefix={TABS_PREFIX}
        fill
      />

      <Panel id={SECTION_PERSONAL} active={active}>
        <PersonalSection
          account={account}
          isVerifiedStudent={isVerifiedStudent}
          verificationEnabled={verificationEnabled}
          verification={verification}
          showVerificationImpersonationNote={showVerificationImpersonationNote}
        />
      </Panel>

      <Panel id={SECTION_CONTACTS} active={active}>
        <ContactsSection
          account={account}
          requested={visited.has(SECTION_CONTACTS)}
          isStaff={!isPureStudent}
          isImpersonating={Boolean(isImpersonating)}
        />
      </Panel>

      <Panel id={SECTION_SECURITY} active={active}>
        <SecuritySection
          hasPassword={hasPassword}
          email={account.profile.email}
          canSelfDeactivate={canSelfDeactivate}
          deactivateOwnAccount={deactivateOwnAccount}
          endSession={endSession}
        />
      </Panel>

      <HelpBlock />
    </div>
  );
}
