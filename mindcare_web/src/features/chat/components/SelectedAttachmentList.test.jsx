import { render, screen, fireEvent } from '@testing-library/react';
import SelectedAttachmentList from './SelectedAttachmentList';

function makeFile(name, size = 1024, type = 'application/pdf') {
  return new File([new ArrayBuffer(size)], name, { type });
}

const pdf = makeFile('отчёт.pdf');
const img = makeFile('фото.jpg', 2048, 'image/jpeg');

test('returns null for empty array', () => {
  const { container } = render(
    <SelectedAttachmentList files={[]} onRemove={jest.fn()} />,
  );
  expect(container).toBeEmptyDOMElement();
});

test('returns null when files is undefined', () => {
  const { container } = render(<SelectedAttachmentList onRemove={jest.fn()} />);
  expect(container).toBeEmptyDOMElement();
});

test('renders filename for each file', () => {
  render(<SelectedAttachmentList files={[pdf, img]} onRemove={jest.fn()} />);
  expect(screen.getByText('отчёт.pdf')).toBeInTheDocument();
  expect(screen.getByText('фото.jpg')).toBeInTheDocument();
});

test('renders human-readable file size', () => {
  render(<SelectedAttachmentList files={[pdf]} onRemove={jest.fn()} />);
  expect(screen.getByText('1.0 KB')).toBeInTheDocument();
});

test('remove button has accessible aria-label', () => {
  render(<SelectedAttachmentList files={[pdf]} onRemove={jest.fn()} />);
  expect(screen.getByRole('button', { name: /Убрать отчёт\.pdf/ })).toBeInTheDocument();
});

test('clicking remove calls onRemove with correct index', () => {
  const onRemove = jest.fn();
  render(<SelectedAttachmentList files={[pdf, img]} onRemove={onRemove} />);
  fireEvent.click(screen.getByRole('button', { name: /Убрать фото\.jpg/ }));
  expect(onRemove).toHaveBeenCalledWith(1);
});

test('uploading=true disables all remove buttons', () => {
  render(
    <SelectedAttachmentList files={[pdf, img]} onRemove={jest.fn()} uploading />,
  );
  screen.getAllByRole('button').forEach((btn) => expect(btn).toBeDisabled());
});

test('long filename is truncated by CSS (title attribute present)', () => {
  const longFile = makeFile('очень-длинное-имя-файла-который-не-помещается-в-одну-строку.pdf');
  render(<SelectedAttachmentList files={[longFile]} onRemove={jest.fn()} />);
  expect(
    screen.getByTitle('очень-длинное-имя-файла-который-не-помещается-в-одну-строку.pdf'),
  ).toBeInTheDocument();
});

test('multiple files all get individual remove buttons', () => {
  const files = [pdf, img, makeFile('doc.docx')];
  render(<SelectedAttachmentList files={files} onRemove={jest.fn()} />);
  expect(screen.getAllByRole('button')).toHaveLength(3);
});
