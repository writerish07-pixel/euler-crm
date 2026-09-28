import { bootNativeShell } from "./native";

describe("bootNativeShell", () => {
  test("is a no-op in jsdom (live website)", async () => {
    await expect(bootNativeShell()).resolves.toBe(false);
  });
});
