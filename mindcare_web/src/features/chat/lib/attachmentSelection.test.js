import { mergeSelectedFiles, MAX_SELECTED_FILES } from './attachmentSelection';

function makeFile(name, size = 1024) {
  return new File([new ArrayBuffer(size)], name, { type: 'application/pdf' });
}

test('MAX_SELECTED_FILES is 5', () => {
  expect(MAX_SELECTED_FILES).toBe(5);
});

test('accepts valid files and returns them with no error', () => {
  const { files, error } = mergeSelectedFiles([], [makeFile('a.pdf')]);
  expect(files).toHaveLength(1);
  expect(error).toBeNull();
});

test('merges incoming with existing files', () => {
  const existing = [makeFile('a.pdf')];
  const { files } = mergeSelectedFiles(existing, [makeFile('b.pdf')]);
  expect(files).toHaveLength(2);
  expect(files[0].name).toBe('a.pdf');
  expect(files[1].name).toBe('b.pdf');
});

test('silently rejects empty files (size === 0)', () => {
  const empty = new File([], 'empty.pdf', { type: 'application/pdf' });
  const { files, error } = mergeSelectedFiles([], [empty]);
  expect(files).toHaveLength(0);
  expect(error).toBeNull();
});

test('filters empty files from a mixed batch', () => {
  const valid = makeFile('valid.pdf');
  const empty = new File([], 'empty.pdf', { type: 'application/pdf' });
  const { files } = mergeSelectedFiles([], [empty, valid]);
  expect(files).toHaveLength(1);
  expect(files[0].name).toBe('valid.pdf');
});

test('enforces MAX_SELECTED_FILES limit', () => {
  const batch = Array.from({ length: 6 }, (_, i) => makeFile(`f${i}.pdf`));
  const { files, error } = mergeSelectedFiles([], batch);
  expect(files).toHaveLength(MAX_SELECTED_FILES);
  expect(error).not.toBeNull();
});

test('error message mentions the limit number', () => {
  const batch = Array.from({ length: 6 }, (_, i) => makeFile(`f${i}.pdf`));
  const { error } = mergeSelectedFiles([], batch);
  expect(error).toMatch(/5/);
});

test('existing + incoming total exceeding limit is truncated', () => {
  const existing = Array.from({ length: 3 }, (_, i) => makeFile(`e${i}.pdf`));
  const incoming = Array.from({ length: 4 }, (_, i) => makeFile(`n${i}.pdf`));
  const { files, error } = mergeSelectedFiles(existing, incoming);
  expect(files).toHaveLength(MAX_SELECTED_FILES);
  expect(error).not.toBeNull();
});

test('exactly MAX_SELECTED_FILES files: no error', () => {
  const batch = Array.from({ length: 5 }, (_, i) => makeFile(`f${i}.pdf`));
  const { files, error } = mergeSelectedFiles([], batch);
  expect(files).toHaveLength(5);
  expect(error).toBeNull();
});

test('empty incoming returns existing unchanged', () => {
  const existing = [makeFile('a.pdf')];
  const { files, error } = mergeSelectedFiles(existing, []);
  expect(files).toHaveLength(1);
  expect(error).toBeNull();
});

test('original File objects are preserved (identity check)', () => {
  const orig = makeFile('original.pdf');
  const { files } = mergeSelectedFiles([orig], [makeFile('new.pdf')]);
  expect(files[0]).toBe(orig);
});

test('FileList-like object (iterable) is handled', () => {
  const file = makeFile('doc.pdf');
  // Simulate FileList-like iterable
  const fileList = { 0: file, length: 1, [Symbol.iterator]: Array.prototype[Symbol.iterator] };
  const { files } = mergeSelectedFiles([], Array.from(fileList));
  expect(files).toHaveLength(1);
});
