import { EDIT_ROLE_OPTIONS, CREATE_ROLE_OPTIONS, ROLE_LABELS } from './roleLabels';

describe('EDIT_ROLE_OPTIONS (Stage 31n-hotfix)', () => {
  const values = EDIT_ROLE_OPTIONS.map((o) => o.value);

  test('does NOT offer student as a selectable option', () => {
    expect(values).not.toContain('student');
  });

  test('offers exactly psychologist / supervisor / admin', () => {
    expect(values).toEqual(['psychologist', 'supervisor', 'admin']);
  });

  test('labels are the shared ROLE_LABELS (no divergence)', () => {
    EDIT_ROLE_OPTIONS.forEach((o) => {
      expect(o.label).toBe(ROLE_LABELS[o.value]);
    });
  });
});

describe('CREATE_ROLE_OPTIONS', () => {
  test('also excludes student (created via self-registration)', () => {
    expect(CREATE_ROLE_OPTIONS.map((o) => o.value)).not.toContain('student');
  });
});
