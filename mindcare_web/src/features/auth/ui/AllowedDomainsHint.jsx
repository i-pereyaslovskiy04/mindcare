import { useEffect, useRef, useState } from 'react';
import Icon from '../../../components/Icon/Icon';
import styles from './AuthModal.module.css';

export const DOMAINS_HINT_ID = 'r-email-domains';
export const DOMAIN_ERROR_ID = 'r-email-domain-error';
const PANEL_ID = 'r-email-domains-list';
const TITLE_ID = 'r-email-domains-title';

/** Домен адреса так же, как его берёт backend: strip + lower, часть после последнего «@». */
export function emailDomainOf(email) {
  const normalized = (email || '').trim().toLowerCase();
  const at = normalized.lastIndexOf('@');
  return at < 0 ? '' : normalized.slice(at + 1);
}

/** Домена нет в загруженном списке. Только для подсказки: допуск решает backend. */
export function isDomainUnsupported(email, domains) {
  const domain = emailDomainOf(email);
  return Boolean(domain) && !domains.some((d) => d.toLowerCase() === domain);
}

/**
 * Разрешённые домены под полем Email — progressive disclosure: короткая
 * подсказка и info-кнопка, список раскрывается по клику (мышь, клавиатура,
 * touch; не hover) в компактной панели прямо под подсказкой — в потоке формы,
 * без перекрытия полей и обрезки скроллом модалки. Закрывают повторный клик,
 * Escape и клик снаружи. При неподдерживаемом домене — ошибка и действие,
 * открывающее ту же панель.
 *
 * domains — список из useAllowedEmailDomains (ответ backend); пустой — блока
 * нет. children — ошибка формата email: рисуется ПОСЛЕ строки подсказки, чтобы
 * её появление на blur не сдвигало info-кнопку между mousedown и click.
 */
export default function AllowedDomainsHint({ domains, unsupported, children }) {
  const [open, setOpen] = useState(false);
  const wrapRef = useRef(null);
  const infoRef = useRef(null);
  const openerRef = useRef(null);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (e) => {
      if (e.key !== 'Escape') return;
      // Capture-фаза на document: первый Escape закрывает список, а не
      // AuthModal (её обработчик — на document в фазе всплытия).
      e.stopPropagation();
      setOpen(false);
      if (wrapRef.current?.contains(document.activeElement)) {
        const opener = openerRef.current?.isConnected ? openerRef.current : infoRef.current;
        opener?.focus();
      }
    };
    const onMouseDown = (e) => {
      if (!wrapRef.current?.contains(e.target)) setOpen(false);
    };
    document.addEventListener('keydown', onKeyDown, true);
    document.addEventListener('mousedown', onMouseDown, true);
    return () => {
      document.removeEventListener('keydown', onKeyDown, true);
      document.removeEventListener('mousedown', onMouseDown, true);
    };
  }, [open]);

  if (!domains.length) return children ?? null;

  const toggle = (e) => {
    openerRef.current = e.currentTarget;
    setOpen((value) => !value);
  };
  const triggerProps = { 'aria-expanded': open, 'aria-controls': PANEL_ID, onClick: toggle };

  return (
    <div ref={wrapRef} className={styles.domains}>
      <div className={`${styles.authNote} ${styles.domainsHint}`}>
        <span id={DOMAINS_HINT_ID}>Используйте почту разрешённого домена</span>
        <button
          ref={infoRef}
          type="button"
          className={styles.domainsInfo}
          aria-label="Показать разрешённые домены"
          {...triggerProps}
        >
          <Icon name="info" size={15} />
        </button>
      </div>
      {children}
      {unsupported && (
        <div className={styles.domainError}>
          <span id={DOMAIN_ERROR_ID} role="alert">Этот домен не поддерживается.</span>
          <button type="button" className={styles.domainsLink} {...triggerProps}>
            Посмотреть разрешённые домены
          </button>
        </div>
      )}
      <div
        id={PANEL_ID}
        className={styles.domainsPanel}
        role="group"
        aria-labelledby={TITLE_ID}
        hidden={!open}
      >
        <p id={TITLE_ID} className={styles.domainsTitle}>Разрешённые домены</p>
        <ul className={styles.domainsList}>
          {domains.map((domain) => <li key={domain}>@{domain}</li>)}
        </ul>
      </div>
    </div>
  );
}
