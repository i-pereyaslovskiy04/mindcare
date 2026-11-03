import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import AdminTestsPage from './AdminTestsPage';
import { useAdminTests } from '../hooks/useAdminTests';
import { publishTest } from '../../../../api/tests.api';
import { notifyReviewQueueChanged } from '../../../moderation/lib/reviewQueueEvents';

jest.mock('../hooks/useAdminTests');
jest.mock('../../../../api/tests.api');
jest.mock('../../../moderation/lib/reviewQueueEvents');
jest.mock('react-router-dom', () => ({ useNavigate: () => jest.fn() }), { virtual: true });

const ITEM = {
  uuid: 't-1', title: 'Шкала тревоги', scoring: 'sum', version: 1, is_active: true,
  status: 'in_review', question_count: 3, categories: [], tags: [],
  created_at: '2026-10-01T10:00:00Z', updated_at: '2026-10-02T11:22:33.123456+00:00',
  created_by_name: 'Автор',
};
const conflict = (current) => Object.assign(new Error('Состояние теста изменилось.'), {
  status: 409, code: 'test_state_changed', body: { current_status: current },
});

let refetch;
beforeEach(() => {
  refetch = jest.fn();
  useAdminTests.mockReturnValue({
    items: [ITEM], loading: false, error: null, total: 1, page: 1, setPage: jest.fn(),
    query: '', setQuery: jest.fn(), filters: {}, setFilters: jest.fn(), refetch,
  });
});

test('публикация передаёт строку списка (ожидаемое состояние) целиком', async () => {
  publishTest.mockResolvedValueOnce({});
  render(<AdminTestsPage />);
  userEvent.click(screen.getByRole('button', { name: 'Опубликовать «Шкала тревоги»' }));
  await waitFor(() => expect(publishTest).toHaveBeenCalledWith(ITEM));
  await waitFor(() => expect(refetch).toHaveBeenCalled());
});

test('409 test_state_changed: сообщение, список и очередь обновлены', async () => {
  publishTest.mockRejectedValueOnce(conflict('needs_changes'));
  render(<AdminTestsPage />);
  userEvent.click(screen.getByRole('button', { name: 'Опубликовать «Шкала тревоги»' }));
  expect(await screen.findByText(/Состояние теста изменилось/)).toBeInTheDocument();
  expect(refetch).toHaveBeenCalled();
  expect(notifyReviewQueueChanged).toHaveBeenCalled();
});

test('повтор уже принятого решения: без сообщения об ошибке, только обновление', async () => {
  publishTest.mockRejectedValueOnce(conflict('published'));
  render(<AdminTestsPage />);
  userEvent.click(screen.getByRole('button', { name: 'Опубликовать «Шкала тревоги»' }));
  await waitFor(() => expect(refetch).toHaveBeenCalled());
  expect(screen.queryByText(/Состояние теста изменилось/)).toBeNull();
});
