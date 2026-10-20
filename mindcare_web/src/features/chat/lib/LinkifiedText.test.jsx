import { render, screen } from '@testing-library/react';
import LinkifiedText from './LinkifiedText';
import MessageBubble from '../components/MessageBubble';

// react-router-dom (v7) не резолвится jest-резолвером проекта — virtual mock:
// router <Link> рендерится как <a data-router-link> (переход внутри SPA).
jest.mock('react-router-dom', () => ({
  Link: ({ to, children, ...rest }) => require('react').createElement(
    'a', { href: to, 'data-router-link': 'true', ...rest }, children,
  ),
}), { virtual: true });

const SETTINGS_PATH = '/student/settings#student-verification';
const INVITE = 'Укажите номер студенческого билета в настройках аккаунта.\n\n'
  + `Открыть раздел: ${SETTINGS_PATH}`;

// eslint-disable-next-line no-script-url -- намеренно опасная схема для security-теста
const JS_URL = 'javascript:alert(1)';

describe('LinkifiedText — security & linkify', () => {
  test('http URL becomes a link', () => {
    render(<LinkifiedText text="see http://example.com now" />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', 'http://example.com');
    expect(link).toHaveTextContent('http://example.com');
  });

  test('https URL becomes a link', () => {
    render(<LinkifiedText text="https://example.com/path" />);
    expect(screen.getByRole('link')).toHaveAttribute(
      'href',
      'https://example.com/path',
    );
  });

  test('link opens in new tab with noopener+noreferrer', () => {
    render(<LinkifiedText text="https://example.com" />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('target', '_blank');
    const rel = link.getAttribute('rel') || '';
    expect(rel).toContain('noopener');
    expect(rel).toContain('noreferrer');
  });

  test('javascript-scheme URL does NOT become a link', () => {
    render(<LinkifiedText text={JS_URL} />);
    expect(screen.queryByRole('link')).toBeNull();
    expect(screen.getByText(JS_URL)).toBeInTheDocument();
  });

  test('data-scheme URL does NOT become a link', () => {
    render(<LinkifiedText text="data:text/html,xxx" />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  test('<script> content is rendered as text, not parsed as HTML', () => {
    const payload = '<script>alert(1)</script>';
    const { container } = render(<LinkifiedText text={payload} />);
    // никакой реальный <script> элемент не создаётся (нет HTML-инъекции)
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText(payload)).toBeInTheDocument();
  });

  test('HTML tags are shown as text (no dangerouslySetInnerHTML)', () => {
    const { container } = render(<LinkifiedText text="<b>bold</b>" />);
    // тег не превращается в реальный <b> элемент
    // eslint-disable-next-line testing-library/no-container, testing-library/no-node-access
    expect(container.querySelector('b')).toBeNull();
    expect(screen.getByText('<b>bold</b>')).toBeInTheDocument();
  });

  test('empty text renders no link', () => {
    render(<LinkifiedText text="" />);
    expect(screen.queryByRole('link')).toBeNull();
  });
});

describe('LinkifiedText — внутренние ссылки system-сообщений (ADR-029)', () => {
  test('allowlisted path becomes a router link with a readable label', () => {
    render(<LinkifiedText text={INVITE} allowInternalLinks />);
    const link = screen.getByRole('link', { name: 'Подтверждение студента ДонГУ' });
    expect(link).toHaveAttribute('href', SETTINGS_PATH);
    expect(link).toHaveAttribute('data-router-link', 'true');
    expect(link).not.toHaveAttribute('target');
    expect(screen.queryByText(SETTINGS_PATH)).toBeNull();
  });

  test('without the flag the path stays plain text', () => {
    render(<LinkifiedText text={INVITE} />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  test.each([
    `${SETTINGS_PATH}-evil`,
    `x${SETTINGS_PATH}`,
    `//evil.example${SETTINGS_PATH}`,
    '/student/settings',
    '/admin/users',
    '/student/settings#other',
  ])('non-allowlisted or glued path %s is not linked', (value) => {
    render(<LinkifiedText text={`Перейти: ${value}`} allowInternalLinks />);
    expect(screen.queryByRole('link')).toBeNull();
  });

  test('trailing punctuation and brackets are kept outside the link', () => {
    render(<LinkifiedText text={`(см. ${SETTINGS_PATH}).`} allowInternalLinks />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('href', SETTINGS_PATH);
  });

  test('external URL that embeds the path stays an external link', () => {
    render(<LinkifiedText text={`https://evil.example${SETTINGS_PATH}`} allowInternalLinks />);
    const link = screen.getByRole('link');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link).not.toHaveAttribute('data-router-link');
  });

  test('MessageBubble links the path only for system messages', () => {
    const { unmount } = render(<MessageBubble variant="system" text={INVITE} time="10:00" />);
    expect(screen.getByRole('link', { name: 'Подтверждение студента ДонГУ' }))
      .toHaveAttribute('href', SETTINGS_PATH);
    unmount();
    render(<MessageBubble variant="incoming" text={INVITE} time="10:00" />);
    expect(screen.queryByRole('link')).toBeNull();
  });
});
