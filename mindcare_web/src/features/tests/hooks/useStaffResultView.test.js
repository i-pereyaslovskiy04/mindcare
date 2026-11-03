import { act, renderHook, waitFor } from '@testing-library/react';
import useStaffResultView, { AUDIT_UNAVAILABLE } from './useStaffResultView';
import { getStaffTestResult, getStaffTestResultAnswers } from '../../../api/tests.api';

jest.mock('../../../api/tests.api');

const apiError = (status) => Object.assign(new Error('x'), { status });
const detailOf = (uuid) => ({ uuid, total_score: uuid === 'A' ? 3 : 9, scales: [] });
const answersOf = (uuid) => ({ result_uuid: uuid, order: 'test_order', items: [] });

function deferred() {
  let resolve; let reject;
  const promise = new Promise((res, rej) => { resolve = res; reject = rej; });
  return { promise, resolve, reject };
}

beforeEach(() => jest.resetAllMocks());

describe('useStaffResultView', () => {
  it('переключение A→B: запоздалый ответ A не попадает в B', async () => {
    const a = deferred();
    const b = deferred();
    getStaffTestResult.mockReturnValueOnce(a.promise).mockReturnValueOnce(b.promise);
    const { result } = renderHook(() => useStaffResultView('c-1', 'psychologist'));
    act(() => { result.current.toggle('A'); });
    act(() => { result.current.toggle('B'); });
    await act(async () => { b.resolve(detailOf('B')); });
    await act(async () => { a.resolve(detailOf('A')); });
    expect(result.current.openUuid).toBe('B');
    expect(result.current.detail.data.total_score).toBe(9);
  });

  it('ответы прежнего результата не показываются у нового', async () => {
    getStaffTestResult.mockResolvedValue(detailOf('A'));
    const answers = deferred();
    getStaffTestResultAnswers.mockReturnValueOnce(answers.promise);
    const { result } = renderHook(() => useStaffResultView('c-1', 'psychologist'));
    act(() => { result.current.toggle('A'); });
    await waitFor(() => expect(result.current.detail.data).not.toBeNull());
    act(() => { result.current.loadAnswers(); });
    getStaffTestResult.mockResolvedValue(detailOf('B'));
    act(() => { result.current.toggle('B'); });
    await act(async () => { answers.resolve(answersOf('A')); });
    expect(result.current.openUuid).toBe('B');
    expect(result.current.answers.data).toBeNull();
  });

  it('смена клиента или роли очищает раскрытие и отбрасывает летящие ответы', async () => {
    const detail = deferred();
    getStaffTestResult.mockReturnValueOnce(detail.promise);
    const { result, rerender } = renderHook(
      ({ id, role }) => useStaffResultView(id, role),
      { initialProps: { id: 'c-1', role: 'psychologist' } },
    );
    act(() => { result.current.toggle('A'); });
    rerender({ id: 'c-2', role: 'psychologist' });
    expect(result.current.openUuid).toBeNull();
    await act(async () => { detail.resolve(detailOf('A')); });
    expect(result.current.detail.data).toBeNull();

    getStaffTestResult.mockResolvedValueOnce(detailOf('B'));
    act(() => { result.current.toggle('B'); });
    await waitFor(() => expect(result.current.detail.data).not.toBeNull());
    rerender({ id: 'c-2', role: 'supervisor' });
    expect(result.current.openUuid).toBeNull();
    expect(result.current.detail.data).toBeNull();
  });

  it('404 ответов: всё раскрытое очищается, список уведомляется', async () => {
    getStaffTestResult.mockResolvedValue(detailOf('A'));
    getStaffTestResultAnswers.mockRejectedValueOnce(apiError(404));
    const onAccessLost = jest.fn();
    const { result } = renderHook(() => useStaffResultView('c-1', 'psychologist', { onAccessLost }));
    act(() => { result.current.toggle('A'); });
    await waitFor(() => expect(result.current.detail.data).not.toBeNull());
    await act(async () => { result.current.loadAnswers(); });
    expect(onAccessLost).toHaveBeenCalledWith(expect.objectContaining({ status: 404 }));
    expect(result.current.openUuid).toBeNull();
    expect(result.current.detail.data).toBeNull();
  });

  it('503 детали: содержимого нет, сообщение о журнале', async () => {
    getStaffTestResult.mockRejectedValueOnce(apiError(503));
    const { result } = renderHook(() => useStaffResultView('c-1', 'psychologist'));
    await act(async () => { result.current.toggle('A'); });
    expect(result.current.detail.data).toBeNull();
    expect(result.current.detail.error).toBe(AUDIT_UNAVAILABLE);
  });

  it('скрытие ответов не отменяет загрузку детали; повторный клик не шлёт второй запрос', async () => {
    const detail = deferred();
    getStaffTestResult.mockReturnValueOnce(detail.promise);
    const answers = deferred();
    getStaffTestResultAnswers.mockReturnValueOnce(answers.promise);
    const { result } = renderHook(() => useStaffResultView('c-1', 'psychologist'));
    act(() => { result.current.toggle('A'); });
    act(() => { result.current.loadAnswers(); });
    act(() => { result.current.loadAnswers(); });
    expect(getStaffTestResultAnswers).toHaveBeenCalledTimes(1);
    act(() => { result.current.hideAnswers(); });
    await act(async () => { detail.resolve(detailOf('A')); });
    await act(async () => { answers.resolve(answersOf('A')); });
    expect(result.current.detail.data.total_score).toBe(3);
    expect(result.current.answers.data).toBeNull();
  });
});
