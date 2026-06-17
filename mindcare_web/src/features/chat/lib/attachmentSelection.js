export const MAX_SELECTED_FILES = 5;

/**
 * Merges incoming browser File objects into the current selection.
 *
 * - Silently filters empty files (size === 0)
 * - Enforces MAX_SELECTED_FILES limit (truncates + returns user-visible error)
 *
 * @param {File[]} existing
 * @param {FileList|File[]} incoming
 * @returns {{ files: File[], error: string | null }}
 */
export function mergeSelectedFiles(existing, incoming) {
  const valid = Array.from(incoming).filter((f) => f.size > 0);
  const next = [...existing, ...valid];

  if (next.length > MAX_SELECTED_FILES) {
    return {
      files: next.slice(0, MAX_SELECTED_FILES),
      error: `Можно прикрепить не больше ${MAX_SELECTED_FILES} файлов.`,
    };
  }

  return { files: next, error: null };
}
