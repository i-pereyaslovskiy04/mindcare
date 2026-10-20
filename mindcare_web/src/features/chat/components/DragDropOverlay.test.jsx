import { render, screen } from '@testing-library/react';
import DragDropOverlay from './DragDropOverlay';

test('returns null when visible=false', () => {
  const { container } = render(<DragDropOverlay visible={false} />);
  expect(container).toBeEmptyDOMElement();
});

test('returns null when visible prop is omitted', () => {
  const { container } = render(<DragDropOverlay />);
  expect(container).toBeEmptyDOMElement();
});

test('renders title when visible=true', () => {
  render(<DragDropOverlay visible />);
  expect(screen.getByText('Перетащите файлы сюда')).toBeInTheDocument();
});

test('renders subtitle when visible=true', () => {
  render(<DragDropOverlay visible />);
  expect(screen.getByText('Они будут добавлены к сообщению')).toBeInTheDocument();
});

test('has role=status for accessibility', () => {
  render(<DragDropOverlay visible />);
  expect(screen.getByRole('status')).toBeInTheDocument();
});

test('hidden overlay has no status role', () => {
  render(<DragDropOverlay visible={false} />);
  expect(screen.queryByRole('status')).not.toBeInTheDocument();
});
