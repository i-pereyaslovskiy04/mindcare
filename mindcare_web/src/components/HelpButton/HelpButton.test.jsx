import { render, screen } from '@testing-library/react';
import HelpButton, { helpHref } from './HelpButton';

test('ссылка на раздел руководства в новой вкладке', () => {
  render(<HelpButton guide="campaigns" section="results" />);
  const link = screen.getByRole('link', { name: /Справка/ });
  expect(link).toHaveAttribute('href', '/help/campaigns.html#results');
  expect(link).toHaveAttribute('target', '_blank');
  expect(link).toHaveAttribute('rel', 'noopener noreferrer');
  expect(helpHref('methodologies')).toBe('/help/methodologies.html');
});
