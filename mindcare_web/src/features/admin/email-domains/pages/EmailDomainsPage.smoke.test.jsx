import { render, screen } from '@testing-library/react';
import EmailDomainsPage from './EmailDomainsPage';
import * as api from '../../../../api/domains.api';

jest.mock('../../../../api/domains.api');

test('renders the email domains page with its title and section', async () => {
  api.getEmailDomains.mockResolvedValue([]);
  render(<EmailDomainsPage />);
  expect(screen.getByRole('heading', { name: 'Домены регистрации' })).toBeInTheDocument();
  expect(await screen.findByText('Разрешённые почтовые домены')).toBeInTheDocument();
});
