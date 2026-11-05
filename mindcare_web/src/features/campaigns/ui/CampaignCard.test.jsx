import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import CampaignCard, { campaignLink, exportFilename } from './CampaignCard';
import {
  deleteCampaign, rotateCampaignLink, setCampaignStatus,
} from '../../../api/campaigns.api';

jest.mock('../../../api/campaigns.api');

const CAMPAIGN = {
  uuid: 'c-1',
  title: '1 курс',
  status: 'open',
  test_title: 'ИТО',
  responses_count: 0,
  created_at: '2026-11-04T10:00:00Z',
  closed_at: null,
  link_token: 'tok',
  link_path: '/test/ito-2026-k7m2xq',
  link_url: 'https://mindcare.example/test/ito-2026-k7m2xq',
};

function setup(overrides = {}) {
  const onChange = jest.fn();
  const onDeleted = jest.fn();
  render(<CampaignCard campaign={{ ...CAMPAIGN, ...overrides }}
    onChange={onChange} onDeleted={onDeleted} />);
  return { onChange, onDeleted };
}

beforeEach(() => jest.resetAllMocks());

test('ссылка — из link_url, иначе origin + link_path', () => {
  expect(campaignLink(CAMPAIGN)).toBe('https://mindcare.example/test/ito-2026-k7m2xq');
  expect(campaignLink({ ...CAMPAIGN, link_url: null }))
    .toBe(`${window.location.origin}/test/ito-2026-k7m2xq`);
});

test('имя файла выгрузки без запрещённых символов', () => {
  expect(exportFilename('1 курс / УФФ')).toBe('Результаты_1_курс_УФФ.xlsx');
});

test('без ответов скачать нельзя; ссылка показана', () => {
  setup();
  expect(screen.getByRole('button', { name: 'Скачать xlsx' })).toBeDisabled();
  expect(screen.getByLabelText('Ссылка для участников'))
    .toHaveValue('https://mindcare.example/test/ito-2026-k7m2xq');
});

test('закрыть — ответ backend уходит в onChange', async () => {
  setCampaignStatus.mockResolvedValue({ ...CAMPAIGN, status: 'closed' });
  const { onChange } = setup();
  await userEvent.click(screen.getByRole('button', { name: 'Закрыть' }));
  expect(setCampaignStatus).toHaveBeenCalledWith('c-1', 'closed');
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ status: 'closed' })));
});

test('новая ссылка — только после подтверждения', async () => {
  rotateCampaignLink.mockResolvedValue({ ...CAMPAIGN, link_token: 'new' });
  const { onChange } = setup();
  await userEvent.click(screen.getByRole('button', { name: 'Новая ссылка' }));
  expect(rotateCampaignLink).not.toHaveBeenCalled();
  await userEvent.click(screen.getByRole('button', { name: 'Выпустить' }));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ link_token: 'new' })));
});

test('удаление — подтверждение, затем onDeleted; ошибка остаётся в диалоге', async () => {
  deleteCampaign.mockRejectedValueOnce(new Error('Сбой')).mockResolvedValueOnce(null);
  const { onDeleted } = setup();
  await userEvent.click(screen.getByRole('button', { name: 'Удалить' }));
  const confirm = screen.getAllByRole('button', { name: 'Удалить' }).at(-1);
  await userEvent.click(confirm);
  expect(await screen.findByText('Сбой')).toBeInTheDocument();
  expect(onDeleted).not.toHaveBeenCalled();
  await userEvent.click(screen.getAllByRole('button', { name: 'Удалить' }).at(-1));
  await waitFor(() => expect(onDeleted).toHaveBeenCalledWith('c-1'));
});
