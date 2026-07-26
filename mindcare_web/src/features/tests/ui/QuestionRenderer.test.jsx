/**
 * QuestionRenderer — доступность вопросов теста (ГОСТ Р 52872-2019):
 * текстовый эквивалент прогресса, доступные имена групп и контролов.
 */

import { render, screen } from '@testing-library/react';
import QuestionRenderer from './QuestionRenderer';

const single = {
  id: 7,
  question_type: 'single_choice',
  question_text: 'Как часто вы чувствуете тревогу?',
  is_required: true,
  options: [
    { id: 1, option_text: 'Никогда' },
    { id: 2, option_text: 'Иногда' },
  ],
};

describe('QuestionRenderer — доступность', () => {
  test('показывает текстовый эквивалент прогресса «Вопрос N из M»', () => {
    render(
      <QuestionRenderer question={single} index={4} total={20} onChange={() => {}} />
    );
    expect(screen.getByText(/Вопрос 5 из 20/)).toBeInTheDocument();
  });

  test('группа вариантов имеет доступное имя (текст вопроса)', () => {
    render(
      <QuestionRenderer question={single} index={0} total={3} onChange={() => {}} />
    );
    const group = screen.getByRole('radiogroup');
    expect(group).toHaveAccessibleName(/Как часто вы чувствуете тревогу/);
  });

  test('обязательность вопроса читается текстом, а не только звёздочкой', () => {
    render(
      <QuestionRenderer question={single} index={0} total={3} onChange={() => {}} />
    );
    expect(screen.getByText('(обязательный вопрос)')).toBeInTheDocument();
  });

  test('множественный выбор — группа с доступным именем', () => {
    render(
      <QuestionRenderer
        question={{ ...single, question_type: 'multiple_choice' }}
        index={1}
        total={5}
        value={[]}
        onChange={() => {}}
      />
    );
    expect(screen.getByRole('group')).toHaveAccessibleName(
      /Как часто вы чувствуете тревогу/
    );
  });

  test('шкала — слайдер с доступным именем и текстовым значением', () => {
    render(
      <QuestionRenderer
        question={{ ...single, question_type: 'scale', config: { min: 0, max: 10 } }}
        index={2}
        total={5}
        value={7}
        onChange={() => {}}
      />
    );
    const slider = screen.getByRole('slider');
    expect(slider).toHaveAccessibleName(/Как часто вы чувствуете тревогу/);
    expect(slider).toHaveAttribute('aria-valuetext', '7 из 10');
  });

  test('свободный ответ — textarea с доступным именем', () => {
    render(
      <QuestionRenderer
        question={{ ...single, question_type: 'free_text' }}
        index={0}
        total={2}
        value=""
        onChange={() => {}}
      />
    );
    expect(screen.getByRole('textbox')).toHaveAccessibleName(
      /Как часто вы чувствуете тревогу/
    );
  });
});
