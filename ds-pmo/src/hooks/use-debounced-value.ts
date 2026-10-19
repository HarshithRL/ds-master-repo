import { useEffect, useState } from "react";

/**
 * Returns `value` after `delay` ms of stillness. Used by admin tables
 * (audit log, snapshots) to debounce free-text search inputs.
 */
export function useDebouncedValue<T>(value: T, delay = 300): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const t = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(t);
  }, [value, delay]);
  return debounced;
}
