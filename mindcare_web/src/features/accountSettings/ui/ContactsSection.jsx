import { useState } from 'react';
import Button from '../../../components/UI/Button/Button';
import TextField from '../../../components/UI/TextField/TextField';
import { formatPhoneInput, PHONE_PLACEHOLDER } from '../../admin/users/phone';
import useMyContacts from '../../contacts/hooks/useMyContacts';
import ContactsEditor from '../../contacts/ui/ContactsEditor';
import styles from './AccountSettings.module.css';

// Подписи согласованы с реальной матрицей доступа (ADR-032):
// чистый студент — назначенный психолог и супервизор; сотрудник со staff-ролью
// (student у него неявный, ADR-024) — только назначенный психолог при действующем
// сопровождении.
export const AUDIENCE_NOTE_STUDENT =
  'Контакты доступны вашему назначенному психологу и супервизору. '
  + 'Каждый просмотр фиксируется в журнале.';
export const AUDIENCE_NOTE_STAFF =
  'Контакты доступны назначенному вам психологу при действующем сопровождении. '
  + 'Каждый просмотр фиксируется в журнале.';

/** Форма телефона монтируется после загрузки профиля: черновик стартует с сохранённого. */
function PhoneForm({ profile, state, onSave, onEdit }) {
  const [phone, setPhone] = useState(profile.phone);
  const dirty = phone !== profile.phone;

  return (
    <form
      className={styles.form}
      onSubmit={(e) => { e.preventDefault(); onSave(phone); }}
    >
      <TextField
        id="settings-phone"
        label="Номер телефона"
        type="tel"
        inputMode="tel"
        autoComplete="tel"
        value={phone}
        onChange={(e) => { setPhone(formatPhoneInput(e.target.value)); onEdit(); }}
        placeholder={PHONE_PLACEHOLDER}
        hint="Оставьте поле пустым, чтобы удалить номер"
        disabled={state.saving}
      />
      {state.error && <div className={styles.formError} role="alert">{state.error}</div>}
      {state.success && <div className={styles.formSuccess} role="status">Телефон сохранён.</div>}
      <div className={styles.actions}>
        <Button type="submit" variant="primary" loading={state.saving} disabled={!dirty}>
          Сохранить телефон
        </Button>
      </div>
    </form>
  );
}

/**
 * Раздел «Контакты»: основной телефон и дополнительные способы связи.
 * Монтируется всегда (черновики переживают смену раздела), но данные
 * дополнительных контактов запрашиваются только когда раздел открывали
 * (`requested`) и вне режима «под именем» — backend в нём отвечает 403.
 */
export default function ContactsSection({ account, requested, isStaff, isImpersonating }) {
  const contacts = useMyContacts({ enabled: requested && !isImpersonating });
  const { profile, loading, loadError, phoneState, savePhone, resetPhoneFeedback } = account;

  if (isImpersonating) {
    return (
      <div className={styles.stack}>
        <div className={styles.card}>
          <h2 className={styles.sectionTitle}>Контакты</h2>
          <p className={styles.dangerText}>Недоступно при входе под именем пользователя.</p>
        </div>
      </div>
    );
  }

  const audienceNote = isStaff ? AUDIENCE_NOTE_STAFF : AUDIENCE_NOTE_STUDENT;

  return (
    <div className={styles.stack}>
      <section className={styles.card} aria-labelledby="settings-phone-title">
        <h2 id="settings-phone-title" className={styles.sectionTitle}>Основной телефон</h2>
        {loading ? (
          <div className={styles.empty}>Загрузка профиля…</div>
        ) : loadError ? (
          <div className={styles.formError} role="alert">{loadError}</div>
        ) : (
          <PhoneForm
            profile={profile}
            state={phoneState}
            onSave={savePhone}
            onEdit={resetPhoneFeedback}
          />
        )}
      </section>

      <section className={styles.card} aria-labelledby="settings-contacts-title">
        <h2 id="settings-contacts-title" className={styles.sectionTitle}>Дополнительные контакты</h2>
        <ContactsEditor contacts={contacts} audienceNote={audienceNote} idPrefix="settings-contacts" />
      </section>
    </div>
  );
}
