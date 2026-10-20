import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import TestTakePage from './TestTakePage';
import * as testsApi from '../../../api/tests.api';

// react-router-dom (v7) не резолвится jest-резолвером в этом проекте — как и в
// остальных тестах, мокаем виртуально.
jest.mock('react-router-dom', () => ({
  useParams: () => ({ uuid: 'test-uuid' }),
  useNavigate: () => jest.fn(),
}), { virtual: true });

jest.mock('../../../api/tests.api');

const TEST = {
  uuid: 'test-uuid',
  title: 'Т',
  description: '',
  time_limit_min: null,   // без тайм-лимита — таймер не должен мешать тесту
  questions: [{
    id: 1, question_text: 'Q1', question_order: 1, question_type: 'single_choice',
    is_required: true, config: {}, media: [],
    options: [
      { id: 10, option_text: 'нет', option_order: 0, media: [] },
      { id: 11, option_text: 'да', option_order: 1, media: [] },
    ],
  }],
};

describe('TestTakePage — ручное завершение теста', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    testsApi.getTestConsent.mockResolvedValue({ accepted: true });
    testsApi.getTestForTake.mockResolvedValue(TEST);
    testsApi.submitTest.mockResolvedValue({ uuid: 'result-uuid' });
  });

  it('шлёт timed_out=false (не MouseEvent) при клике «Завершить»', async () => {
    render(<TestTakePage />);

    // Ждём загрузки и отвечаем на единственный обязательный вопрос.
    const yesOption = await screen.findByText('да');
    fireEvent.click(yesOption);

    const submitBtn = await screen.findByText('Завершить и узнать результат');
    fireEvent.click(submitBtn);

    await waitFor(() => expect(testsApi.submitTest).toHaveBeenCalledTimes(1));

    const [, , timedOutArg] = testsApi.submitTest.mock.calls[0];
    // Регрессия: onClick={submit} (без обёртки) передавал сюда MouseEvent —
    // truthy объект с циклическими ссылками, а не false. JSON.stringify падал
    // с "cannot serialize cyclic structures", и (даже если бы не упал)
    // is_required-проверка молча пропускалась бы на каждом обычном сабмите.
    expect(timedOutArg).toBe(false);
  });
});
