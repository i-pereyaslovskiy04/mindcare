import { render, screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import CampaignsPage from './CampaignsPage';
import SupervisorCampaignPage from './SupervisorCampaignPage';
import { deleteCampaign, getCampaign, getCampaigns, getCampaignTests } from '../../api/campaigns.api';

jest.mock('../../api/campaigns.api');

const C = {
  uuid: 'c-1', title: 'Весна, 1 курс', status: 'open', link_state: 'open', test_title: 'ИТО',
  test_uuid: 't-1', responses_count: 12, created_at: '2026-11-04T10:00:00Z', closed_at: null,
  closes_at: '2026-11-30T18:00:00Z', access_code_set: true,
  link_token: 'tok', link_path: '/test/vesna-abc', link_url: 'https://x/test/vesna-abc',
};

function renderAt(path) {
  return render(
    <MemoryRouter initialEntries={[path]}>
      <Routes>
        <Route path="/supervisor/campaigns" element={<CampaignsPage />} />
        <Route path="/supervisor/campaigns/:uuid" element={<SupervisorCampaignPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  jest.resetAllMocks();
  getCampaigns.mockResolvedValue({ items: [C], has_more: false });
  getCampaignTests.mockResolvedValue([]);
  getCampaign.mockResolvedValue(C);
});

test('список — компактная строка, кампания открывается на своей странице', async () => {
  renderAt('/supervisor/campaigns');
  const link = (await screen.findAllByRole('link', { name: 'Весна, 1 курс' }))[0];
  expect(link).toHaveAttribute('href', '/supervisor/campaigns/c-1');
  expect(screen.queryByRole('button', { name: 'Скачать xlsx' })).not.toBeInTheDocument();
  expect(screen.getAllByText('Кодовое слово').length).toBeGreaterThan(0);
  userEvent.click(link);
  expect(await screen.findByRole('heading', { level: 1, name: 'Весна, 1 курс' })).toBeInTheDocument();
  expect(getCampaign).toHaveBeenCalledWith('c-1');
  expect(screen.getByRole('button', { name: 'Скачать xlsx' })).toBeInTheDocument();
  expect(screen.getByRole('link', { name: /К списку кампаний/ })).toHaveAttribute('href', '/supervisor/campaigns');
});

test('нет кампании — понятное сообщение', async () => {
  const err = new Error('nf');
  err.status = 404;
  getCampaign.mockRejectedValue(err);
  renderAt('/supervisor/campaigns/zzz');
  expect(await screen.findByRole('alert')).toHaveTextContent('Кампания не найдена');
});

test('после удаления — возврат к списку', async () => {
  deleteCampaign.mockResolvedValue(null);
  renderAt('/supervisor/campaigns/c-1');
  userEvent.click(await screen.findByRole('button', { name: 'Удалить' }));
  const dialog = await screen.findByRole('dialog');
  userEvent.click(within(dialog).getByRole('button', { name: 'Удалить' }));
  expect(await screen.findByRole('heading', { level: 1, name: 'Тестирование по ссылке' })).toBeInTheDocument();
});
