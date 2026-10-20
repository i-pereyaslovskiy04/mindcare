import Button from '../../../components/UI/Button/Button';
import { serviceKindOf } from '../lib/draft';
import { contactHref } from '../lib/href';
import styles from './ContactsReadOnly.module.css';

const AUDIT_NOTE = 'Просмотр контактов фиксируется в журнале.';

function typeLabel(catalog, type) {
  return catalog?.types?.find((t) => t.code === type)?.label ?? type;
}

function serviceLabel(catalog, item) {
  const kind = serviceKindOf(catalog, item.type);
  if (!kind || !item.service) return null;
  return catalog?.services?.[kind]?.find((s) => s.code === item.service)?.label ?? item.service;
}

function ContactValue({ item }) {
  const href = contactHref(item);
  if (!href) return <span className={styles.value}>{item.value}</span>;
  const external = href.startsWith('http');
  return (
    <a
      className={styles.link}
      href={href}
      {...(external ? { target: '_blank', rel: 'noopener noreferrer nofollow' } : {})}
    >
      {item.value}
    </a>
  );
}

/**
 * Контакты пользователя только для чтения (для сотрудника, ADR-032).
 * data = { primary_phone, items, catalog }. Значения подставляются как текст;
 * ссылкой становятся только проверенные значения (см. contactHref).
 */
export function ContactsReadOnly({ data }) {
  const items = data?.items ?? [];
  const phone = data?.primary_phone;
  const catalog = data?.catalog ?? null;

  if (!phone && items.length === 0) {
    return (
      <div>
        <p className={styles.empty}>Контакты не указаны.</p>
      </div>
    );
  }

  return (
    <div className={styles.wrap}>
      <ul className={styles.list}>
        {phone && (
          <li className={styles.item}>
            <span className={styles.kind}>Основной телефон</span>
            <ContactValue item={{ type: 'phone', value: phone }} />
          </li>
        )}
        {items.map((item) => {
          const service = serviceLabel(catalog, item);
          return (
            <li key={item.id} className={styles.item}>
              <span className={styles.kind}>
                {[typeLabel(catalog, item.type), service].filter(Boolean).join(' · ')}
              </span>
              <ContactValue item={item} />
              {item.label && <span className={styles.label}>{item.label}</span>}
            </li>
          );
        })}
      </ul>
      <p className={styles.note}>{AUDIT_NOTE}</p>
    </div>
  );
}

/**
 * Контейнер для сотрудника: состояние хука useUserContacts → разметка.
 * Тексты отказов единые для 404/403 — существование пользователя не раскрывается.
 */
export default function UserContactsSection({ contacts }) {
  const { status, data, refetch } = contacts;

  if (status === 'idle' || status === 'loading') {
    return <p className={styles.state} role="status">Загрузка контактов…</p>;
  }
  if (status === 'unavailable' || status === 'forbidden') {
    return <p className={styles.state}>Контакты недоступны.</p>;
  }
  if (status === 'auditUnavailable' || status === 'error') {
    return (
      <div className={styles.errorBox}>
        <p role="alert" className={styles.alert}>
          {status === 'auditUnavailable'
            ? 'Контакты временно недоступны: просмотр не удалось зафиксировать в журнале.'
            : 'Не удалось загрузить контакты.'}
        </p>
        <Button type="button" variant="secondary" onClick={refetch}>Повторить</Button>
      </div>
    );
  }
  return <ContactsReadOnly data={data} />;
}
