import { useState } from 'react';
import Badge from '../../../components/UI/Badge/Badge';
import Button from '../../../components/UI/Button/Button';
import TextField from '../../../components/UI/TextField/TextField';
import { roleLabel } from '../../../shared/lib/roles';
import StudentVerificationSection from '../../studentVerification/ui/StudentVerificationSection';
import { VERIFIED_BADGE_LABEL } from '../../studentVerification/lib/status';
import styles from './AccountSettings.module.css';

function avatarLetter(name) {
  const t = (name || '').trim();
  return t ? t[0].toUpperCase() : '?';
}

/** Форма ФИО монтируется после загрузки профиля: черновик стартует с сохранённого значения. */
function FullNameForm({ profile, isVerifiedStudent, state, onSave, onEdit }) {
  const [fullName, setFullName] = useState(profile.full_name);
  const dirty = fullName !== profile.full_name;

  return (
    <form
      className={styles.form}
      onSubmit={(e) => { e.preventDefault(); onSave(fullName); }}
    >
      <div className={styles.profileHead}>
        <div className={styles.avatar} aria-hidden="true">{avatarLetter(profile.full_name)}</div>
        <div>
          <div className={styles.profileName}>{profile.full_name || 'Без имени'}</div>
          <div className={styles.profileRole}>{roleLabel(profile.role)}</div>
          {isVerifiedStudent && (
            <Badge tone="success" className={styles.verifiedBadge}>{VERIFIED_BADGE_LABEL}</Badge>
          )}
        </div>
      </div>

      <TextField
        id="settings-full-name"
        label="ФИО"
        value={fullName}
        onChange={(e) => { setFullName(e.target.value); onEdit(); }}
        placeholder="Иванов Иван Иванович"
        maxLength={255}
        autoComplete="name"
        disabled={state.saving}
      />
      <TextField
        id="settings-email"
        label="Email"
        type="email"
        value={profile.email}
        readOnly
        hint="Используется для входа, изменить нельзя"
      />

      {state.error && <div className={styles.formError} role="alert">{state.error}</div>}
      {state.success && <div className={styles.formSuccess} role="status">ФИО сохранено.</div>}

      <div className={styles.actions}>
        <Button type="submit" variant="primary" loading={state.saving} disabled={!dirty}>
          Сохранить
        </Button>
      </div>
    </form>
  );
}

/**
 * Раздел «Личные данные»: профиль (ФИО, email), подтверждение студента ДонГУ.
 * Телефон и способы связи — в разделе «Контакты».
 */
export default function PersonalSection({
  account,
  isVerifiedStudent,
  verificationEnabled,
  verification,
  showVerificationImpersonationNote,
}) {
  const { profile, loading, loadError, nameState, saveFullName, resetNameFeedback } = account;

  return (
    <div className={styles.stack}>
      <section className={styles.card} aria-labelledby="settings-profile-title">
        <h2 id="settings-profile-title" className={styles.sectionTitle}>Профиль</h2>
        {loading ? (
          <div className={styles.empty}>Загрузка профиля…</div>
        ) : loadError ? (
          <div className={styles.formError} role="alert">{loadError}</div>
        ) : (
          <FullNameForm
            profile={profile}
            isVerifiedStudent={isVerifiedStudent}
            state={nameState}
            onSave={saveFullName}
            onEdit={resetNameFeedback}
          />
        )}
      </section>

      {verificationEnabled && (
        <StudentVerificationSection
          className={styles.card}
          verification={verification.data}
          loading={verification.loading}
          error={verification.error}
          onSubmitted={verification.setData}
        />
      )}
      {showVerificationImpersonationNote && (
        <div className={styles.card}>
          <h2 className={styles.sectionTitle}>Подтверждение студента ДонГУ</h2>
          <p className={styles.dangerText}>Недоступно при входе под именем пользователя.</p>
        </div>
      )}
    </div>
  );
}
