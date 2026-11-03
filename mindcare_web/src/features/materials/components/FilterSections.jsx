import FilterChip from '../../../components/UI/FilterChip/FilterChip';

const CheckIcon = () => (
  <svg width="9" height="8" viewBox="0 0 9 8" fill="none" aria-hidden="true">
    <path d="M1 4l2.5 2.5L8 1" stroke="currentColor" strokeWidth="1.5"
      strokeLinecap="round" strokeLinejoin="round" />
  </svg>
);

function Section({ title, options, value, onChange, size, classes }) {
  if (!options.length) return null;
  return (
    <section className={classes.section}>
      <h3 className={classes.sectionTitle}>{title}</h3>
      <div className={classes.tagGrid} role="group" aria-label={title}>
        {options.map((opt) => {
          const active = value === opt.value;
          return (
            <FilterChip
              key={opt.value}
              active={active}
              size={size}
              // Один выбор в секции: API статей принимает один category_id и один tag_uuid.
              onClick={() => onChange(active ? null : opt.value)}
              icon={active ? <CheckIcon /> : null}
            >
              {opt.label}
            </FilterChip>
          );
        })}
      </div>
    </section>
  );
}

/**
 * Секции фильтров библиотеки — общие для FiltersDropdown и FilterSheet:
 * «Тип материала» (категория) и «Тема» (тег). Секция без вариантов не
 * показывается. classes — section / sectionTitle / tagGrid панели.
 */
export default function FilterSections({
  category, onCategoryChange, categoryOptions = [],
  tag, onTagChange, tagOptions = [],
  size, classes,
}) {
  return (
    <>
      <Section title="Тип материала" options={categoryOptions} value={category}
        onChange={onCategoryChange} size={size} classes={classes} />
      <Section title="Тема" options={tagOptions} value={tag}
        onChange={onTagChange} size={size} classes={classes} />
    </>
  );
}
