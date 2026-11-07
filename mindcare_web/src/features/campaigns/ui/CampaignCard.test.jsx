import { render, screen, waitFor } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import userEvent from '@testing-library/user-event';
import CampaignCard, { campaignLink, exportFilename } from './CampaignCard';
import {
  clearCampaignAccessCode, deleteCampaign, renameCampaign, rotateCampaignLink,
  setCampaignAccessCode, setCampaignSchedule, setCampaignStatus,
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
  render(
    <MemoryRouter>
      <CampaignCard campaign={{ ...CAMPAIGN, ...overrides }}
        onChange={onChange} onDeleted={onDeleted} />
    </MemoryRouter>,
  );
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

test('переименование — новое название, ссылка прежняя', async () => {
  renameCampaign.mockResolvedValue({ ...CAMPAIGN, title: '2 курс' });
  const { onChange } = setup();
  await userEvent.click(screen.getByRole('button', { name: 'Переименовать' }));
  const field = screen.getByLabelText('Название');
  expect(field).toHaveValue('1 курс');
  expect(screen.getByText('Адрес ссылки не изменится')).toBeInTheDocument();
  await userEvent.clear(field);
  await userEvent.type(field, '  2   курс ');
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  expect(renameCampaign).toHaveBeenCalledWith('c-1', '2 курс');
  await waitFor(() => expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({ title: '2 курс', link_token: 'tok' })));
  expect(await screen.findByText('Название изменено, ссылка прежняя')).toBeInTheDocument();
  expect(screen.queryByLabelText('Название')).not.toBeInTheDocument();
});

test('переименование: короткое название не отправляется, то же — без запроса', async () => {
  setup();
  await userEvent.click(screen.getByRole('button', { name: 'Переименовать' }));
  const field = screen.getByLabelText('Название');
  await userEvent.clear(field);
  await userEvent.type(field, 'x');
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  expect(screen.getByRole('alert')).toHaveTextContent('Минимум 2 символа');
  await userEvent.clear(field);
  await userEvent.type(field, '1 курс');
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  expect(renameCampaign).not.toHaveBeenCalled();
  expect(screen.queryByLabelText('Название')).not.toBeInTheDocument();
});

test('переименование: ошибка backend показывается у поля', async () => {
  renameCampaign.mockRejectedValue(new Error('Кампания не найдена'));
  const { onChange } = setup();
  await userEvent.click(screen.getByRole('button', { name: 'Переименовать' }));
  await userEvent.type(screen.getByLabelText('Название'), ' 2026');
  await userEvent.click(screen.getByRole('button', { name: 'Сохранить' }));
  expect(await screen.findByRole('alert')).toHaveTextContent('Кампания не найдена');
  expect(onChange).not.toHaveBeenCalled();
});

test('состояние ссылки: ещё не началась, сроки и код в описании', () => {
  setup({ link_state: 'scheduled', opens_at: '2026-12-01T07:00:00Z', access_code_set: true });
  expect(screen.getByText('Ещё не началась')).toBeInTheDocument();
  expect(screen.getByText(/с 1 дек.*10:00.*по кодовому слову/)).toBeInTheDocument();
});

test('сроки и кодовое слово: сохранение и снятие', async () => {
  setCampaignAccessCode.mockResolvedValue({ ...CAMPAIGN, access_code_set: true });
  clearCampaignAccessCode.mockResolvedValue({ ...CAMPAIGN, access_code_set: false });
  setCampaignSchedule.mockResolvedValue({ ...CAMPAIGN, closes_at: null });
  const { onChange } = setup({ access_code_set: true, closes_at: '2026-12-01T07:00:00Z' });
  userEvent.click(screen.getByRole('button', { name: 'Сроки и код' }));

  userEvent.type(screen.getByLabelText('Новое кодовое слово'), 'abc');
  userEvent.click(screen.getByRole('button', { name: 'Сменить слово' }));
  expect(await screen.findByText('От 4 до 64 символов')).toBeInTheDocument();
  expect(setCampaignAccessCode).not.toHaveBeenCalled();
  userEvent.type(screen.getByLabelText('Новое кодовое слово'), 'd  весна');
  userEvent.click(screen.getByRole('button', { name: 'Сменить слово' }));
  await waitFor(() => expect(setCampaignAccessCode).toHaveBeenCalledWith('c-1', 'abcd весна'));
  expect(await screen.findByText(/повторно его не показать/)).toBeInTheDocument();

  userEvent.click(screen.getByRole('button', { name: 'Снять слово' }));
  await waitFor(() => expect(clearCampaignAccessCode).toHaveBeenCalledWith('c-1'));
  userEvent.click(screen.getByRole('button', { name: 'Снять сроки' }));
  await waitFor(() => expect(setCampaignSchedule).toHaveBeenCalledWith(
    'c-1', { opens_at: null, closes_at: null }));
  expect(onChange).toHaveBeenCalledTimes(3);
});

test('ссылка «Открыть методику» ведёт в редактор методики кампании', () => {
  setup({ test_uuid: 't-1' });
  expect(screen.getByRole('link', { name: 'Открыть методику' }))
    .toHaveAttribute('href', '/supervisor/tests/t-1');
});
