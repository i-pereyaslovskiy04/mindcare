/**
 * Стабильный React-ключ строки журнала.
 *
 * `entry_id` приходит СТРОКОЙ: id всех трёх журналов имеет тип BIGINT, а
 * JSON-число в JavaScript теряет точность за пределами 2^53. Приводить его к
 * Number нельзя — две соседние записи могли бы схлопнуться в один ключ.
 */
export function rowKey(item) {
  return `${item.source}:${item.entry_id}:${item.occurred_at}`;
}
