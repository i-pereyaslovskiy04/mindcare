import { render, screen } from '@testing-library/react';
import LinkifiedText from './LinkifiedText';

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
