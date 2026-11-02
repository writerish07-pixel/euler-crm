import { useEffect, useState } from "react";

/**
 * The value, but only after the user has stopped typing for `ms`.
 *
 * Search boxes used to call the server on every key press. On a slow phone
 * connection the answers came back out of order, so the list flickered and
 * could end on the result for a half-typed number.
 */
export function useDebouncedValue(value, ms = 300) {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    if (value === settled) return undefined;
    // Clearing the box should show the full list straight away.
    if (value === "" || value == null) {
      setSettled(value);
      return undefined;
    }
    const t = setTimeout(() => setSettled(value), ms);
    return () => clearTimeout(t);
  }, [value, ms, settled]);
  return settled;
}
