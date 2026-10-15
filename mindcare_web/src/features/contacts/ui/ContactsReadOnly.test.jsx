/* eslint-disable no-script-url */
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import UserContactsSection, { ContactsReadOnly } from './ContactsReadOnly';
import { formatPhoneInput } from '../../admin/users/phone';

const CATALOG = {
  types: [
    { code: 'phone', label: 'Телефон', service_kind: null },
    { code: 'messenger', label: 'Мессенджер', service_kind: 'messenger' },
    { code: 'website', label: 'Сайт', service_kind: null },
    { code: 'other', label: 'Другое', service_kind: null },
  ],
  services: { messenger: [{ code: 'telegram', label: 'Telegram' }] },
};

describe('ContactsReadOnly', () => {
  it('пусто, когда нечего показывать', () => {
    render(<ContactsReadOnly data={{ primary_phone: null, items: [], catalog: CATALOG }} />);
    expect(screen.getByText('Контакты не указаны.')).toBeInTheDocument();
  });

  it('показывает основной телефон, подписи и заметку об аудите', () => {
    render(
      <ContactsReadOnly
        data={{
          primary_phone: '+79001234567',
          catalog: CATALOG,
          items: [
            { id: '1', type: 'messenger', service: 'telegram', value: '@name', label: 'рабочий' },
          ],
        }}
      />,
    );
    expect(screen.getByText('Основной телефон')).toBeInTheDocument();
    expect(screen.getByRole('link', { name: '+79001234567' })).toHaveAttribute('href', 'tel:+79001234567');
    expect(screen.getByText('Мессенджер · Telegram')).toBeInTheDocument();
    expect(screen.getByText('@name')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: '@name' })).toBeNull();
    expect(screen.getByText('рабочий')).toBeInTheDocument();
    expect(screen.getByText(/фиксируется в журнале/)).toBeInTheDocument();
  });

  it('внешние ссылки безопасны; небезопасное значение остаётся текстом', () => {
    render(
      <ContactsReadOnly
        data={{
          primary_phone: null,
          catalog: CATALOG,
          items: [
            { id: '1', type: 'website', service: null, value: 'https://example.org', label: null },
            { id: '2', type: 'website', service: null, value: 'javascript:alert(1)', label: null },
            { id: '3', type: 'other', service: null, value: 'https://x.example', label: 'Прочее' },
          ],
        }}
      />,
    );
    const link = screen.getByRole('link', { name: 'https://example.org' });
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noopener');
    expect(link.getAttribute('rel')).toContain('noreferrer');
    expect(link.getAttribute('rel')).toContain('nofollow');
    expect(screen.getByText('javascript:alert(1)')).toBeInTheDocument();
    expect(screen.queryByRole('link', { name: 'javascript:alert(1)' })).toBeNull();
    expect(screen.queryByRole('link', { name: 'https://x.example' })).toBeNull();
  });
});

describe('основной телефон сотрудника', () => {
  it('formatPhoneInput → отображение → корректный tel:, текст остаётся форматированным', () => {
    const stored = formatPhoneInput('9491234567');
    render(<ContactsReadOnly data={{ primary_phone: stored, items: [], catalog: CATALOG }} />);
    const link = screen.getByRole('link', { name: '+7 (949) 123-45-67' });
    expect(link).toHaveAttribute('href', 'tel:+79491234567');
    expect(link).not.toHaveAttribute('target');
  });

  it('нетелефонная строка в primary_phone показывается текстом без ссылки', () => {
    render(<ContactsReadOnly data={{ primary_phone: 'звонить после 18', items: [], catalog: CATALOG }} />);
    expect(screen.getByText('звонить после 18')).toBeInTheDocument();
    expect(screen.queryByRole('link')).toBeNull();
  });

  it('форматированный дополнительный телефон тоже получает tel:', () => {
    render(
      <ContactsReadOnly
        data={{
          primary_phone: null,
          catalog: CATALOG,
          items: [{ id: '1', type: 'phone', service: null, value: '+7 (949) 000-11-22', label: null }],
        }}
      />,
    );
    expect(screen.getByRole('link', { name: '+7 (949) 000-11-22' })).toHaveAttribute('href', 'tel:+79490001122');
  });
});

describe('UserContactsSection', () => {
  it('загрузка', () => {
    render(<UserContactsSection contacts={{ status: 'loading', data: null, refetch: jest.fn() }} />);
    expect(screen.getByRole('status')).toHaveTextContent('Загрузка');
  });

  it.each(['unavailable', 'forbidden'])('%s → единый нейтральный текст', (status) => {
    render(<UserContactsSection contacts={{ status, data: null, refetch: jest.fn() }} />);
    expect(screen.getByText('Контакты недоступны.')).toBeInTheDocument();
  });

  it('сбой журнала (503) объясняется и позволяет повторить', async () => {
    const refetch = jest.fn();
    render(<UserContactsSection contacts={{ status: 'auditUnavailable', data: null, refetch }} />);
    expect(screen.getByRole('alert')).toHaveTextContent('зафиксировать в журнале');
    await userEvent.click(screen.getByRole('button', { name: 'Повторить' }));
    expect(refetch).toHaveBeenCalled();
  });

  it('готово → список', () => {
    render(
      <UserContactsSection
        contacts={{
          status: 'ready',
          refetch: jest.fn(),
          data: { primary_phone: '+79001234567', items: [], catalog: CATALOG },
        }}
      />,
    );
    expect(screen.getByText('Основной телефон')).toBeInTheDocument();
  });
});
