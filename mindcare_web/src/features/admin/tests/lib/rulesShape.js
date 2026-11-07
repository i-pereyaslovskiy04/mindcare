/**
 * Правила обработки методики (ADR-037, ScoringRulesV1) ↔ форма конструктора.
 *
 * Форма:
 *   { enabled, instruction, invalid_mark, type_threshold,
 *     scales: [{ _key, code, label, main, max_valid,       // max_valid '' — не шкала достоверности
 *                own_levels, levels: [{ _key, code, label, min, max }],    // свои уровни основной шкалы
 *                norms: { enabled, kind, label, groups: [{ _key, gender, age_min, age_max,
 *                         extra: [условия backend как есть], table: [{ _key, min, max, value }] }] } }],
 *     levels: [{ _key, code, label, min, max }],
 *     types:  [{ _key, name, scales: [code] }] }
 *
 * Проверку согласованности и все вычисления делает backend (analyze /
 * preview-score) — здесь только перекладка полей, без бизнес-правил.
 */

export const DEFAULT_INVALID_MARK = 'недостоверно';

export function emptyRules() {
  return {
    enabled: false,
    instruction: '',
    invalid_mark: DEFAULT_INVALID_MARK,
    type_threshold: '',
    scales: [],
    levels: [],
    types: [],
  };
}

const levelFromBackend = (lv, nextKey) => ({
  _key: nextKey(),
  code: lv.code,
  label: lv.label,
  min: String(lv.min),
  max: String(lv.max),
});

const levelsToBackend = (levels) => levels
  .filter((lv) => lv.code.trim())
  .map((lv) => ({
    code: lv.code.trim(),
    label: lv.label.trim() || lv.code.trim(),
    min: Number(lv.min),
    max: Number(lv.max),
  }));

export const NORM_KINDS = [
  { value: 'sten', label: 'Стены' },
  { value: 't', label: 'T-баллы' },
  { value: 'stanine', label: 'Станайны' },
  { value: 'percentile', label: 'Процентили' },
  { value: 'custom', label: 'Другое' },
];

export function emptyNormGroup(nextKey) {
  return {
    _key: nextKey(), gender: '', age_min: '', age_max: '', extra: [],
    table: [{ _key: nextKey(), min: '', max: '', value: '' }],
  };
}

function normsFromBackend(norms, nextKey) {
  if (!norms) return { enabled: false, kind: 'sten', label: '', groups: [] };
  return {
    enabled: true,
    kind: norms.kind || 'custom',
    label: norms.label || '',
    groups: (norms.groups || []).map((g) => {
      const by = Object.fromEntries((g.when || []).map((c) => [c.field, c]));
      return {
        _key: nextKey(),
        gender: by.gender?.eq || '',
        age_min: by.age?.min != null ? String(by.age.min) : '',
        age_max: by.age?.max != null ? String(by.age.max) : '',
        // Условия, которых нет в форме (например, факультет), сохраняются как есть.
        extra: (g.when || []).filter((c) => c.field !== 'gender' && c.field !== 'age'),
        table: (g.table || []).map((r) => ({
          _key: nextKey(), min: String(r.min), max: String(r.max), value: String(r.value),
        })),
      };
    }),
  };
}

function normsToBackend(norms) {
  if (!norms?.enabled) return null;
  const groups = norms.groups.map((g) => {
    const when = [];
    if (g.gender) when.push({ field: 'gender', eq: g.gender });
    if (!isBlankValue(g.age_min) || !isBlankValue(g.age_max)) {
      when.push({
        field: 'age',
        ...(isBlankValue(g.age_min) ? {} : { min: Number(g.age_min) }),
        ...(isBlankValue(g.age_max) ? {} : { max: Number(g.age_max) }),
      });
    }
    return {
      when: [...when, ...(g.extra || [])],
      table: g.table
        .filter((r) => !isBlankValue(r.min) && !isBlankValue(r.max) && !isBlankValue(r.value))
        .map((r) => ({ min: Number(r.min), max: Number(r.max), value: Number(r.value) })),
    };
  }).filter((g) => g.table.length);
  if (!groups.length) return null;
  return { kind: norms.kind || 'custom', ...(norms.label.trim() ? { label: norms.label.trim() } : {}), groups };
}

function isBlankValue(v) {
  return v === '' || v == null;
}

export function fromBackendRules(rules, nextKey) {
  if (!rules) return emptyRules();
  const limits = Object.fromEntries(
    (rules.validity?.scales || []).map((v) => [v.code, v.max_valid]),
  );
  return {
    enabled: true,
    instruction: rules.instruction || '',
    invalid_mark: rules.validity?.invalid_mark || DEFAULT_INVALID_MARK,
    type_threshold: rules.types ? String(rules.types.threshold) : '',
    scales: (rules.scales || []).map((s) => ({
      _key: nextKey(),
      code: s.code,
      label: s.label,
      main: Boolean(s.main),
      max_valid: s.code in limits ? String(limits[s.code]) : '',
      own_levels: Boolean(s.levels?.length),
      levels: (s.levels || []).map((lv) => levelFromBackend(lv, nextKey)),
      norms: normsFromBackend(s.norms, nextKey),
    })),
    levels: (rules.levels || []).map((lv) => levelFromBackend(lv, nextKey)),
    types: (rules.types?.items || []).map((t) => ({
      _key: nextKey(),
      name: t.name,
      scales: [...t.scales],
    })),
  };
}

const isBlank = (v) => v === '' || v == null;

/** Форма → payload `scoring_rules` (null — правил нет). */
export function toBackendRules(form) {
  if (!form || !form.enabled) return null;
  const scales = form.scales.filter((s) => s.code.trim());
  const out = {
    version: 1,
    instruction: form.instruction.trim() || null,
    scales: scales.map((s) => {
      const own = s.main && s.own_levels ? levelsToBackend(s.levels || []) : [];
      const norms = normsToBackend(s.norms);
      return {
        code: s.code.trim(),
        label: s.label.trim() || s.code.trim(),
        main: Boolean(s.main),
        ...(own.length ? { levels: own } : {}),
        ...(norms ? { norms } : {}),
      };
    }),
    levels: levelsToBackend(form.levels),
    validity: null,
    types: null,
  };
  const validity = scales.filter((s) => !isBlank(s.max_valid));
  if (validity.length) {
    out.validity = {
      scales: validity.map((s) => ({ code: s.code.trim(), max_valid: Number(s.max_valid) })),
      invalid_mark: form.invalid_mark.trim() || DEFAULT_INVALID_MARK,
    };
  }
  const types = form.types.filter((t) => t.name.trim() && t.scales.length);
  if (types.length) {
    out.types = {
      threshold: Number(form.type_threshold) || 0,
      items: types.map((t) => ({ name: t.name.trim(), scales: [...t.scales] })),
    };
  }
  return out;
}

export function snapshotRules(form) {
  return JSON.stringify(toBackendRules(form));
}

/**
 * Шкалы, которые встречаются в вопросах, но ещё не объявлены в правилах, —
 * для кнопки «Добавить шкалы из вопросов». Порядок — как в вопросах.
 */
export function missingScaleCodes(rulesForm, questions) {
  const declared = new Set(rulesForm.scales.map((s) => s.code.trim()));
  const seen = [];
  questions.forEach((q) => {
    const code = (q.scale || '').trim();
    if (code && !declared.has(code) && !seen.includes(code)) seen.push(code);
  });
  return seen;
}
