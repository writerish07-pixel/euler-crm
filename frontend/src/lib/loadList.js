import { toast } from "sonner";
import { get, apiErrorMessage } from "./api";

/** Load a register. A failed call must not look like an empty desk. */
export function loadList(url, setRows, params, errorMsg = "Could not load") {
  return get(url, params)
    .then((data) => {
      const rows = Array.isArray(data) ? data : [];
      setRows(rows);
      return rows;
    })
    .catch((err) => {
      setRows([]);
      toast.error(apiErrorMessage(err, errorMsg));
      return [];
    });
}
