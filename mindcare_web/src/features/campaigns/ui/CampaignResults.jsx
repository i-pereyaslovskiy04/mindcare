import Button from '../../../components/UI/Button/Button';
import Select from '../../../components/UI/Select/Select';
import useCampaignResults, { EMPTY_FILTERS } from '../hooks/useCampaignResults';
import styles from './CampaignResults.module.css';

const LEVEL_CLASS = {
  low: styles.lvlLow,
  accent: styles.lvlAccent,
  maladaptive: styles.lvlMaladaptive,
  invalid: styles.lvlMaladaptive,
};
const LEVEL_ORDER = ['low', 'norm', 'accent', 'maladaptive'];
const GENDER = { male: 'Муж', female: 'Жен' };
const GENDER_OPTIONS = [
  { value: '', label: 'Все' }, { value: 'female', label: 'Женский' },
  { value: 'male', label: 'Мужской' },
];
const VALIDITY_OPTIONS = [
  { value: '', label: 'Все' }, { value: 'valid', label: 'Достоверные' },
  { value: 'invalid', label: 'Недостоверные (L или F > 5)' },
];

function Stat({ label, value }) {
  return (
    <div className={styles.stat} role="group" aria-label={label}>
      <span className={styles.statValue}>{value ?? '—'}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function GroupTable({ id, title, firstCol, groups }) {
  return (
    <section aria-labelledby={id}>
      <h4 id={id} className={styles.heading}>{title}</h4>
      <table className={styles.table}>
        <thead>
          <tr>
            <th scope="col">{firstCol}</th><th scope="col">Участников</th>
            <th scope="col">Достоверных</th><th scope="col">С типом</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <tr key={g.code}>
              <th scope="row">{g.label}</th><td>{g.count}</td><td>{g.valid}</td><td>{g.with_type}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}

function fmt(value) {
  return value == null ? '—' : String(value).replace('.', ',');
}

/**
 * Первичная обработка результатов кампании: фильтры (на сервере), итоги,
 * распределение уровней по шкалам, частоты типов, разбивки по факультетам и
 * полу, таблица баллов участников с цветом по уровню (и текстом уровня для
 * экранных дикторов). Те же расчёты, что на листе «Сводка» в xlsx.
 */
export default function CampaignResults({ campaignUuid }) {
  const { data, loading, error, filters, setFilters, refetch } =
    useCampaignResults(campaignUuid, true);
  const unfiltered = Object.values(filters).every((v) => !v);

  if (error) {
    return (
      <div className={styles.errorRow}>
        <p className={styles.error} role="alert">{error}</p>
        <Button type="button" variant="secondary" onClick={refetch}>Повторить</Button>
      </div>
    );
  }
  if (!data) return <p className={styles.muted} role="status">Загрузка результатов…</p>;
  if (!data.total_all) return <p className={styles.muted}>Пока никто не прошёл тестирование.</p>;

  const { summary, scales, level_labels: levelLabels } = data;
  // Факультеты фильтра — всех участников кампании (backend, без учёта фильтров).
  const facultyOptions = data.faculties.map((f) => ({ value: f.code, label: f.label }));
  const typeOptions = [
    { value: '', label: 'Все' },
    { value: '__none__', label: 'Без выраженного типа' },
    ...data.type_names.map((t) => ({ value: t, label: t })),
  ];

  return (
    <div className={styles.wrap} aria-busy={loading}>
      <div className={styles.filters}>
        <Select label="Факультет" value={filters.faculty_code} appearance="field"
          options={[{ value: '', label: 'Все' }, ...facultyOptions]}
          onChange={(v) => setFilters({ faculty_code: v })} />
        <Select label="Пол" value={filters.gender} appearance="field"
          options={GENDER_OPTIONS} onChange={(v) => setFilters({ gender: v })} />
        <Select label="Достоверность" value={filters.validity} appearance="field"
          options={VALIDITY_OPTIONS} onChange={(v) => setFilters({ validity: v })} />
        <Select label="Тип" value={filters.type} appearance="field"
          options={typeOptions} onChange={(v) => setFilters({ type: v })} />
        <Button type="button" variant="ghost" disabled={unfiltered}
          onClick={() => setFilters(EMPTY_FILTERS)}>
          Сбросить
        </Button>
      </div>

      <div className={styles.stats}>
        <Stat label={`Участников${unfiltered ? '' : ` (из ${data.total_all})`}`} value={summary.total} />
        <Stat label="Достоверных" value={summary.valid} />
        <Stat label="Недостоверных" value={summary.invalid} />
        <Stat label="С выраженным типом" value={summary.with_type} />
      </div>

      <section aria-labelledby={`${campaignUuid}-scales`}>
        <h4 id={`${campaignUuid}-scales`} className={styles.heading}>По шкалам</h4>
        <div className={styles.scroll}>
          <table className={styles.table}>
            <thead>
              <tr>
                <th scope="col">Шкала</th>
                <th scope="col">Среднее</th>
                <th scope="col">Мин–макс</th>
                {LEVEL_ORDER.map((code) => (
                  <th key={code} scope="col" className={LEVEL_CLASS[code]}>{levelLabels[code]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {summary.scales.map((s) => (
                <tr key={s.scale}>
                  <th scope="row">{s.label}</th>
                  <td>{fmt(s.mean)}</td>
                  <td>{s.min == null ? '—' : `${s.min}–${s.max}`}</td>
                  {'valid' in s.levels ? (
                    <td colSpan={4}>
                      достоверно: {s.levels.valid}; недостоверно: {s.levels.invalid}
                    </td>
                  ) : LEVEL_ORDER.map((code) => <td key={code}>{s.levels[code] ?? 0}</td>)}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <div className={styles.twoCol}>
        <section aria-labelledby={`${campaignUuid}-types`}>
          <h4 id={`${campaignUuid}-types`} className={styles.heading}>Типы (все шкалы типа ≥ 8)</h4>
          <table className={styles.table}>
            <thead>
              <tr><th scope="col">Тип</th><th scope="col">Всего</th><th scope="col">Недостоверно</th></tr>
            </thead>
            <tbody>
              {summary.types.map((t) => (
                <tr key={t.name}><th scope="row">{t.name}</th><td>{t.count}</td><td>{t.invalid}</td></tr>
              ))}
            </tbody>
          </table>
        </section>
        <GroupTable id={`${campaignUuid}-gender`} title="По полу" firstCol="Пол"
          groups={summary.by_gender} />
        <GroupTable id={`${campaignUuid}-faculty`} title="По факультетам" firstCol="Факультет"
          groups={summary.by_faculty} />
      </div>

      <section aria-labelledby={`${campaignUuid}-rows`}>
        <h4 id={`${campaignUuid}-rows`} className={styles.heading}>
          Участники ({data.items.length})
        </h4>
        <p className={styles.legend}>
          Цвет балла:{' '}
          {['low', 'accent', 'maladaptive'].map((code) => (
            <span key={code} className={`${styles.legendItem} ${LEVEL_CLASS[code]}`}>
              {levelLabels[code]}
            </span>
          ))}
        </p>
        <div className={styles.scroll}>
          <table className={`${styles.table} ${styles.rows}`}>
            <thead>
              <tr>
                <th scope="col">ФИО</th>
                <th scope="col">Факультет</th>
                <th scope="col">Пол</th>
                <th scope="col">Возраст</th>
                {scales.map((s) => (
                  <th key={s.code} scope="col" title={s.label}>{s.code}</th>
                ))}
                <th scope="col">Достоверность</th>
                <th scope="col">Тип</th>
              </tr>
            </thead>
            <tbody>
              {data.items.map((r) => (
                <tr key={r.uuid}>
                  <th scope="row">{r.full_name}</th>
                  <td>{r.faculty_label || r.faculty_code}</td>
                  <td>{GENDER[r.gender] || r.gender}</td>
                  <td>{r.age}</td>
                  {scales.map((s) => {
                    const code = r.levels[s.code];
                    return (
                      <td key={s.code} className={`${styles.score} ${LEVEL_CLASS[code] || ''}`}>
                        {r.scores[s.code] ?? '—'}
                        {code && code !== 'norm' && code !== 'valid' && (
                          <span className={styles.srOnly}>
                            {` (${code === 'invalid' ? 'недостоверно' : levelLabels[code]})`}
                          </span>
                        )}
                      </td>
                    );
                  })}
                  <td>{r.is_valid === false ? 'недостоверно' : 'достоверно'}</td>
                  <td className={styles.types}>{r.types.join('; ') || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}
