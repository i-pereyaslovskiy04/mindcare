import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MethodologyImportDialog from './MethodologyImportDialog';
import * as testsApi from '../../../../api/tests.api';

jest.mock('../../../../api/tests.api', () => ({
  ...jest.requireActual('../../../../api/tests.api'),
  importMethodology: jest.fn(),
  downloadMethodologyTemplate: jest.fn(),
}));

const file = () => new File(['x'], 'm.xlsx', {
  type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
});

function setup() {
  const onCreated = jest.fn();
  render(<MethodologyImportDialog open onClose={() => {}} onCreated={onCreated} />);
  return { onCreated };
}

test('ошибки файла показываются с адресом, черновик создать нельзя', async () => {
  testsApi.importMethodology.mockResolvedValue({
    ok: false, warnings: [], summary: null,
    errors: [{ sheet: 'Вопросы', row: 3, column: 'A', message: 'номера должны идти подряд' }],
  });
  setup();
  userEvent.upload(screen.getByLabelText(/Файл методики/), file());
  expect(await screen.findByRole('alert')).toHaveTextContent(
    'лист «Вопросы», строка 3, колонка A: номера должны идти подряд');
  expect(testsApi.importMethodology).toHaveBeenCalledWith(expect.any(File), {
    dryRun: true, base: '/api/admin/tests',
  });
  expect(screen.getByRole('button', { name: 'Создать черновик' })).toBeDisabled();
});

test('проверенный файл — сводка, замечания и создание черновика', async () => {
  testsApi.importMethodology
    .mockResolvedValueOnce({
      ok: true, errors: [], warnings: ['шкала «X» из правил не встречается ни в одном вопросе'],
      summary: { title: 'ИТО', questions: 91, options: 2, scales: 10, levels: 4, types: 6, interpretations: 0 },
    })
    .mockResolvedValueOnce({ ok: true, test_uuid: 'new-uuid' });
  const { onCreated } = setup();
  userEvent.upload(screen.getByLabelText(/Файл методики/), file());
  expect(await screen.findByText(/вопросов 91/)).toBeInTheDocument();
  expect(screen.getByText(/шкала «X»/)).toBeInTheDocument();
  userEvent.click(screen.getByRole('button', { name: 'Создать черновик' }));
  await waitFor(() => expect(onCreated).toHaveBeenCalledWith('new-uuid'));
  expect(testsApi.importMethodology).toHaveBeenLastCalledWith(expect.any(File), { base: '/api/admin/tests' });
});
