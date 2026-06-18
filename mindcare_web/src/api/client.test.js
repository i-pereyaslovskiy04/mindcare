import { parseErrorMessage, apiFetchBlob, saveBlobToDisk } from './client';

describe('parseErrorMessage', () => {
  test('detail-строка используется как сообщение', () => {
    expect(parseErrorMessage({ detail: 'Email уже зарегистрирован' }, 409))
      .toBe('Email уже зарегистрирован');
  });

  test('detail-массив из одного элемента → его msg', () => {
    expect(parseErrorMessage({ detail: [{ msg: 'Field required' }] }, 422))
      .toBe('Field required');
  });

  test('detail-массив из нескольких → оба сообщения через "; "', () => {
    const msg = parseErrorMessage({ detail: [{ msg: 'A' }, { msg: 'B' }] }, 422);
    expect(msg).toContain('A');
    expect(msg).toContain('B');
    expect(msg).toBe('A; B');
  });

  test('detail c loc → читаемое поле перед msg (без префикса body)', () => {
    expect(parseErrorMessage({ detail: [{ loc: ['body', 'email'], msg: 'Invalid' }] }, 422))
      .toBe('email: Invalid');
  });

  test('никогда не превращается в "[object Object]"', () => {
    const msg = parseErrorMessage({ detail: [{ type: 'x', loc: ['body', 'a'], msg: 'нужно', input: null }] }, 422);
    expect(msg).not.toContain('[object Object]');
  });

  test('message-строка как fallback при отсутствии detail', () => {
    expect(parseErrorMessage({ message: 'Что-то пошло не так' }, 500))
      .toBe('Что-то пошло не так');
  });

  test('неизвестный формат → HTTP <status>', () => {
    expect(parseErrorMessage({}, 503)).toBe('HTTP 503');
  });

  test('пустое тело без статуса → общий fallback', () => {
    expect(parseErrorMessage({}, undefined)).toBe('Ошибка запроса');
  });
});

// ── saveBlobToDisk (Stage 32d-hotfix-b) ──────────────────────────────────────

describe('saveBlobToDisk', () => {
  // fetchFn recreated in beforeEach — jest.restoreAllMocks() resets standalone
  // jest.fn() implementations (same as mockReset), so const-level definition breaks.
  let fetchFn;

  beforeEach(() => {
    fetchFn = jest.fn().mockResolvedValue(new Blob(['content'], { type: 'application/pdf' }));
    global.URL.createObjectURL = jest.fn(() => 'blob:test-url');
    global.URL.revokeObjectURL = jest.fn();
    delete window.showSaveFilePicker;
  });

  afterEach(() => {
    jest.restoreAllMocks();
    jest.clearAllMocks();
  });

  // ── Anchor fallback (нет File System Access API) ──────────────────────────

  describe('anchor fallback (no showSaveFilePicker)', () => {
    let appendSpy;

    beforeEach(() => {
      appendSpy = jest.spyOn(document.body, 'appendChild').mockImplementation((el) => el);
      jest.spyOn(document.body, 'removeChild').mockImplementation(() => null);
      jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
    });

    test('calls URL.createObjectURL with a Blob', async () => {
      await saveBlobToDisk(fetchFn, 'test.pdf');
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
      expect(URL.createObjectURL).toHaveBeenCalledWith(expect.any(Blob));
    });

    test('wraps blob as application/octet-stream (браузер не открывает документ inline)', async () => {
      let passedBlob;
      URL.createObjectURL.mockImplementation((b) => { passedBlob = b; return 'blob:test-url'; });
      await saveBlobToDisk(fetchFn, 'spreadsheet.xlsx');
      expect(passedBlob?.type).toBe('application/octet-stream');
    });

    test('sets download attribute via setAttribute (not only .download)', async () => {
      let capturedAnchor = null;
      appendSpy.mockImplementation((el) => { capturedAnchor = el; return el; });
      await saveBlobToDisk(fetchFn, 'presentation.pptx');
      expect(capturedAnchor?.getAttribute('download')).toBe('presentation.pptx');
    });

    test('filename defaults to "файл" when null', async () => {
      let capturedAnchor = null;
      appendSpy.mockImplementation((el) => { capturedAnchor = el; return el; });
      await saveBlobToDisk(fetchFn, null);
      expect(capturedAnchor?.getAttribute('download')).toBe('файл');
    });

    test('does not navigate away from current page', async () => {
      const originalHref = window.location.href;
      await saveBlobToDisk(fetchFn, 'test.pdf');
      expect(window.location.href).toBe(originalHref);
    });

    test('URL.revokeObjectURL deferred via setTimeout, not synchronous', async () => {
      jest.useFakeTimers();
      await saveBlobToDisk(fetchFn, 'test.pdf');
      expect(URL.revokeObjectURL).not.toHaveBeenCalled();
      jest.runAllTimers();
      expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
      jest.useRealTimers();
    });
  });

  // ── File System Access API primary path ───────────────────────────────────

  describe('File System Access API (showSaveFilePicker available)', () => {
    let mockWritable;
    let mockFileHandle;

    beforeEach(() => {
      mockWritable = {
        write: jest.fn().mockResolvedValue(undefined),
        close: jest.fn().mockResolvedValue(undefined),
      };
      mockFileHandle = {
        createWritable: jest.fn().mockResolvedValue(mockWritable),
      };
      window.showSaveFilePicker = jest.fn().mockResolvedValue(mockFileHandle);
    });

    afterEach(() => {
      delete window.showSaveFilePicker;
    });

    test('calls showSaveFilePicker with suggestedName', async () => {
      await saveBlobToDisk(fetchFn, 'document.docx');
      expect(window.showSaveFilePicker).toHaveBeenCalledWith({ suggestedName: 'document.docx' });
    });

    test('calls writable.write with a Blob from fetchFn', async () => {
      await saveBlobToDisk(fetchFn, 'document.docx');
      // Blob instances compare poorly in jest — verify type instead of reference.
      expect(mockWritable.write).toHaveBeenCalledWith(expect.any(Blob));
    });

    test('calls writable.close after write', async () => {
      await saveBlobToDisk(fetchFn, 'document.docx');
      expect(mockWritable.close).toHaveBeenCalled();
    });

    test('does NOT call URL.createObjectURL (no blob navigation)', async () => {
      await saveBlobToDisk(fetchFn, 'document.docx');
      expect(URL.createObjectURL).not.toHaveBeenCalled();
    });

    test('cancel (AbortError) re-throws AbortError and does not write', async () => {
      window.showSaveFilePicker = jest.fn().mockRejectedValue(
        new DOMException('Cancelled', 'AbortError'),
      );
      await expect(saveBlobToDisk(fetchFn, 'test.pdf')).rejects.toMatchObject({ name: 'AbortError' });
      expect(mockWritable.write).not.toHaveBeenCalled();
    });

    test('non-AbortError from picker falls through to anchor fallback', async () => {
      window.showSaveFilePicker = jest.fn().mockRejectedValue(
        new DOMException('Not allowed', 'NotAllowedError'),
      );
      const appendSpy = jest.spyOn(document.body, 'appendChild').mockImplementation((el) => el);
      const removeSpy = jest.spyOn(document.body, 'removeChild').mockImplementation(() => null);
      const clickSpy = jest.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

      await saveBlobToDisk(fetchFn, 'test.pdf');
      expect(URL.createObjectURL).toHaveBeenCalledTimes(1);

      appendSpy.mockRestore();
      removeSpy.mockRestore();
      clickSpy.mockRestore();
    });
  });
});

// ── apiFetchBlob filename parsing (Stage 32d-hotfix) ─────────────────────────

function _mockFetch(cdHeader) {
  jest.spyOn(global, 'fetch').mockResolvedValue({
    ok: true,
    status: 200,
    blob: async () => new Blob(['data']),
    headers: { get: (name) => (name.toLowerCase() === 'content-disposition' ? cdHeader : null) },
  });
}

describe('apiFetchBlob — Content-Disposition filename', () => {
  afterEach(() => jest.restoreAllMocks());

  test('RFC 5987: кириллическое имя файла декодируется корректно', async () => {
    _mockFetch("attachment; filename*=UTF-8''%D0%BE%D1%82%D1%87%D1%91%D1%82.pdf");
    const { filename } = await apiFetchBlob('/test');
    expect(filename).toBe('отчёт.pdf');
  });

  test('RFC 5987: ASCII имя файла без процентного кодирования', async () => {
    _mockFetch("attachment; filename*=UTF-8''report.pdf");
    const { filename } = await apiFetchBlob('/test');
    expect(filename).toBe('report.pdf');
  });

  test('RFC 5987: Office имя файла с пробелами и расширением .docx', async () => {
    _mockFetch("attachment; filename*=UTF-8''My%20Document.docx");
    const { filename } = await apiFetchBlob('/test');
    expect(filename).toBe('My Document.docx');
  });

  test('нет Content-Disposition заголовка → filename: null', async () => {
    _mockFetch(null);
    const { filename } = await apiFetchBlob('/test');
    expect(filename).toBeNull();
  });

  test('возвращает blob объект', async () => {
    _mockFetch(null);
    const { blob } = await apiFetchBlob('/test');
    expect(blob).toBeInstanceOf(Blob);
  });
});
