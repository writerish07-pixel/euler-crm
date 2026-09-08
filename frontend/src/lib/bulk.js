import { post } from "./api";

/** Desk-sized slice so one Railway/proxy hop stays well under a minute. */
export const BULK_CHUNK_SIZE = 50;

/**
 * POST a bulk mutation in slices. Each slice uses the no-retry bulk client.
 * `countKey` is the numeric success field on the JSON body (movedCount, filled, …).
 */
export async function postInChunks(url, {
  items,
  itemsKey,
  extra = {},
  chunkSize = BULK_CHUNK_SIZE,
  countKey = "movedCount",
  onProgress,
} = {}) {
  const list = Array.isArray(items) ? items : [];
  const size = Math.max(1, Number(chunkSize) || BULK_CHUNK_SIZE);
  let count = 0;
  let skipped = [];
  let last = {};
  if (!list.length) return { movedCount: 0, skipped: [], last };
  for (let i = 0; i < list.length; i += size) {
    const slice = list.slice(i, i + size);
    last = await post(url, { ...extra, [itemsKey]: slice });
    count += Number(last[countKey] || last.movedCount || 0);
    skipped = skipped.concat(last.skipped || last.errors || []);
    if (onProgress) {
      onProgress({
        done: Math.min(i + slice.length, list.length),
        total: list.length,
        last,
      });
    }
  }
  return { ...last, movedCount: count, skipped, [countKey]: count };
}
