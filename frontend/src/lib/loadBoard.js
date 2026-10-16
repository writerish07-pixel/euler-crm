import { toast } from "sonner";
import { get, apiErrorMessage } from "./api";

/** Dashboard GET. A failed call must not sit on “Loading…” forever. */
export function loadBoard(url, setData, setErr, errorMsg = "Could not load") {
  return get(url)
    .then((data) => {
      setData(data);
      if (setErr) setErr("");
      return data;
    })
    .catch((err) => {
      const msg = apiErrorMessage(err, errorMsg);
      if (setErr) setErr(msg);
      toast.error(msg);
      return null;
    });
}
