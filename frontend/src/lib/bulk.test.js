import { post } from "./api";
import { postInChunks } from "./bulk";

jest.mock("./api", () => ({
  post: jest.fn(),
}));

test("postInChunks sends slices and sums movedCount", async () => {
  post.mockImplementation(async (_url, body) => ({
    movedCount: body.leadIds.length,
    skipped: [],
  }));
  const ids = Array.from({ length: 120 }, (_, i) => `L${i}`);
  const r = await postInChunks("/leads/allocate", {
    items: ids,
    itemsKey: "leadIds",
    extra: { executive: "Prerna" },
    chunkSize: 50,
  });
  expect(post).toHaveBeenCalledTimes(3);
  expect(post.mock.calls[0][1].leadIds).toHaveLength(50);
  expect(post.mock.calls[2][1].leadIds).toHaveLength(20);
  expect(post.mock.calls[0][1].executive).toBe("Prerna");
  expect(r.movedCount).toBe(120);
});
